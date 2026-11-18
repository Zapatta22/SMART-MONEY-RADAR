import unittest

from smart_money_radar.data_sources.damm_v2_accounts import DammV2SwapAccounts
from smart_money_radar.data_sources.damm_v2_analyzer import DammV2SwapEventAssociation
from smart_money_radar.data_sources.damm_v2_decoder import DammV2EvtSwap2, DammV2SwapResult
from smart_money_radar.data_sources.damm_v2_transfer_analyzer import (
    DammV2SwapTransferContext,
    analyze_damm_v2_transfer_evidence,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    SolanaTokenTransfer,
)


def _accounts():
    return DammV2SwapAccounts(
        pool_authority="authority", pool="pool",
        input_token_account="user-a", output_token_account="user-b",
        token_a_vault="vault-a", token_b_vault="vault-b",
        token_a_mint="mint-a", token_b_mint="mint-b", payer="payer",
        token_a_program=SPL_TOKEN_PROGRAM_ID,
        token_b_program=TOKEN_2022_PROGRAM_ID,
        referral_token_account="referral", event_authority="event",
        program="damm", remaining_accounts=(),
        input_vault="vault-a", output_vault="vault-b",
        input_mint="mint-a", output_mint="mint-b",
        input_token_program=SPL_TOKEN_PROGRAM_ID,
        output_token_program=TOKEN_2022_PROGRAM_ID,
    )


def _event(has_referral=False, referral_fee=0, direction="A_TO_B", fee_mode="BOTH_TOKEN"):
    return DammV2EvtSwap2(
        pool=bytes(32),
        trade_direction=direction,
        collect_fee_mode=fee_mode,
        has_referral=has_referral,
        amount_0=100,
        amount_1=90,
        swap_mode="EXACT_IN",
        swap_result=DammV2SwapResult(
            included_fee_input_amount=100,
            excluded_fee_input_amount=95,
            amount_left=0,
            output_amount=90,
            next_sqrt_price=1 << 64,
            claiming_fee=2,
            protocol_fee=1,
            compounding_fee=1,
            referral_fee=referral_fee,
        ),
        included_transfer_fee_amount_in=100,
        included_transfer_fee_amount_out=90,
        excluded_transfer_fee_amount_out=90,
        current_timestamp=1_700_000_000,
        reserve_a_amount=1_000,
        reserve_b_amount=2_000,
    )


def _association(status="MATCHED", outer=0, path=(0,), height=3, event=None):
    return DammV2SwapEventAssociation(
        status=status, instruction_index=outer, inner_instruction_index=1,
        cpi_path=path, stack_height=height, instruction=None,
        event_inner_instruction_index=4, event_cpi_path=(0, 1),
        event_stack_height=4, event=_event() if event is None else event,
    )


def _transfer(source, destination, program, mint, decimals, amount=100,
              outer=0, path=(0, 0), height=4, status="EXECUTED"):
    return SolanaTokenTransfer(
        program_id=program,
        program_name="SPL Token" if program == SPL_TOKEN_PROGRAM_ID else "Token-2022",
        instruction_type="TRANSFER_CHECKED",
        instruction_index=outer,
        inner_instruction_index=2,
        stack_height=height,
        cpi_path=path,
        source_account=source,
        destination_account=destination,
        authority="authority",
        mint=mint,
        amount_raw=amount,
        decimals=decimals,
        execution_status=status,
        source_format="compiled",
    )


class DammV2TransferAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.context = DammV2SwapTransferContext(_association(), _accounts())
        self.input = _transfer("user-a", "vault-a", SPL_TOKEN_PROGRAM_ID, "mint-a", 6)
        self.output = _transfer("vault-b", "user-b", TOKEN_2022_PROGRAM_ID, "mint-b", 9)

    def test_attributes_exact_input_and_output_descendant_transfers(self):
        result = analyze_damm_v2_transfer_evidence(
            [self.context], [self.input, self.output]
        )[0]
        self.assertEqual(result.status, "ATTRIBUTED")
        self.assertIs(result.input_transfer, self.input)
        self.assertIs(result.output_transfer, self.output)
        self.assertTrue(result.transfer_fee_review_required)
        self.assertIn("deltas e taxas", result.reason)

    def test_requires_exact_cpi_descendant_and_same_outer_instruction(self):
        unrelated = _transfer(
            "user-a", "vault-a", SPL_TOKEN_PROGRAM_ID, "mint-a", 6,
            path=(1, 0),
        )
        other_outer = _transfer(
            "vault-b", "user-b", TOKEN_2022_PROGRAM_ID, "mint-b", 9,
            outer=1,
        )
        result = analyze_damm_v2_transfer_evidence(
            [self.context], [unrelated, other_outer]
        )[0]
        self.assertEqual(result.status, "TRANSFER_MISSING")

    def test_rejects_transfer_occurring_after_evt_swap2(self):
        after_event = _transfer(
            "user-a", "vault-a", SPL_TOKEN_PROGRAM_ID, "mint-a", 6
        )
        after_event = SolanaTokenTransfer(
            **{**after_event.__dict__, "inner_instruction_index": 6}
        )
        result = analyze_damm_v2_transfer_evidence(
            [self.context], [after_event, self.output]
        )[0]
        self.assertEqual(result.status, "TRANSFER_MISSING")

    def test_rejects_transfer_simple_without_mint_and_decimals(self):
        simple = _transfer(
            "user-a", "vault-a", SPL_TOKEN_PROGRAM_ID, "mint-a", 6
        )
        simple = SolanaTokenTransfer(
            **{**simple.__dict__, "mint": None, "decimals": None,
               "instruction_type": "TRANSFER"}
        )
        result = analyze_damm_v2_transfer_evidence(
            [self.context], [simple, self.output]
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("mint/decimals ausentes", result.reason)

    def test_rejects_mint_or_program_mismatch(self):
        wrong_mint = _transfer(
            "user-a", "vault-a", SPL_TOKEN_PROGRAM_ID, "wrong-mint", 6
        )
        result = analyze_damm_v2_transfer_evidence(
            [self.context], [wrong_mint, self.output]
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("mint", result.reason)

    def test_marks_multiple_candidates_ambiguous(self):
        duplicate = _transfer(
            "user-a", "vault-a", SPL_TOKEN_PROGRAM_ID, "mint-a", 6,
            path=(0, 1), height=4,
        )
        result = analyze_damm_v2_transfer_evidence(
            [self.context], [self.input, duplicate, self.output]
        )[0]
        self.assertEqual(result.status, "AMBIGUOUS")

    def test_prevents_transfer_reuse_across_two_swaps(self):
        second = DammV2SwapTransferContext(
            _association(outer=0, path=(0,), height=3), _accounts()
        )
        result = analyze_damm_v2_transfer_evidence(
            [self.context, second], [self.input, self.output]
        )
        self.assertEqual([item.status for item in result], ["AMBIGUOUS", "AMBIGUOUS"])

    def test_rejects_transfer_with_untrusted_cpi_hierarchy(self):
        untrusted = SolanaTokenTransfer(
            **{**self.input.__dict__, "cpi_path_valid": False}
        )
        result = analyze_damm_v2_transfer_evidence(
            [self.context], [untrusted, self.output]
        )[0]
        self.assertEqual(result.status, "TRANSFER_MISSING")

    def test_failed_transfer_is_not_attributed(self):
        failed = _transfer(
            "user-a", "vault-a", SPL_TOKEN_PROGRAM_ID, "mint-a", 6,
            status="FAILED",
        )
        result = analyze_damm_v2_transfer_evidence(
            [self.context], [failed, self.output]
        )[0]
        self.assertEqual(result.status, "TRANSFER_MISSING")

    def test_attributes_referral_transfer_from_fee_mode_token_b_vault(self):
        event = _event(has_referral=True, referral_fee=5)
        context = DammV2SwapTransferContext(_association(event=event), _accounts())
        referral = _transfer(
            "vault-b", "referral", TOKEN_2022_PROGRAM_ID, "mint-b", 9, amount=5
        )
        result = analyze_damm_v2_transfer_evidence(
            [context], [self.input, self.output, referral]
        )[0]
        self.assertEqual(result.status, "ATTRIBUTED")
        self.assertIs(result.referral_transfer, referral)
        self.assertTrue(result.transfer_fee_review_required)
        self.assertIn("referral", result.reason)

    def test_attributes_referral_from_token_a_vault_when_fee_mode_requires_token_a(self):
        event = _event(
            has_referral=True,
            referral_fee=7,
            direction="B_TO_A",
            fee_mode="BOTH_TOKEN",
        )
        base = _accounts()
        accounts = DammV2SwapAccounts(
            **{
                **base.__dict__,
                "input_vault": "vault-b",
                "output_vault": "vault-a",
                "input_mint": "mint-b",
                "output_mint": "mint-a",
                "input_token_program": TOKEN_2022_PROGRAM_ID,
                "output_token_program": SPL_TOKEN_PROGRAM_ID,
            }
        )
        context = DammV2SwapTransferContext(_association(event=event), accounts)
        input_transfer = _transfer(
            "user-b", "vault-b", TOKEN_2022_PROGRAM_ID, "mint-b", 9
        )
        output_transfer = _transfer(
            "vault-a", "user-a", SPL_TOKEN_PROGRAM_ID, "mint-a", 6
        )
        referral = _transfer(
            "vault-a", "referral", SPL_TOKEN_PROGRAM_ID, "mint-a", 6, amount=7
        )
        result = analyze_damm_v2_transfer_evidence(
            [context], [input_transfer, output_transfer, referral]
        )[0]
        self.assertEqual(result.status, "ATTRIBUTED")
        self.assertIs(result.referral_transfer, referral)

    def test_requires_referral_transfer_when_event_has_nonzero_referral_fee(self):
        event = _event(has_referral=True, referral_fee=5)
        context = DammV2SwapTransferContext(_association(event=event), _accounts())
        result = analyze_damm_v2_transfer_evidence(
            [context], [self.input, self.output]
        )[0]
        self.assertEqual(result.status, "TRANSFER_MISSING")
        self.assertIn("referral", result.reason)

    def test_rejects_referral_transfer_amount_mismatch(self):
        event = _event(has_referral=True, referral_fee=5)
        context = DammV2SwapTransferContext(_association(event=event), _accounts())
        referral = _transfer(
            "vault-b", "referral", TOKEN_2022_PROGRAM_ID, "mint-b", 9, amount=6
        )
        result = analyze_damm_v2_transfer_evidence(
            [context], [self.input, self.output, referral]
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("diverge do EvtSwap2", result.reason)

    def test_marks_duplicate_referral_transfers_ambiguous(self):
        event = _event(has_referral=True, referral_fee=5)
        context = DammV2SwapTransferContext(_association(event=event), _accounts())
        first = _transfer(
            "vault-b", "referral", TOKEN_2022_PROGRAM_ID, "mint-b", 9, amount=5
        )
        second = _transfer(
            "vault-b", "referral", TOKEN_2022_PROGRAM_ID, "mint-b", 9, amount=5,
            path=(0, 1),
        )
        result = analyze_damm_v2_transfer_evidence(
            [context], [self.input, self.output, first, second]
        )[0]
        self.assertEqual(result.status, "AMBIGUOUS")

    def test_referral_transfer_fee_checked_instruction_remains_attributed_not_matched(self):
        event = _event(has_referral=True, referral_fee=5)
        context = DammV2SwapTransferContext(_association(event=event), _accounts())
        referral = _transfer(
            "vault-b", "referral", TOKEN_2022_PROGRAM_ID, "mint-b", 9, amount=5
        )
        referral = SolanaTokenTransfer(
            **{
                **referral.__dict__,
                "instruction_type": "TRANSFER_CHECKED_WITH_FEE",
                "fee_amount_raw": 1,
            }
        )
        result = analyze_damm_v2_transfer_evidence(
            [context], [self.input, self.output, referral]
        )[0]
        self.assertEqual(result.status, "ATTRIBUTED")
        self.assertIs(result.referral_transfer, referral)

    def test_rejects_referral_fee_without_has_referral_flag(self):
        event = _event(has_referral=False, referral_fee=5)
        context = DammV2SwapTransferContext(_association(event=event), _accounts())
        result = analyze_damm_v2_transfer_evidence(
            [context], [self.input, self.output]
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("sem has_referral", result.reason)

    def test_unmatched_swap_event_stays_unresolved(self):
        context = DammV2SwapTransferContext(
            _association(status="AMBIGUOUS"), _accounts()
        )
        result = analyze_damm_v2_transfer_evidence(
            [context], [self.input, self.output]
        )[0]
        self.assertEqual(result.status, "ASSOCIATION_UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
