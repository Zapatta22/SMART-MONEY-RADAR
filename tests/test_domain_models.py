import unittest
from datetime import datetime, timezone
from decimal import Decimal

from smart_money_radar.domain.models import (
    ObservedTransaction, PoolSnapshot, SwapClassification, SwapEvidence,
    SwapObservation, TokenBalanceDelta, WalletProfile, build_swap_operation_id,
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

    def test_swap_observation_contains_operation_not_semantic_evidence(self):
        item = SwapObservation(
            "op-1", "solana", "wallet", "sig", "USDC", "TOKEN",
            Decimal("2"), Decimal("3"), NOW, "1",
        )
        self.assertEqual(item.operation_id, "op-1")
        with self.assertRaises(ValueError):
            SwapObservation("op-1", "solana", "wallet", "sig", "A", "A",
                            Decimal("2"), Decimal("3"), NOW, "1")
        with self.assertRaises(ValueError):
            SwapObservation("op-1", "solana", "wallet", "sig", "A", "B",
                            Decimal("0"), Decimal("3"), NOW, "1")

    def test_swap_classification_accepts_buy_sell_and_unknown(self):
        self.assertEqual(SwapClassification("op-1", "BUY", Decimal("0.9"), "entrada de ativo").side, "BUY")
        self.assertEqual(SwapClassification("op-1", "SELL", Decimal("0.8"), "saída de ativo").side, "SELL")
        unknown = SwapClassification("op-1", "UNKNOWN", Decimal("0"), "evidência insuficiente")
        self.assertEqual(unknown.side, "UNKNOWN")
        with self.assertRaises(ValueError):
            SwapClassification("op-1", "UNKNOWN", Decimal("0.2"), "ambíguo")
        with self.assertRaises(ValueError):
            SwapClassification("op-1", "BUY", Decimal("1.1"), "inválido")
        with self.assertRaises(ValueError):
            SwapClassification("op-1", "BUY", Decimal("0.9"), "")

    def test_swap_evidence_preserves_program_venue_instruction_and_cpi(self):
        evidence = SwapEvidence("op-1", "program-id", "Raydium CPMM", 2, (0, 1), ("inner transfer",))
        self.assertEqual(evidence.cpi_path, (0, 1))
        with self.assertRaises(ValueError):
            SwapEvidence("op-1", "program-id", None, -1)

    def test_operation_id_is_stable_and_distinguishes_multiple_operations(self):
        first = build_swap_operation_id("solana", "signature", 2, (0, 1))
        repeated = build_swap_operation_id("solana", "signature", 2, (0, 1))
        second = build_swap_operation_id("solana", "signature", 2, (0, 2))
        third = build_swap_operation_id("solana", "signature", 3, ())
        self.assertEqual(first, repeated)
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, third)

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
