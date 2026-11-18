import unittest
from dataclasses import replace

from smart_money_radar.data_sources.damm_v2_accounts import DammV2SwapAccounts
from smart_money_radar.data_sources.damm_v2_analyzer import DammV2SwapEventAssociation
from smart_money_radar.data_sources.damm_v2_decoder import DammV2EvtSwap2, DammV2SwapResult
from smart_money_radar.data_sources.damm_v2_economic_reconciliation import (
    reconcile_damm_v2_economic_batch,
)
from smart_money_radar.data_sources.damm_v2_transfer_analyzer import DammV2SwapTransferContext, DammV2TransferEvidence
from smart_money_radar.data_sources.solana_token_balance_delta_decoder import (
    SolanaTokenAccountBalanceDelta,
    SolanaTokenBalanceDeltaIssue,
    SolanaTokenBalanceDeltaResult,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    SolanaTokenTransfer,
)
from smart_money_radar.data_sources.solana_wrapped_sol_funding import NATIVE_MINT


def _accounts():
    return DammV2SwapAccounts(
        pool_authority="authority", pool="pool",
        input_token_account="user-a", output_token_account="user-b",
        token_a_vault="vault-a", token_b_vault="vault-b",
        token_a_mint="mint-a", token_b_mint="mint-b", payer="payer",
        token_a_program=TOKEN_2022_PROGRAM_ID,
        token_b_program=TOKEN_2022_PROGRAM_ID,
        referral_token_account="referral", event_authority="event",
        program="damm", remaining_accounts=(),
        input_vault="vault-a", output_vault="vault-b",
        input_mint="mint-a", output_mint="mint-b",
        input_token_program=TOKEN_2022_PROGRAM_ID,
        output_token_program=TOKEN_2022_PROGRAM_ID,
    )


def _event(referral_fee=0, has_referral=False):
    return DammV2EvtSwap2(
        pool=bytes(32), trade_direction="A_TO_B",
        collect_fee_mode="BOTH_TOKEN", has_referral=has_referral,
        amount_0=100, amount_1=90, swap_mode="EXACT_IN",
        swap_result=DammV2SwapResult(
            included_fee_input_amount=95,
            excluded_fee_input_amount=90,
            amount_left=0, output_amount=90, next_sqrt_price=1 << 64,
            claiming_fee=2, protocol_fee=1, compounding_fee=1,
            referral_fee=referral_fee,
        ),
        included_transfer_fee_amount_in=100,
        included_transfer_fee_amount_out=90,
        excluded_transfer_fee_amount_out=90,
        current_timestamp=1_700_000_000,
        reserve_a_amount=1_000, reserve_b_amount=2_000,
    )


def _context(outer=0, path=(0,), event=None):
    association = DammV2SwapEventAssociation(
        status="MATCHED", instruction_index=outer,
        inner_instruction_index=1, cpi_path=path, stack_height=3,
        instruction=None, event_inner_instruction_index=5,
        event_cpi_path=path + (0,), event_stack_height=4,
        event=_event() if event is None else event,
    )
    return DammV2SwapTransferContext(association, _accounts())


def _transfer(source, destination, mint, amount, fee=None, decimals=6,
              outer=0, inner=2, path=(0, 0)):
    return SolanaTokenTransfer(
        program_id=TOKEN_2022_PROGRAM_ID,
        program_name="Token-2022",
        instruction_type="TRANSFER_CHECKED_WITH_FEE" if fee is not None else "TRANSFER_CHECKED",
        instruction_index=outer, inner_instruction_index=inner,
        stack_height=4, cpi_path=path,
        source_account=source, destination_account=destination,
        authority="authority", mint=mint, amount_raw=amount,
        decimals=decimals, execution_status="EXECUTED",
        source_format="compiled", fee_amount_raw=fee,
    )


def _evidence(context, input_transfer, output_transfer, referral=None):
    association = context.association
    return DammV2TransferEvidence(
        status="ATTRIBUTED",
        instruction_index=association.instruction_index,
        inner_instruction_index=association.inner_instruction_index,
        cpi_path=association.cpi_path,
        input_transfer=input_transfer,
        output_transfer=output_transfer,
        referral_transfer=referral,
        reason="fixture attribution",
        transfer_fee_review_required=True,
    )


def _deltas(values):
    rows = []
    for index, (account, mint, amount, decimals) in enumerate(values):
        rows.append(SolanaTokenAccountBalanceDelta(
            account_index=index, token_account=account, mint=mint,
            owner="owner", pre_amount_raw=1_000,
            post_amount_raw=1_000 + amount, delta_raw=amount,
            decimals=decimals,
        ))
    return SolanaTokenBalanceDeltaResult(tuple(rows), ())


def _reconcile(contexts, evidence, deltas, all_transfers=None):
    if all_transfers is None:
        all_transfers = []
        for item in evidence:
            all_transfers.extend(
                transfer for transfer in (
                    item.input_transfer, item.output_transfer, item.referral_transfer
                ) if transfer is not None
            )
    return reconcile_damm_v2_economic_batch(
        contexts, evidence, deltas, all_transfers
    )


class DammV2EconomicReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.context = _context()
        self.input = _transfer("user-a", "vault-a", "mint-a", 100, fee=5)
        self.output = _transfer("vault-b", "user-b", "mint-b", 90, fee=0)
        self.evidence = _evidence(self.context, self.input, self.output)

    def test_reconciles_gross_debits_and_net_credits_against_account_deltas(self):
        deltas = _deltas([
            ("user-a", "mint-a", -100, 6),
            ("vault-a", "mint-a", 95, 6),
            ("vault-b", "mint-b", -90, 6),
            ("user-b", "mint-b", 90, 6),
        ])
        result = _reconcile(
            [self.context], [self.evidence], deltas
        )
        self.assertEqual(result.status, "RECONCILED")
        self.assertEqual(result.operation_count, 1)
        self.assertEqual(len(result.expected_account_deltas), 4)

    def test_reconciles_legacy_token_2022_checked_using_event_gross_net_fields(self):
        input_transfer = _transfer(
            "user-a", "vault-a", "mint-a", 100, fee=None
        )
        output_transfer = _transfer(
            "vault-b", "user-b", "mint-b", 90, fee=None
        )
        evidence = _evidence(self.context, input_transfer, output_transfer)
        result = _reconcile(
            [self.context], [evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        self.assertEqual(result.status, "RECONCILED")


    def test_reconciles_wrapped_sol_input_funded_and_synced_before_swap(self):
        accounts = replace(
            self.context.accounts,
            input_mint=NATIVE_MINT,
            input_token_program=SPL_TOKEN_PROGRAM_ID,
        )
        event = self.context.association.event
        event = replace(
            event,
            included_transfer_fee_amount_in=100,
            swap_result=replace(event.swap_result, included_fee_input_amount=100),
        )
        association = replace(self.context.association, instruction_index=2, event=event)
        context = replace(self.context, association=association, accounts=accounts)
        input_transfer = SolanaTokenTransfer(
            program_id=SPL_TOKEN_PROGRAM_ID, program_name="SPL Token",
            instruction_type="TRANSFER_CHECKED", instruction_index=2,
            inner_instruction_index=2, stack_height=4, cpi_path=(0, 0),
            source_account="user-a", destination_account="vault-a",
            authority="authority", mint=NATIVE_MINT, amount_raw=100,
            decimals=9, execution_status="EXECUTED", source_format="compiled",
        )
        evidence = _evidence(context, input_transfer, self.output)
        raw = {
            "result": {
                "transaction": {
                    "message": {
                        "accountKeys": [
                            "wallet", "user-a",
                            "11111111111111111111111111111111",
                            SPL_TOKEN_PROGRAM_ID, "damm",
                        ],
                        "instructions": [
                            {"programIdIndex": 2, "accounts": [0, 1], "data": "3Bxs4dhy4yn7qUy5"},
                            {"programIdIndex": 3, "accounts": [1], "data": "J"},
                            {"programIdIndex": 4, "accounts": [0, 1], "data": "swap"},
                        ],
                    }
                },
                "meta": {
                    "preBalances": [10_000_000, 2_000_000, 1, 1, 1],
                    "postBalances": [9_999_900, 2_000_000, 1, 1, 1],
                },
            }
        }
        result = reconcile_damm_v2_economic_batch(
            [context], [evidence],
            _deltas([
                ("user-a", NATIVE_MINT, 0, 9),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ]),
            [input_transfer, self.output],
            raw_transaction=raw, monitored_wallet="wallet",
        )
        self.assertEqual(result.status, "RECONCILED")
        self.assertEqual(len(result.wrapped_sol_fundings), 1)
        row = next(x for x in result.expected_account_deltas if x.token_account == "user-a")
        self.assertEqual(row.expected_delta_raw, 0)

    def test_rejects_fee_amount_outside_transfer_amount(self):
        invalid_input = _transfer(
            "user-a", "vault-a", "mint-a", 100, fee=101
        )
        evidence = _evidence(self.context, invalid_input, self.output)
        result = _reconcile(
            [self.context], [evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("fee explícita inválida", result.reason)

    def test_rejects_event_output_gross_inconsistency(self):
        inconsistent_event = DammV2EvtSwap2(
            **{
                **self.context.association.event.__dict__,
                "swap_result": DammV2SwapResult(
                    **{
                        **self.context.association.event.swap_result.__dict__,
                        "output_amount": 89,
                    }
                ),
            }
        )
        context = _context(event=inconsistent_event)
        evidence = _evidence(context, self.input, self.output)
        result = _reconcile(
            [context], [evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("output_amount", result.reason)

    def test_rejects_net_credit_that_disagrees_with_explicit_transfer_fee(self):
        bad_input = _transfer("user-a", "vault-a", "mint-a", 100, fee=4)
        evidence = _evidence(self.context, bad_input, self.output)
        result = _reconcile(
            [self.context], [evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("crédito líquido", result.reason)

    def test_rejects_missing_or_incomplete_balance_snapshots(self):
        incomplete = SolanaTokenBalanceDeltaResult(
            (), (SolanaTokenBalanceDeltaIssue(None, "SNAPSHOTS_MISSING"),)
        )
        result = _reconcile(
            [self.context], [self.evidence], incomplete
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("SNAPSHOTS_MISSING", result.reason)

    def test_rejects_delta_mismatch(self):
        result = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 94, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("delta diverge", result.reason)

    def test_aggregates_sequential_swaps_sharing_the_same_token_accounts(self):
        second = _context(path=(1,))
        second_input = _transfer(
            "user-a", "vault-a", "mint-a", 100, fee=5, inner=3, path=(1, 0)
        )
        second_output = _transfer(
            "vault-b", "user-b", "mint-b", 90, fee=0, inner=4, path=(1, 0)
        )
        results = _reconcile(
            [self.context, second],
            [
                self.evidence,
                _evidence(second, second_input, second_output),
            ],
            _deltas([
                ("user-a", "mint-a", -200, 6),
                ("vault-a", "mint-a", 190, 6),
                ("vault-b", "mint-b", -180, 6),
                ("user-b", "mint-b", 180, 6),
            ]),
        )
        self.assertEqual(results.status, "RECONCILED")
        self.assertEqual(results.operation_count, 2)

    def test_requires_explicit_referral_fee_for_token_2022(self):
        context = _context(event=_event(referral_fee=5, has_referral=True))
        referral = _transfer(
            "vault-b", "referral", "mint-b", 5, fee=None, inner=3
        )
        evidence = _evidence(context, self.input, self.output, referral)
        result = _reconcile(
            [context], [evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -95, 6),
                ("user-b", "mint-b", 90, 6),
                ("referral", "mint-b", 5, 6),
            ])
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("não está explícita", result.reason)

    def test_reconciles_referral_transfer_with_explicit_token_2022_fee(self):
        context = _context(event=_event(referral_fee=5, has_referral=True))
        referral = _transfer(
            "vault-b", "referral", "mint-b", 5, fee=1, inner=3
        )
        evidence = _evidence(context, self.input, self.output, referral)
        result = _reconcile(
            [context], [evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -95, 6),
                ("user-b", "mint-b", 90, 6),
                ("referral", "mint-b", 4, 6),
            ])
        )
        self.assertEqual(result.status, "RECONCILED")

    def test_rejects_non_boolean_cpi_path_validity(self):
        invalid = SolanaTokenTransfer(
            **{**self.input.__dict__, "cpi_path_valid": 1}
        )
        evidence = _evidence(self.context, invalid, self.output)
        result = _reconcile(
            [self.context], [evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("proveniência CPI", result.reason)

    def test_rejects_duplicate_reference_in_transfer_inventory(self):
        result = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ]),
            all_transfers=[self.input, self.output, self.input],
        )
        self.assertEqual(result.status, "AMBIGUOUS")
        self.assertIn("referência duplicada", result.reason)

    def test_rejects_claimed_transfer_missing_from_complete_inventory(self):
        result = _reconcile(
            [self.context], [self.evidence],
            _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ]),
            all_transfers=[self.input],
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("não contém todas as transferências atribuídas", result.reason)

    def test_rejects_unattributed_transfer_touching_a_swap_account(self):
        unrelated = _transfer(
            "third-party", "user-a", "mint-a", 1, fee=0, inner=3
        )
        result = _reconcile(
            [self.context], [self.evidence],
            _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ]),
            all_transfers=[self.input, self.output, unrelated],
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("não atribuídas", result.reason)

    def test_rejects_duplicate_swap_identity_even_with_distinct_transfers(self):
        second_input = _transfer(
            "user-a", "vault-a", "mint-a", 100, fee=5, inner=3, path=(0, 1)
        )
        second_output = _transfer(
            "vault-b", "user-b", "mint-b", 90, fee=0, inner=4, path=(0, 2)
        )
        second_evidence = _evidence(
            self.context, second_input, second_output
        )
        result = _reconcile(
            [self.context, self.context],
            [self.evidence, second_evidence],
            _deltas([
                ("user-a", "mint-a", -200, 6),
                ("vault-a", "mint-a", 190, 6),
                ("vault-b", "mint-b", -180, 6),
                ("user-b", "mint-b", 180, 6),
            ]),
        )
        self.assertEqual(result.status, "AMBIGUOUS")
        self.assertIn("identidade de swap", result.reason)

    def test_rejects_transfer_reuse(self):
        result = _reconcile(
            [self.context, self.context],
            [self.evidence, self.evidence],
            _deltas([]),
            all_transfers=[self.input, self.output],
        )
        self.assertEqual(result.status, "AMBIGUOUS")
        self.assertIn("reutilizada", result.reason)


if __name__ == "__main__":
    unittest.main()
