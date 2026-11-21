"""CM29: two independent non-trading radar status channels."""
import hashlib
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smart_money_radar.services.radar_integration_status import (
    RadarObservation, compose_radar_snapshot,
)
from smart_money_radar.services.opportunity_classifier import (
    OpportunityEvidence, classify_opportunity,
)
from smart_money_radar.services.wallet_consensus import WalletConsensusReport
from smart_money_radar.domain.paper_entry_risk_policy import (
    EntryRiskLimits, EntryRiskSnapshot,
)

T=datetime(2026,11,20,20,tzinfo=timezone.utc)
RAW=b"synthetic source proof for contract test"


def observation(radar="smart_money", **changes):
    record=RadarObservation(
        radar=radar, source_id="local-source",pool="pool-1",signature="sig-1",
        slot=471887787,available_at=T,raw_payload=RAW,
        raw_sha256=hashlib.sha256(RAW).hexdigest(),
        coverage="COMPLETE",source_authenticated=True,
    )
    return replace(record,**changes)


def classification():
    evidence=OpportunityEvidence(
        token_mint="token-1",chain="solana",pool="pool-1",as_of=T,
        source_id="local-source",source_status="VERIFIED",
        history_coverage="COMPLETE",token_safety="VERIFIED",
        liquidity_quote=Decimal("15000"),volume_quote=Decimal("5000"),
        liquidity_verified=True,volume_verified=True,
        price_confirmation=True,volume_confirmation=True,
        wallet_independence_verified=True,
    )
    consensus=WalletConsensusReport(
        direction="BUY",eligible_wallets=4,supporting_signatures=6,
        rejected_wallets=(),members=(),independence_verified=True,
        actionable=False,reasons=(),
    )
    return classify_opportunity(evidence,consensus)


def risk():
    return (EntryRiskLimits(
        max_position_fraction=Decimal("0.1"),
        max_daily_loss_fraction=Decimal("0.03"),
        max_slippage_bps=Decimal("300"),
        min_liquidity_quote=Decimal("1000"),
    ),EntryRiskSnapshot(
        equity=Decimal("10000"),proposed_notional=Decimal("100"),
        daily_realized_pnl=Decimal("-50"),estimated_slippage_bps=Decimal("40"),
        verified_liquidity_quote=Decimal("10000"),
        emergency_halt=False,evidence_verified=True,
    ))


class RadarIntegrationStatusTests(unittest.TestCase):
    def test_launch_and_smart_money_remain_independent_and_non_trading(self):
        limits,snap=risk()
        launch=compose_radar_snapshot(observation("launch"),risk_limits=limits,risk_snapshot=snap)
        smart=compose_radar_snapshot(observation(),classification=classification(),
                                     risk_limits=limits,risk_snapshot=snap)
        self.assertEqual((launch.radar,smart.radar),("launch","smart_money"))
        self.assertEqual((launch.verdict,smart.verdict),("UNKNOWN","PRIORITY"))
        self.assertEqual(launch.paper_modes,smart.paper_modes)
        self.assertEqual(smart.paper_modes,(("immediate","BLOCKED"),("confirmed","BLOCKED")))
        self.assertFalse(launch.operational_authorized)
        self.assertFalse(smart.operational_authorized)
        self.assertIn("classification_missing",launch.reasons)
        self.assertEqual(smart.evidence_status,"LOCALLY_CONSISTENT")

    def test_unknown_coverage_never_unlocks_financial_execution(self):
        obj=compose_radar_snapshot(observation(coverage="UNKNOWN"))
        self.assertEqual(obj.coverage,"UNKNOWN")
        self.assertIn("historical_coverage_unproven",obj.reasons)
        self.assertEqual(dict(obj.paper_modes)["confirmed"],"BLOCKED")
        self.assertFalse(obj.operational_authorized)

    def test_raw_integrity_conflict_reports_conflicted(self):
        obj=compose_radar_snapshot(observation(raw_payload=b"tampered"))
        self.assertEqual(obj.evidence_status,"CONFLICTED")
        self.assertIn("raw_sha256_conflict",obj.reasons)
        self.assertFalse(obj.operational_authorized)

    def test_missing_signature_and_publication_never_promote_unknown(self):
        obj=compose_radar_snapshot(observation(signature=None,available_at=None))
        self.assertEqual(obj.evidence_status,"UNKNOWN")
        self.assertIn("signature_missing",obj.reasons)
        self.assertIn("publication_time_missing",obj.reasons)

    def test_fake_verified_and_complete_do_not_authorize_orders(self):
        limits,snap=risk()
        obj=compose_radar_snapshot(observation(),classification=classification(),
                                   risk_limits=limits,risk_snapshot=snap)
        self.assertEqual(obj.verdict,"PRIORITY")
        self.assertFalse(obj.operational_authorized)
        self.assertTrue(all(mode=="BLOCKED" for _,mode in obj.paper_modes))

    def test_source_pool_and_cutoff_mismatch_fail_closed(self):
        for changes in ({"source_id":"different"},{"pool":"different"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                compose_radar_snapshot(observation(**changes),classification=classification())
        with self.assertRaises(ValueError):
            compose_radar_snapshot(observation(available_at=T+timedelta(seconds=1)),
                                   classification=classification())

    def test_emergency_halt_preserves_existing_risk_rejection(self):
        limits,snap=risk()
        obj=compose_radar_snapshot(observation(),risk_limits=limits,
                                   risk_snapshot=replace(snap,emergency_halt=True))
        self.assertIn("emergency_halt",obj.reasons)
        self.assertFalse(obj.operational_authorized)

    def test_launch_cannot_reuse_smart_money_classification_implicitly(self):
        with self.assertRaises(ValueError):
            compose_radar_snapshot(observation("launch"),classification=classification())

    def test_unverified_source_and_regressive_evidence_types(self):
        obj=compose_radar_snapshot(observation(source_authenticated=False))
        self.assertIn("source_not_authenticated",obj.reasons)
        for change in ({"slot":-1},{"raw_sha256":"not-hash"},{"coverage":"WRONG"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                compose_radar_snapshot(observation(**change))

    def test_missing_risk_pair_is_rejected(self):
        limits,_=risk()
        with self.assertRaises(ValueError):
            compose_radar_snapshot(observation(),risk_limits=limits)


if __name__=="__main__":
    unittest.main()
