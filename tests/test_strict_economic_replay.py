"""No economic performance is emitted from untrusted or inconsistent evidence."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smart_money_radar.domain.paper_entry_risk_policy import EntryRiskLimits, EntryRiskSnapshot
from smart_money_radar.domain.paper_replay import PaperConfig, ReplayTick
from smart_money_radar.services.evidence_chain import EvidenceChain
from smart_money_radar.services.strict_economic_replay import (
    StrictReplayCandidate, strict_economic_replay,
)

T=datetime(2026,11,20,tzinfo=timezone.utc)
CFG=PaperConfig(initial_cash=Decimal(100),max_entry_cash=Decimal(10),max_exposure=Decimal(".2"),fee_bps=Decimal(20),slippage_bps=Decimal(30))
LIMITS=EntryRiskLimits(max_position_fraction=Decimal(".2"),max_daily_loss_fraction=Decimal(".1"),max_slippage_bps=Decimal(40),min_liquidity_quote=Decimal(100))


def candidate(**changes):
    chain=EvidenceChain(operation_id="op",signature="sig",slot=10,pool="pool",
                        quote_id="q1",source_id="source",cutoff=T,
                        raw_local_sha256="a"*64,quote_raw_sha256="b"*64,
                        status="LOCALLY_LINKED_UNATTESTED",reasons=())
    tick=ReplayTick(at=T,market_at=T-timedelta(seconds=1),price=Decimal("1"),
                    volume=Decimal("100"),signal="BUY",entry_allowed=True,quote_id="q1",
                    bid=Decimal(".99"),ask=Decimal("1.01"),
                    bid_size=Decimal("200"),ask_size=Decimal("200"))
    risk=EntryRiskSnapshot(equity=Decimal(100),proposed_notional=Decimal(10),
                           daily_realized_pnl=Decimal(0),estimated_slippage_bps=Decimal(20),
                           verified_liquidity_quote=Decimal(200),emergency_halt=False,
                           evidence_verified=True)
    return replace(StrictReplayCandidate(chain,tick,risk,True,T,"e1","pool"),**changes)


def run(*rows):
    return strict_economic_replay(tuple(rows),pool="pool",config=CFG,
                                  risk_limits=LIMITS,cutoff=T+timedelta(minutes=2))


class StrictEconomicReplayTests(unittest.TestCase):
    def test_local_hashes_never_enable_economic_results(self):
        out=run(candidate())
        self.assertEqual(out.status,"BLOCKED")
        self.assertIn("full_chain_not_authenticated",out.reasons)
        self.assertIsNone(out.immediate)
        self.assertIsNone(out.confirmed)
        self.assertIsNone(out.comparison)
        self.assertFalse(out.economic_results_credible)
        self.assertFalse(out.operational_authorized)

    def test_fake_caller_flags_cannot_override_missing_executability(self):
        chain=replace(candidate().chain,provider_authenticated=True,finalized_attested=True)
        out=run(candidate(chain=chain))
        self.assertIn("full_chain_not_authenticated",out.reasons)

    def test_pool_mismatch_is_blocked(self):
        out=run(candidate(evidence_pool="other"))
        self.assertIn("pool_mismatch",out.reasons)

    def test_missing_quote_id_is_blocked(self):
        chain=replace(candidate().chain,quote_id=None)
        out=run(candidate(chain=chain))
        self.assertIn("missing_quote_or_evidence_id",out.reasons)

    def test_future_quote_is_blocked(self):
        chain=replace(candidate().chain,cutoff=T-timedelta(seconds=3))
        out=run(candidate(chain=chain))
        self.assertIn("future_price",out.reasons)

    def test_duplicate_quotes_blocked(self):
        a=candidate()
        b=candidate(chain=replace(a.chain,cutoff=T+timedelta(seconds=1)))
        out=run(a,b)
        self.assertIn("duplicate_quote_id",out.reasons)

    def test_critical_risk_survives_positive_classification(self):
        risk=replace(candidate().risk,emergency_halt=True)
        out=run(candidate(risk=risk))
        self.assertIn("mandatory_risk_block",out.reasons)

    def test_no_quotes_produces_no_fake_pnl(self):
        out=run()
        self.assertEqual(out.status,"BLOCKED")
        self.assertIn("no_historical_evidence",out.reasons)
        self.assertIsNone(out.comparison)

    def test_result_reproducible(self):
        self.assertEqual(run(candidate()),run(candidate()))

    def test_classification_blocked(self):
        self.assertIn("classification_blocked",
                      run(candidate(classification_allows_simulation=False)).reasons)


if __name__=="__main__":
    unittest.main()
