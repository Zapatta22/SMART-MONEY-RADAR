import unittest

from smart_money_radar.data_sources.damm_v2_accounts import (
    decode_damm_v2_swap_accounts,
)
from smart_money_radar.data_sources.damm_v2_decoder import (
    DammV2EvtSwap2,
    DammV2SwapResult,
    METEORA_DAMM_V2_PROGRAM_ID,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
)


def event(direction="A_TO_B", pool=bytes(32)):
    return DammV2EvtSwap2(
        pool=pool,
        trade_direction=direction,
        collect_fee_mode="BOTH_TOKEN",
        has_referral=False,
        amount_0=100,
        amount_1=90,
        swap_mode="EXACT_IN",
        swap_result=DammV2SwapResult(100, 0, 0, 90, 1, 0, 0, 0, 0),
        included_transfer_fee_amount_in=0,
        included_transfer_fee_amount_out=0,
        excluded_transfer_fee_amount_out=0,
        current_timestamp=1,
        reserve_a_amount=1000,
        reserve_b_amount=2000,
    )


class DammV2AccountsTests(unittest.TestCase):
    def setUp(self):
        self.keys = [
            "authority", "pool", "user-in", "user-out", "vault-a", "vault-b",
            "mint-a", "mint-b", "payer", SPL_TOKEN_PROGRAM_ID,
            TOKEN_2022_PROGRAM_ID, "referral", "event-authority",
            METEORA_DAMM_V2_PROGRAM_ID, "remaining",
        ]
        self.instruction = {"programId": METEORA_DAMM_V2_PROGRAM_ID,
                            "accounts": list(range(len(self.keys)))}

    def test_maps_a_to_b_accounts_and_preserves_remaining(self):
        result = decode_damm_v2_swap_accounts(
            self.instruction, self.keys, event()
        )
        self.assertEqual(result.input_token_account, "user-in")
        self.assertEqual(result.output_token_account, "user-out")
        self.assertEqual(result.input_vault, "vault-a")
        self.assertEqual(result.output_vault, "vault-b")
        self.assertEqual(result.input_mint, "mint-a")
        self.assertEqual(result.output_mint, "mint-b")
        self.assertEqual(result.input_token_program, SPL_TOKEN_PROGRAM_ID)
        self.assertEqual(result.output_token_program, TOKEN_2022_PROGRAM_ID)
        self.assertEqual(result.remaining_accounts, ("remaining",))

    def test_maps_b_to_a_direction_without_reordering_instruction_fields(self):
        result = decode_damm_v2_swap_accounts(
            self.instruction, self.keys, event("B_TO_A")
        )
        self.assertEqual(result.input_vault, "vault-b")
        self.assertEqual(result.output_vault, "vault-a")
        self.assertEqual(result.input_mint, "mint-b")
        self.assertEqual(result.output_mint, "mint-a")
        self.assertEqual(result.input_token_program, TOKEN_2022_PROGRAM_ID)
        self.assertEqual(result.output_token_program, SPL_TOKEN_PROGRAM_ID)

    def test_rejects_pool_mismatch(self):
        with self.assertRaisesRegex(ValueError, "pool"):
            decode_damm_v2_swap_accounts(
                self.instruction, self.keys, event(pool=bytes([1]) * 32)
            )

    def test_rejects_short_account_list_and_unknown_token_program(self):
        with self.assertRaisesRegex(ValueError, "14 contas"):
            decode_damm_v2_swap_accounts(
                {"accounts": [0] * 13}, self.keys, event()
            )
        bad = dict(self.instruction)
        bad["accounts"] = list(self.instruction["accounts"])
        bad["accounts"][9] = 0
        with self.assertRaisesRegex(ValueError, "token program"):
            decode_damm_v2_swap_accounts(bad, self.keys, event())

    def test_resolves_compiled_indexes_and_rejects_invalid_indexes(self):
        result = decode_damm_v2_swap_accounts(
            self.instruction, self.keys, event()
        )
        self.assertEqual(result.pool, "pool")
        bad = dict(self.instruction)
        bad["accounts"] = [999] + self.instruction["accounts"][1:]
        with self.assertRaisesRegex(ValueError, "accounts\\[0\\]"):
            decode_damm_v2_swap_accounts(bad, self.keys, event())


if __name__ == "__main__":
    unittest.main()
