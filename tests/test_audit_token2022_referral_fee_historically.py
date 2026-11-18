import unittest
from types import SimpleNamespace
from unittest.mock import patch

from smart_money_radar.data_sources.token2022_transfer_fee_state import (
    TransferFeeConfigState, TransferFeeRate,
)
from tools.audit_token2022_referral_fee_historically import (
    TOKEN_2022_PROGRAM_ID,
    audit,
    epoch_for_slot,
)


class HistoricalReferralFeeAuditTests(unittest.TestCase):
    def test_epoch_for_normal_slot_uses_epoch_schedule(self):
        with patch(
            "tools.audit_token2022_referral_fee_historically.rpc_result",
            return_value={
                "firstNormalSlot": 1000,
                "firstNormalEpoch": 10,
                "slotsPerEpoch": 100,
            },
        ):
            self.assertEqual(epoch_for_slot("https://rpc.example", 1250), 12)

    def test_audit_matches_historical_withheld_delta(self):
        config = TransferFeeConfigState(
            withheld_amount=0,
            older_transfer_fee=TransferFeeRate(0, 1000, 100),
            newer_transfer_fee=TransferFeeRate(20, 500, 200),
        )
        mint_before = SimpleNamespace(
            owner=TOKEN_2022_PROGRAM_ID, data=b"mint-before",
            last_updated_slot=471000000, last_updated_transaction_index=2,
        )
        mint_after = SimpleNamespace(
            owner=TOKEN_2022_PROGRAM_ID, data=b"mint-after",
            last_updated_slot=471000000, last_updated_transaction_index=2,
        )
        referral_before = SimpleNamespace(
            owner=TOKEN_2022_PROGRAM_ID, data=b"ref-before",
            last_updated_slot=471000000, last_updated_transaction_index=1,
        )
        referral_after = SimpleNamespace(
            owner=TOKEN_2022_PROGRAM_ID, data=b"ref-after",
            last_updated_slot=471107341, last_updated_transaction_index=5,
        )
        with (
            patch(
                "tools.audit_token2022_referral_fee_historically.get_transaction_index",
                return_value=6,
            ),
            patch(
                "tools.audit_token2022_referral_fee_historically.epoch_for_slot",
                return_value=21,
            ),
            patch(
                "tools.audit_token2022_referral_fee_historically.get_historical_account_info_before_transaction",
                side_effect=[mint_before, referral_before],
            ),
            patch(
                "tools.audit_token2022_referral_fee_historically.get_historical_account_info",
                side_effect=[mint_after, referral_after],
            ),
            patch(
                "tools.audit_token2022_referral_fee_historically.decode_transfer_fee_config",
                return_value=config,
            ),
            patch(
                "tools.audit_token2022_referral_fee_historically.decode_transfer_fee_amount",
                side_effect=[
                    SimpleNamespace(withheld_amount=50),
                    SimpleNamespace(withheld_amount=80),
                ],
            ),
        ):
            result = audit(
                "https://rpc.example", "https://helius.example",
                "signature", 471107341, "mint", "referral-account", [1000, 500],
            )
        self.assertEqual(result["status"], "HISTORICAL_FEE_MATCH")
        self.assertEqual(result["transaction_index"], 6)
        self.assertEqual(result["selected_rate"]["basis_points"], 200)
        self.assertEqual(result["expected_fee_per_transfer_raw"], [20, 10])
        self.assertEqual(result["expected_fee_raw"], 30)
        self.assertEqual(result["withheld_delta_raw"], 30)
        self.assertFalse(result["reconciliation_released"])

    def test_audit_rejects_changed_mint_config(self):
        config_a = TransferFeeConfigState(
            0, TransferFeeRate(0, 100, 100), TransferFeeRate(10, 100, 100)
        )
        config_b = TransferFeeConfigState(
            0, TransferFeeRate(0, 100, 100), TransferFeeRate(10, 100, 200)
        )
        mint_a = SimpleNamespace(owner=TOKEN_2022_PROGRAM_ID, data=b"a")
        mint_b = SimpleNamespace(owner=TOKEN_2022_PROGRAM_ID, data=b"b")
        with (
            patch(
                "tools.audit_token2022_referral_fee_historically.get_transaction_index",
                return_value=1,
            ),
            patch(
                "tools.audit_token2022_referral_fee_historically.epoch_for_slot",
                return_value=10,
            ),
            patch(
                "tools.audit_token2022_referral_fee_historically.get_historical_account_info_before_transaction",
                return_value=mint_a,
            ),
            patch(
                "tools.audit_token2022_referral_fee_historically.get_historical_account_info",
                return_value=mint_b,
            ),
            patch(
                "tools.audit_token2022_referral_fee_historically.decode_transfer_fee_config",
                side_effect=[config_a, config_b],
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "mudou durante"):
                audit(
                    "https://rpc.example", "https://helius.example",
                    "signature", 471107341, "mint", "referral", [1000],
                )


if __name__ == "__main__":
    unittest.main()
