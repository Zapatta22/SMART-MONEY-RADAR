import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smart_money_radar.domain.paper_evidence_replay import replay_with_evidence
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

    def test_model_mode_explicitly_non_executable(self):
        records = {f"q{i}": self.evidence(i, source="MODEL_ESTIMATE_NOT_OBSERVED")
                   for i in range(4)}
        result = self.replay(records, require_observed_quote=False)
        self.assertEqual(result["evidence_policy"], "MODEL_ALLOWED_PAPER_ONLY")
        self.assertTrue(result["immediate"].fills)


if __name__ == "__main__":
    unittest.main()
