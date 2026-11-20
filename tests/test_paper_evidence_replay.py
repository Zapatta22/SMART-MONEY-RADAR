import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smart_money_radar.domain.paper_evidence_replay import replay_with_evidence
from smart_money_radar.domain.paper_entry_risk_policy import EntryRiskLimits, EntryRiskSnapshot
from smart_money_radar.domain.paper_replay import PaperConfig, ReplayTick


class EvidenceReplayTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 11, 19, tzinfo=timezone.utc)
        self.config = PaperConfig(
            initial_cash=Decimal("1000"), max_entry_cash=Decimal("100"),
            max_exposure=Decimal("0.5"),
        )

    def tick(self, minute, signal="NONE"):
        return ReplayTick(
            at=self.start + timedelta(minutes=minute),
            market_at=self.start + timedelta(minutes=minute),
            price=Decimal("10") + Decimal(minute) / 10,
            volume=Decimal(100 + minute * 10),
            signal=signal, entry_allowed=True, quote_id=f"q{minute}",
        )

    def evidence(self, minute, *, source="OBSERVED_MARKET_QUOTE",
                 available_minute=None):
        return [{
            "evidence_id": f"e{minute}", "pool": "pool-a",
            "observed_at": (self.start + timedelta(minutes=minute)).isoformat(),
            "available_at": (self.start + timedelta(
                minutes=minute if available_minute is None else available_minute
            )).isoformat(),
            "source": source,
            "is_observed_quote": source == "OBSERVED_MARKET_QUOTE",
        }]

    def replay(self, evidence, **kwargs):
        ticks = [self.tick(0, "BUY"), self.tick(1), self.tick(2), self.tick(3)]
        return replay_with_evidence(
            ticks, evidence, config=self.config, expected_pool="pool-a", **kwargs,
        )

    def test_both_modes_can_trade_on_verified_observations(self):
        records = {f"q{i}": self.evidence(i) for i in range(4)}
        result = self.replay(records)
        self.assertTrue(any(f.side == "BUY" for f in result["immediate"].fills))
        self.assertTrue(any(f.side == "BUY" for f in result["confirmed"].fills))

    def test_missing_evidence_blocks_both_modes(self):
        result = self.replay({})
        self.assertFalse(result["immediate"].fills)
        self.assertFalse(result["confirmed"].fills)

    def test_future_and_model_evidence_cannot_be_used_as_observed(self):
        records = {f"q{i}": self.evidence(i) for i in range(4)}
        records["q0"] = self.evidence(0, available_minute=2)
        result = self.replay(records)
        self.assertFalse(result["immediate"].fills)
        self.assertFalse(result["confirmed"].fills)
        records["q0"] = self.evidence(0, source="MODEL_ESTIMATE_NOT_OBSERVED")
        result = self.replay(records)
        self.assertFalse(result["immediate"].fills)
        self.assertFalse(result["confirmed"].fills)

    def test_unverified_future_price_cannot_fill_pending_buy(self):
        records = {"q0": self.evidence(0), "q2": self.evidence(2),
                   "q3": self.evidence(3)}
        result = self.replay(records)
        fills = result["immediate"].fills
        self.assertTrue(fills)
        self.assertEqual(fills[0].filled_at, self.start + timedelta(minutes=2))
        self.assertEqual(result["rejected_evidence_ticks"], 1)

    def test_unverified_price_cannot_trigger_exit_or_valuation(self):
        records = {"q0": self.evidence(0), "q1": self.evidence(1)}
        result = self.replay(records)
        self.assertEqual(result["verified_ticks"], 2)
        self.assertEqual(result["rejected_evidence_ticks"], 2)
        self.assertEqual(result["immediate"].final_equity,
                         self.config.initial_cash - Decimal("100")
                         + result["immediate"].open_quantity * Decimal("10.1"))

    def test_as_of_cutoff_preserves_only_available_history(self):
        records = {f"q{i}": self.evidence(i) for i in range(4)}
        result = self.replay(records, as_of=self.start + timedelta(minutes=1))
        self.assertEqual(result["verified_ticks"], 2)
        self.assertEqual(result["excluded_after_cutoff"], 2)
        self.assertEqual(result["immediate"].fills[0].filled_at,
                         self.start + timedelta(minutes=1))

    def test_as_of_rejects_naive_datetime(self):
        with self.assertRaisesRegex(ValueError, "as_of"):
            self.replay({}, as_of=datetime(2026, 11, 19))

    def test_shared_risk_policy_blocks_both_modes(self):
        records = {f"q{i}": self.evidence(i) for i in range(4)}
        limits = EntryRiskLimits(Decimal("0.2"), Decimal("0.05"),
                                 Decimal("100"), Decimal("1000"))
        blocked = EntryRiskSnapshot(
            Decimal("1000"), Decimal("100"), Decimal("0"),
            Decimal("20"), Decimal("2000"), True, True,
        )
        risk = {f"q{i}": blocked for i in range(4)}
        result = self.replay(records, risk_limits=limits, risk_by_quote=risk)
        self.assertEqual(result["rejected_risk_ticks"], 4)
        self.assertFalse(result["immediate"].fills)
        self.assertFalse(result["confirmed"].fills)

    def test_missing_risk_snapshot_blocks_entry(self):
        records = {f"q{i}": self.evidence(i) for i in range(4)}
        limits = EntryRiskLimits(Decimal("0.2"), Decimal("0.05"),
                                 Decimal("100"), Decimal("1000"))
        result = self.replay(records, risk_limits=limits, risk_by_quote={})
        self.assertEqual(result["rejected_risk_ticks"], 4)
        self.assertFalse(result["immediate"].fills)
        self.assertFalse(result["confirmed"].fills)

    def test_model_mode_explicitly_non_executable(self):
        records = {f"q{i}": self.evidence(i, source="MODEL_ESTIMATE_NOT_OBSERVED")
                   for i in range(4)}
        result = self.replay(records, require_observed_quote=False)
        self.assertEqual(result["evidence_policy"], "MODEL_ALLOWED_PAPER_ONLY")
        self.assertTrue(result["immediate"].fills)


if __name__ == "__main__":
    unittest.main()
