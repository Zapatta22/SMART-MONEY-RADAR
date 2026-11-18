import unittest
from datetime import datetime, timezone
from decimal import Decimal

from smart_money_radar.domain.models import (
    ObservedTransaction, PoolSnapshot, SwapObservation, TokenBalanceDelta, WalletProfile,
)

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


class DomainContractTests(unittest.TestCase):
    def test_accepts_valid_observed_transaction(self):
        item = ObservedTransaction("solana", "wallet", "sig", NOW, {}, "1", "parsed", slot=12)
        self.assertEqual(item.slot, 12)

    def test_rejects_invalid_observation_status_and_slot(self):
        with self.assertRaises(ValueError):
            ObservedTransaction("solana", "wallet", "sig", NOW, {}, "1", "unknown")
        with self.assertRaises(ValueError):
            ObservedTransaction("solana", "wallet", "sig", NOW, {}, "1", "parsed", slot=-1)

    def test_validates_token_balance_delta(self):
        item = TokenBalanceDelta("solana", "wallet", "sig", "mint", "in", Decimal("1.25"), 6)
        self.assertEqual(item.amount, Decimal("1.25"))
        with self.assertRaises(ValueError):
            TokenBalanceDelta("solana", "wallet", "sig", "mint", "in", Decimal("0"))
        with self.assertRaises(ValueError):
            TokenBalanceDelta("solana", "wallet", "sig", "mint", "in", Decimal("1"), True)

    def test_swap_requires_two_assets_and_evidence(self):
        item = SwapObservation("solana", "wallet", "sig", "A", "B", Decimal("2"),
                               Decimal("3"), Decimal("0.8"), ("token_balance_deltas",), NOW, "1")
        self.assertEqual(item.confidence, Decimal("0.8"))
        with self.assertRaises(ValueError):
            SwapObservation("solana", "wallet", "sig", "A", "A", Decimal("2"),
                            Decimal("3"), Decimal("0.8"), ("evidence",), NOW, "1")
        with self.assertRaises(ValueError):
            SwapObservation("solana", "wallet", "sig", "A", "B", Decimal("2"),
                            Decimal("3"), Decimal("1.1"), ("evidence",), NOW, "1")
        with self.assertRaises(ValueError):
            SwapObservation("solana", "wallet", "sig", "A", "B", Decimal("2"),
                            Decimal("3"), Decimal("0.8"), (), NOW, "1")

    def test_pool_snapshot_validates_reserves(self):
        PoolSnapshot("solana", "pool", "A", "B", Decimal("10"), Decimal("20"), NOW)
        with self.assertRaises(ValueError):
            PoolSnapshot("solana", "pool", "A", "B", Decimal("-1"), Decimal("20"), NOW)

    def test_wallet_profile_validates_metrics_and_time_order(self):
        profile = WalletProfile("solana", "wallet", NOW, NOW, 10, 3, Decimal("2.5"), Decimal("0.6"))
        self.assertEqual(profile.swaps_observed, 3)
        with self.assertRaises(ValueError):
            WalletProfile("solana", "wallet", NOW, NOW, 2, 3)
        with self.assertRaises(ValueError):
            WalletProfile("solana", "wallet", NOW, NOW, 2, 1, win_rate=Decimal("1.5"))
