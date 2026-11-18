import unittest
from types import SimpleNamespace
from unittest.mock import patch

from smart_money_radar.data_sources.solana_token_transfer_decoder import TOKEN_2022_PROGRAM_ID
from smart_money_radar.data_sources.token2022_fee_absence_proof import (
    TOKEN_2022_PROGRAM_ID as TOKEN_2022_OWNER,
)
from smart_money_radar.data_sources.token2022_fee_proof_resolver import (
    resolve_token2022_no_fee_proofs,
)


def mint_without_transfer_fee_config():
    data = bytearray(166)
    data[165] = 1
    return bytes(data)


class Token2022FeeProofResolverTests(unittest.TestCase):
    def setUp(self):
        self.raw = {
            "result": {
                "slot": 471107341,
                "transaction": {"signatures": ["signature"]},
                "meta": {"err": None},
            }
        }
        self.transfer = SimpleNamespace(
            execution_status="EXECUTED",
            program_id=TOKEN_2022_PROGRAM_ID,
            instruction_type="TRANSFER_CHECKED",
            mint="mint",
        )
        self.preflight = SimpleNamespace(
            transfer_evidence=[
                SimpleNamespace(
                    status="ATTRIBUTED",
                    referral_transfer=self.transfer,
                )
            ],
            transfers=[self.transfer],
        )

    def test_resolves_proof_for_attributed_token_2022_referral(self):
        with (
            patch(
                "smart_money_radar.data_sources.token2022_fee_proof_resolver.process_damm_v2_transaction",
                return_value=self.preflight,
            ),
            patch(
                "smart_money_radar.data_sources.token2022_fee_proof_resolver.get_transaction_index",
                return_value=144,
            ) as get_index,
            patch(
                "smart_money_radar.data_sources.token2022_fee_proof_resolver._fetch_current_mint",
                return_value=(
                    TOKEN_2022_OWNER, mint_without_transfer_fee_config(), 471116391
                ),
            ),
        ):
            result = resolve_token2022_no_fee_proofs(
                self.raw,
                monitored_wallet="wallet",
                signature="signature",
                rpc_endpoint="https://mainnet.helius-rpc.com",
            )
        self.assertEqual(len(result.proofs), 1)
        self.assertEqual(result.proofs[0].mint, "mint")
        self.assertEqual(result.proofs[0].transaction_index, 144)
        self.assertEqual(result.proofs[0].fee_amount_raw, 0)
        self.assertEqual(result.unresolved_mints, ())
        get_index.assert_called_once()

    def test_returns_unresolved_when_mint_has_transfer_fee_config(self):
        data = bytearray(166 + 4 + 108)
        data[165] = 1
        data[166:168] = (1).to_bytes(2, "little")
        data[168:170] = (108).to_bytes(2, "little")
        with (
            patch(
                "smart_money_radar.data_sources.token2022_fee_proof_resolver.process_damm_v2_transaction",
                return_value=self.preflight,
            ),
            patch(
                "smart_money_radar.data_sources.token2022_fee_proof_resolver.get_transaction_index",
                return_value=144,
            ),
            patch(
                "smart_money_radar.data_sources.token2022_fee_proof_resolver._fetch_current_mint",
                return_value=(TOKEN_2022_OWNER, bytes(data), 471116391),
            ),
        ):
            result = resolve_token2022_no_fee_proofs(
                self.raw,
                monitored_wallet="wallet",
                signature="signature",
                rpc_endpoint="https://mainnet.helius-rpc.com",
            )
        self.assertEqual(result.proofs, ())
        self.assertEqual(result.unresolved_mints, ("mint",))
        self.assertIn("TransferFeeConfig está presente", result.reasons[0])

    def test_resolves_token2022_mints_used_by_supported_routed_venues(self):
        routed_transfer = SimpleNamespace(
            execution_status="EXECUTED",
            program_id=TOKEN_2022_PROGRAM_ID,
            instruction_type="TRANSFER_CHECKED",
            mint="routed-mint",
            cpi_path_valid=True,
            cpi_program_path=(
                "4X3dGCFh63SyE2bNZdGUV7Rj5ukK1XgrxesoxyKQNiRN",
                "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
            ),
        )
        preflight = SimpleNamespace(transfer_evidence=[], transfers=[routed_transfer])
        with (
            patch(
                "smart_money_radar.data_sources.token2022_fee_proof_resolver.process_damm_v2_transaction",
                return_value=preflight,
            ),
            patch(
                "smart_money_radar.data_sources.token2022_fee_proof_resolver.get_transaction_index",
                return_value=144,
            ),
            patch(
                "smart_money_radar.data_sources.token2022_fee_proof_resolver._fetch_current_mint",
                return_value=(
                    TOKEN_2022_OWNER, mint_without_transfer_fee_config(), 471116391
                ),
            ),
        ):
            result = resolve_token2022_no_fee_proofs(
                self.raw,
                monitored_wallet="wallet",
                signature="signature",
                rpc_endpoint="https://mainnet.helius-rpc.com",
            )
        self.assertEqual([proof.mint for proof in result.proofs], ["routed-mint"])

    def test_skips_transactions_without_attributed_token_2022_referral(self):
        preflight = SimpleNamespace(transfer_evidence=[], transfers=[])
        with (
            patch(
                "smart_money_radar.data_sources.token2022_fee_proof_resolver.process_damm_v2_transaction",
                return_value=preflight,
            ),
            patch(
                "smart_money_radar.data_sources.token2022_fee_proof_resolver.get_transaction_index"
            ) as get_index,
            patch(
                "smart_money_radar.data_sources.token2022_fee_proof_resolver._fetch_current_mint"
            ) as fetch_mint,
        ):
            result = resolve_token2022_no_fee_proofs(
                self.raw,
                monitored_wallet="wallet",
                signature="signature",
                rpc_endpoint="https://mainnet.helius-rpc.com",
            )
        self.assertEqual(result.proofs, ())
        get_index.assert_not_called()
        fetch_mint.assert_not_called()


if __name__ == "__main__":
    unittest.main()
