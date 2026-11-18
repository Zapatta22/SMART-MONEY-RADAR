import unittest

from smart_money_radar.data_sources.token2022_fee_absence_proof import (
    TOKEN_2022_PROGRAM_ID,
    Token2022NoTransferFeeProof,
    build_no_transfer_fee_proof,
)
from smart_money_radar.data_sources.token2022_transfer_fee_state import (
    transfer_fee_config_present,
)


def mint_without_transfer_fee_config():
    data = bytearray(166)
    data[165] = 1
    return bytes(data)


def mint_with_transfer_fee_config():
    data = bytearray(166 + 4 + 108)
    data[165] = 1
    data[166:168] = (1).to_bytes(2, "little")
    data[168:170] = (108).to_bytes(2, "little")
    return bytes(data)


class Token2022FeeAbsenceProofTests(unittest.TestCase):
    def test_validates_absence_and_builds_zero_fee_proof(self):
        mint_data = mint_without_transfer_fee_config()
        self.assertFalse(transfer_fee_config_present(mint_data))
        proof = build_no_transfer_fee_proof(
            mint="mint",
            signature="signature",
            transaction_slot=471107341,
            transaction_index=144,
            current_snapshot_slot=471116391,
            owner=TOKEN_2022_PROGRAM_ID,
            mint_data=mint_data,
            transaction_successful=True,
            mint_transfer_observed=True,
        )
        self.assertEqual(proof.fee_amount_raw, 0)
        self.assertIn("antes de InitializeMint", proof.basis)
        self.assertEqual(proof.transaction_index, 144)

    def test_rejects_present_or_malformed_transfer_fee_config(self):
        self.assertTrue(transfer_fee_config_present(mint_with_transfer_fee_config()))
        with self.assertRaisesRegex(ValueError, "presente"):
            build_no_transfer_fee_proof(
                mint="mint",
                signature="signature",
                transaction_slot=10,
                transaction_index=0,
                current_snapshot_slot=11,
                owner=TOKEN_2022_PROGRAM_ID,
                mint_data=mint_with_transfer_fee_config(),
                transaction_successful=True,
                mint_transfer_observed=True,
            )
        with self.assertRaisesRegex(ValueError, "truncados"):
            transfer_fee_config_present(b"short")

    def test_rejects_unproven_transaction_or_wrong_owner(self):
        base = dict(
            mint="mint",
            signature="signature",
            transaction_slot=10,
            transaction_index=0,
            current_snapshot_slot=11,
            owner=TOKEN_2022_PROGRAM_ID,
            mint_data=mint_without_transfer_fee_config(),
            transaction_successful=True,
            mint_transfer_observed=True,
        )
        with self.assertRaisesRegex(ValueError, "execução"):
            build_no_transfer_fee_proof(**{**base, "transaction_successful": False})
        with self.assertRaisesRegex(ValueError, "uso do mint"):
            build_no_transfer_fee_proof(**{**base, "mint_transfer_observed": False})
        with self.assertRaisesRegex(ValueError, "não pertence"):
            build_no_transfer_fee_proof(**{**base, "owner": "wrong-owner"})
        with self.assertRaisesRegex(ValueError, "antecede"):
            build_no_transfer_fee_proof(**{**base, "current_snapshot_slot": 9})


if __name__ == "__main__":
    unittest.main()
