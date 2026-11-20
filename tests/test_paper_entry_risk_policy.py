import unittest
from decimal import Decimal

from smart_money_radar.domain.paper_entry_risk_policy import (
    EntryRiskLimits, EntryRiskSnapshot, evaluate_entry_risk,
)


class PaperEntryRiskPolicyTests(unittest.TestCase):
    def setUp(self):
        self.limits = EntryRiskLimits(
            Decimal("0.20"), Decimal("0.05"), Decimal("100"), Decimal("1000"),
        )
        self.base = dict(
            equity=Decimal("1000"), proposed_notional=Decimal("100"),
            daily_realized_pnl=Decimal("0"), estimated_slippage_bps=Decimal("30"),
            verified_liquidity_quote=Decimal("2000"),
            emergency_halt=False, evidence_verified=True,
        )

    def check(self, **overrides):
        return evaluate_entry_risk(self.limits, EntryRiskSnapshot(**(self.base | overrides)))

    def test_all_checks_pass(self):
        self.assertEqual(self.check(), ())

    def test_halt_and_missing_evidence_block(self):
        self.assertEqual(
            self.check(emergency_halt=True, evidence_verified=False),
            ("emergency_halt", "evidence_unverified"),
        )

    def test_position_loss_slippage_liquidity_limits(self):
        reasons = self.check(
            proposed_notional=Decimal("250"),
            daily_realized_pnl=Decimal("-50"),
            estimated_slippage_bps=Decimal("101"),
            verified_liquidity_quote=Decimal("999"),
        )
        self.assertEqual(reasons, (
            "position_limit", "daily_loss_limit", "slippage_limit", "liquidity_limit",
        ))

    def test_zero_equity_blocks_without_division(self):
        self.assertIn("invalid_capital", self.check(equity=Decimal("0")))

    def test_rejects_nan_and_bool_instead_of_decimal(self):
        with self.assertRaises(ValueError):
            self.check(equity=Decimal("NaN"))
        with self.assertRaises(ValueError):
            self.check(equity=True)

    def test_rejects_invalid_limits(self):
        with self.assertRaises(ValueError):
            EntryRiskLimits(Decimal("1.1"), Decimal("0.05"),
                            Decimal("100"), Decimal("1000"))


if __name__ == "__main__":
    unittest.main()
