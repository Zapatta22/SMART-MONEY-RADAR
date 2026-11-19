import unittest

from smart_money_radar.data_sources.damm_v2_accounts import DammV2SwapAccounts
from smart_money_radar.data_sources.damm_v2_analyzer import DammV2SwapEventAssociation
from smart_money_radar.data_sources.damm_v2_decoder import DammV2EvtSwap2, DammV2SwapResult
from smart_money_radar.data_sources.damm_v2_economic_reconciliation import (
    DammV2ExpectedWithheldFeeDelta,
    DammV2MintFeeConfigSnapshot,
    DammV2WithheldFeeSnapshot,
    reconcile_damm_v2_economic_batch,
    verify_damm_v2_mint_fee_config,
    verify_damm_v2_withheld_fee_deltas,
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
from smart_money_radar.data_sources.token2022_transfer_fee_state import (
    TransferFeeConfigState,
    TransferFeeRate,
    decode_transfer_fee_amount_delta,
)


WALLET = "wallet"


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


def _event(referral_fee=0, has_referral=False, excluded_output=90):
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
        excluded_transfer_fee_amount_out=excluded_output,
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


def _withheld_delta(pre, post):
    def account_data(amount):
        base = bytearray(165)
        base[108] = 1
        return bytes(base) + bytes([2]) + (2).to_bytes(2, "little") + (8).to_bytes(2, "little") + amount.to_bytes(8, "little")
    return decode_transfer_fee_amount_delta(account_data(pre), account_data(post))



def _mint_fee_snapshots(input_bps=500, input_max_fee=100, input_epoch=10):
    state = TransferFeeConfigState(
        withheld_amount=0,
        older_transfer_fee=TransferFeeRate(
            epoch=0, maximum_fee=input_max_fee, basis_points=input_bps
        ),
        newer_transfer_fee=TransferFeeRate(
            epoch=input_epoch, maximum_fee=input_max_fee, basis_points=input_bps
        ),
        extension_types=(1,),
    )
    return [
        DammV2MintFeeConfigSnapshot(
            mint="mint-a", transfer_instruction_index=0,
            transfer_inner_instruction_index=2, config_state=state,
            transaction_epoch=input_epoch, transaction_slot=123,
            transaction_order=50, pre_snapshot_order=49,
            mint_state_unchanged_before_transfer=True,
            source="ordered-mint-prestate-fixture", pre_state_ref="mint-a-pre",
        ),
        DammV2MintFeeConfigSnapshot(
            mint="mint-b", transfer_instruction_index=0,
            transfer_inner_instruction_index=2, config_state=None,
            transaction_epoch=input_epoch, transaction_slot=123,
            transaction_order=50, pre_snapshot_order=49,
            mint_state_unchanged_before_transfer=True,
            source="ordered-mint-prestate-fixture", pre_state_ref="mint-b-pre",
        ),
    ]


def _deltas(values):
    rows = []
    for index, (account, mint, amount, decimals) in enumerate(values):
        owner = {
            "user-a": WALLET,
            "user-b": WALLET,
            "vault-a": "authority",
            "vault-b": "authority",
        }.get(account, "referral-owner")
        rows.append(SolanaTokenAccountBalanceDelta(
            account_index=index, token_account=account, mint=mint,
            owner=owner, pre_amount_raw=1_000,
            post_amount_raw=1_000 + amount, delta_raw=amount,
            decimals=decimals,
        ))
    return SolanaTokenBalanceDeltaResult(tuple(rows), ())


def _reconcile(contexts, evidence, deltas, all_transfers=None, **kwargs):
    if all_transfers is None:
        all_transfers = []
        for item in evidence:
            all_transfers.extend(
                transfer for transfer in (
                    item.input_transfer, item.output_transfer, item.referral_transfer
                ) if transfer is not None
            )
    return reconcile_damm_v2_economic_batch(
        contexts, evidence, deltas, all_transfers,
        monitored_wallet=WALLET,
        **kwargs,
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
        self.assertIn("exige epoch/slot/ordem", result.reason)

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

    def test_rejects_transfer_reuse(self):
        result = _reconcile(
            [self.context, self.context],
            [self.evidence, self.evidence],
            _deltas([]),
            all_transfers=[self.input, self.output],
        )
        self.assertEqual(result.status, "AMBIGUOUS")
        self.assertIn("reutilizada", result.reason)



    def test_requires_monitored_wallet_owner_for_user_token_accounts(self):
        deltas = _deltas([
            ("user-a", "mint-a", -100, 6),
            ("vault-a", "mint-a", 95, 6),
            ("vault-b", "mint-b", -90, 6),
            ("user-b", "mint-b", 90, 6),
        ])
        rows = list(deltas.deltas)
        rows[0] = SolanaTokenAccountBalanceDelta(
            account_index=rows[0].account_index,
            token_account=rows[0].token_account,
            mint=rows[0].mint,
            owner="different-wallet",
            pre_amount_raw=rows[0].pre_amount_raw,
            post_amount_raw=rows[0].post_amount_raw,
            delta_raw=rows[0].delta_raw,
            decimals=rows[0].decimals,
        )
        result = _reconcile(
            [self.context], [self.evidence],
            SolanaTokenBalanceDeltaResult(tuple(rows), ()),
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("owner diverge", result.reason)

    def test_requires_pool_authority_to_own_both_vaults(self):
        deltas = _deltas([
            ("user-a", "mint-a", -100, 6),
            ("vault-a", "mint-a", 95, 6),
            ("vault-b", "mint-b", -90, 6),
            ("user-b", "mint-b", 90, 6),
        ])
        rows = list(deltas.deltas)
        rows[1] = SolanaTokenAccountBalanceDelta(
            account_index=rows[1].account_index,
            token_account=rows[1].token_account,
            mint=rows[1].mint,
            owner="wrong-pool-authority",
            pre_amount_raw=rows[1].pre_amount_raw,
            post_amount_raw=rows[1].post_amount_raw,
            delta_raw=rows[1].delta_raw,
            decimals=rows[1].decimals,
        )
        result = _reconcile(
            [self.context], [self.evidence],
            SolanaTokenBalanceDeltaResult(tuple(rows), ()),
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("owner diverge", result.reason)

    def test_exposes_expected_withheld_fee_without_claiming_state_verification(self):
        result = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        self.assertEqual(result.status, "RECONCILED")
        self.assertEqual(result.withheld_fee_status, "EXPECTED_NOT_VERIFIED")
        self.assertEqual(
            result.expected_withheld_fee_deltas,
            (
                DammV2ExpectedWithheldFeeDelta(
                    token_account="vault-a",
                    mint="mint-a",
                    expected_withheld_delta_raw=5,
                ),
            ),
        )

    def test_rejects_empty_monitored_wallet(self):
        with self.assertRaisesRegex(ValueError, "monitored_wallet"):
            reconcile_damm_v2_economic_batch(
                [self.context], [self.evidence],
                _deltas([
                    ("user-a", "mint-a", -100, 6),
                    ("vault-a", "mint-a", 95, 6),
                    ("vault-b", "mint-b", -90, 6),
                    ("user-b", "mint-b", 90, 6),
                ]),
                [self.input, self.output],
                monitored_wallet="",
            )


    def test_verifies_withheld_tlv_delta_with_transaction_bound_snapshots(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        snapshot = DammV2WithheldFeeSnapshot(
            token_account="vault-a", mint="mint-a",
            decoded_delta=_withheld_delta(10, 15),
            transaction_signature="signature-1", transaction_slot=123,
            transaction_order=50, pre_snapshot_order=49, post_snapshot_order=51,
            source="ordered-account-snapshot-fixture",
            pre_state_ref="pre-state-hash", post_state_ref="post-state-hash",
        )
        result = verify_damm_v2_withheld_fee_deltas(
            base, [snapshot], transaction_signature="signature-1",
            transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "RECONCILED")
        self.assertEqual(result.withheld_fee_status, "VERIFIED")

    def test_withheld_tlv_mismatch_fails_closed(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        snapshot = DammV2WithheldFeeSnapshot(
            token_account="vault-a", mint="mint-a",
            decoded_delta=_withheld_delta(10, 14),
            transaction_signature="signature-1", transaction_slot=123,
            transaction_order=50, pre_snapshot_order=49, post_snapshot_order=51,
            source="ordered-account-snapshot-fixture",
            pre_state_ref="pre-state-hash", post_state_ref="post-state-hash",
        )
        result = verify_damm_v2_withheld_fee_deltas(
            base, [snapshot], transaction_signature="signature-1",
            transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("withheld diverge", result.reason)

    def test_withheld_verification_requires_snapshot_for_each_fee_account(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        result = verify_damm_v2_withheld_fee_deltas(
            base, [], transaction_signature="signature-1",
            transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("snapshot withheld ausente", result.reason)

    def test_withheld_verification_rejects_wrong_transaction_signature(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        snapshot = DammV2WithheldFeeSnapshot(
            token_account="vault-a", mint="mint-a",
            decoded_delta=_withheld_delta(10, 15),
            transaction_signature="other-signature", transaction_slot=123,
            transaction_order=50, pre_snapshot_order=49, post_snapshot_order=51,
            source="ordered-account-snapshot-fixture",
            pre_state_ref="pre-state-hash", post_state_ref="post-state-hash",
        )
        result = verify_damm_v2_withheld_fee_deltas(
            base, [snapshot], transaction_signature="signature-1",
            transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("assinatura do snapshot diverge", result.reason)

    def test_withheld_verification_requires_pre_transaction_and_post_transaction_order(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        snapshot = DammV2WithheldFeeSnapshot(
            token_account="vault-a", mint="mint-a",
            decoded_delta=_withheld_delta(10, 15),
            transaction_signature="signature-1", transaction_slot=123,
            transaction_order=50, pre_snapshot_order=50, post_snapshot_order=51,
            source="ordered-account-snapshot-fixture",
            pre_state_ref="pre-state-hash", post_state_ref="post-state-hash",
        )
        result = verify_damm_v2_withheld_fee_deltas(
            base, [snapshot], transaction_signature="signature-1",
            transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("pre < transação < post", result.reason)

    def test_withheld_verification_rejects_duplicate_account_snapshots(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        snapshot = DammV2WithheldFeeSnapshot(
            token_account="vault-a", mint="mint-a",
            decoded_delta=_withheld_delta(10, 15),
            transaction_signature="signature-1", transaction_slot=123,
            transaction_order=50, pre_snapshot_order=49, post_snapshot_order=51,
            source="ordered-account-snapshot-fixture",
            pre_state_ref="pre-state-hash", post_state_ref="post-state-hash",
        )
        result = verify_damm_v2_withheld_fee_deltas(
            base, [snapshot, snapshot], transaction_signature="signature-1",
            transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "AMBIGUOUS")
        self.assertIn("duplicado", result.reason)


    def test_verifies_token2022_fees_against_historical_mint_config_and_epoch(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        result = verify_damm_v2_mint_fee_config(
            base, _mint_fee_snapshots(),
            transaction_epoch=10, transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "RECONCILED")
        self.assertEqual(result.mint_fee_config_status, "VERIFIED")

    def test_mint_fee_config_mismatch_fails_closed(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        result = verify_damm_v2_mint_fee_config(
            base, _mint_fee_snapshots(input_bps=400),
            transaction_epoch=10, transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("transfer fee diverge", result.reason)

    def test_mint_fee_config_requires_snapshot_for_each_token2022_mint(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        result = verify_damm_v2_mint_fee_config(
            base, _mint_fee_snapshots()[:1],
            transaction_epoch=10, transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("snapshot histórico de mint ausente", result.reason)

    def test_mint_fee_config_requires_prestate_before_transaction(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        snapshots = _mint_fee_snapshots()
        snapshots[0] = DammV2MintFeeConfigSnapshot(
            mint="mint-a", transfer_instruction_index=0,
            transfer_inner_instruction_index=2, config_state=snapshots[0].config_state,
            transaction_epoch=10, transaction_slot=123,
            transaction_order=50, pre_snapshot_order=50,
            mint_state_unchanged_before_transfer=True,
            source="ordered-mint-prestate-fixture", pre_state_ref="mint-a-pre",
        )
        result = verify_damm_v2_mint_fee_config(
            base, snapshots,
            transaction_epoch=10, transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("prestate do mint não antecede", result.reason)

    def test_mint_fee_config_rejects_duplicate_mint_snapshots(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        snapshots = _mint_fee_snapshots()
        result = verify_damm_v2_mint_fee_config(
            base, snapshots + [snapshots[0]],
            transaction_epoch=10, transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "AMBIGUOUS")
        self.assertIn("duplicado", result.reason)

    def test_mint_fee_config_selects_older_rate_before_newer_epoch(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        old_state = TransferFeeConfigState(
            withheld_amount=0,
            older_transfer_fee=TransferFeeRate(epoch=0, maximum_fee=100, basis_points=500),
            newer_transfer_fee=TransferFeeRate(epoch=20, maximum_fee=100, basis_points=250),
            extension_types=(1,),
        )
        snapshots = _mint_fee_snapshots()
        snapshots[0] = DammV2MintFeeConfigSnapshot(
            mint="mint-a", transfer_instruction_index=0,
            transfer_inner_instruction_index=2, config_state=old_state,
            transaction_epoch=10, transaction_slot=123,
            transaction_order=50, pre_snapshot_order=49,
            mint_state_unchanged_before_transfer=True,
            source="ordered-mint-prestate-fixture", pre_state_ref="mint-a-pre",
        )
        result = verify_damm_v2_mint_fee_config(
            base, snapshots,
            transaction_epoch=10, transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "RECONCILED")
        self.assertEqual(result.mint_fee_config_status, "VERIFIED")


    def test_mint_fee_config_fails_if_mint_changed_before_transfer(self):
        base = _reconcile(
            [self.context], [self.evidence], _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -90, 6),
                ("user-b", "mint-b", 90, 6),
            ])
        )
        snapshots = _mint_fee_snapshots()
        snapshots[0] = DammV2MintFeeConfigSnapshot(
            mint="mint-a", transfer_instruction_index=0,
            transfer_inner_instruction_index=2,
            config_state=snapshots[0].config_state,
            transaction_epoch=10, transaction_slot=123,
            transaction_order=50, pre_snapshot_order=49,
            mint_state_unchanged_before_transfer=False,
            source="ordered-mint-prestate-fixture", pre_state_ref="mint-a-pre",
        )
        result = verify_damm_v2_mint_fee_config(
            base, snapshots,
            transaction_epoch=10, transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("pode ter mudado antes", result.reason)


    def test_reconciles_token2022_standard_referral_using_historical_mint_prestate(self):
        event = _event(referral_fee=5, has_referral=True, excluded_output=81)
        context = _context(event=event)
        input_transfer = _transfer(
            "user-a", "vault-a", "mint-a", 100, fee=None, inner=2
        )
        output_transfer = _transfer(
            "vault-b", "user-b", "mint-b", 90, fee=None, inner=2
        )
        referral_transfer = _transfer(
            "vault-b", "referral", "mint-b", 5, fee=None, inner=3
        )
        evidence = _evidence(
            context, input_transfer, output_transfer, referral_transfer
        )
        mint_a = TransferFeeConfigState(
            withheld_amount=0,
            older_transfer_fee=TransferFeeRate(epoch=0, maximum_fee=100, basis_points=500),
            newer_transfer_fee=TransferFeeRate(epoch=10, maximum_fee=100, basis_points=500),
            extension_types=(1,),
        )
        mint_b = TransferFeeConfigState(
            withheld_amount=0,
            older_transfer_fee=TransferFeeRate(epoch=0, maximum_fee=100, basis_points=1_000),
            newer_transfer_fee=TransferFeeRate(epoch=10, maximum_fee=100, basis_points=1_000),
            extension_types=(1,),
        )
        snapshots = [
            DammV2MintFeeConfigSnapshot(
                mint="mint-a", transfer_instruction_index=0,
                transfer_inner_instruction_index=2, config_state=mint_a,
                transaction_epoch=10, transaction_slot=123,
                transaction_order=50, pre_snapshot_order=49,
                mint_state_unchanged_before_transfer=True,
                source="ordered-mint-prestate-fixture", pre_state_ref="mint-a-pre",
            ),
            DammV2MintFeeConfigSnapshot(
                mint="mint-b", transfer_instruction_index=0,
                transfer_inner_instruction_index=2, config_state=mint_b,
                transaction_epoch=10, transaction_slot=123,
                transaction_order=50, pre_snapshot_order=49,
                mint_state_unchanged_before_transfer=True,
                source="ordered-mint-prestate-fixture", pre_state_ref="mint-b-output-pre",
            ),
            DammV2MintFeeConfigSnapshot(
                mint="mint-b", transfer_instruction_index=0,
                transfer_inner_instruction_index=3, config_state=mint_b,
                transaction_epoch=10, transaction_slot=123,
                transaction_order=50, pre_snapshot_order=49,
                mint_state_unchanged_before_transfer=True,
                source="ordered-mint-prestate-fixture", pre_state_ref="mint-b-referral-pre",
            ),
        ]
        result = _reconcile(
            [context], [evidence],
            _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -95, 6),
                ("user-b", "mint-b", 81, 6),
                ("referral", "mint-b", 4, 6),
            ]),
            [input_transfer, output_transfer, referral_transfer],
            mint_fee_snapshots=snapshots,
            transaction_epoch=10, transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(result.status, "RECONCILED")
        self.assertEqual(
            [item.expected_fee_raw for item in result.expected_transfer_fees],
            [5, 9, 1],
        )
        self.assertEqual(
            [item.fee_source for item in result.expected_transfer_fees],
            ["EVT_SWAP2_NET", "EVT_SWAP2_NET", "MINT_PRESTATE"],
        )
        verified = verify_damm_v2_mint_fee_config(
            result, snapshots,
            transaction_epoch=10, transaction_slot=123, transaction_order=50,
        )
        self.assertEqual(verified.status, "RECONCILED")
        self.assertEqual(verified.mint_fee_config_status, "VERIFIED")

    def test_token2022_standard_referral_without_mint_prestate_fails_closed(self):
        event = _event(referral_fee=5, has_referral=True, excluded_output=81)
        context = _context(event=event)
        input_transfer = _transfer("user-a", "vault-a", "mint-a", 100, fee=None, inner=2)
        output_transfer = _transfer("vault-b", "user-b", "mint-b", 90, fee=None, inner=2)
        referral_transfer = _transfer("vault-b", "referral", "mint-b", 5, fee=None, inner=3)
        evidence = _evidence(context, input_transfer, output_transfer, referral_transfer)
        result = _reconcile(
            [context], [evidence],
            _deltas([
                ("user-a", "mint-a", -100, 6),
                ("vault-a", "mint-a", 95, 6),
                ("vault-b", "mint-b", -95, 6),
                ("user-b", "mint-b", 81, 6),
                ("referral", "mint-b", 4, 6),
            ]),
            [input_transfer, output_transfer, referral_transfer],
        )
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("exige epoch/slot/ordem", result.reason)

if __name__ == "__main__":
    unittest.main()
