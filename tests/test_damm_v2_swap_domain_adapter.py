import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from smart_money_radar.data_sources.damm_v2_accounts import DammV2SwapAccounts
from smart_money_radar.data_sources.damm_v2_analyzer import DammV2SwapEventAssociation
from smart_money_radar.data_sources.damm_v2_decoder import (\n    METEORA_DAMM_V2_PROGRAM_ID, DammV2EvtSwap2, DammV2SwapResult,\n)
from smart_money_radar.data_sources.damm_v2_economic_reconciliation import (
    DammV2EconomicReconciliation,
)
from smart_money_radar.data_sources.damm_v2_swap_domain_adapter import (
    build_damm_v2_swap_domain_bundles,
)
from smart_money_radar.data_sources.damm_v2_transfer_analyzer import (
    DammV2SwapTransferContext, DammV2TransferEvidence,
)
from smart_money_radar.data_sources.solana_token_balance_delta_decoder import (
    SolanaTokenAccountBalanceDelta, SolanaTokenBalanceDeltaResult,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    TOKEN_2022_PROGRAM_ID, SolanaTokenTransfer,
)


def _context():
    accounts = DammV2SwapAccounts(
        pool_authority="authority", pool="pool",
        input_token_account="user-a", output_token_account="user-b",
        token_a_vault="vault-a", token_b_vault="vault-b",
        token_a_mint="mint-a", token_b_mint="mint-b", payer="payer",
        token_a_program=TOKEN_2022_PROGRAM_ID,
        token_b_program=TOKEN_2022_PROGRAM_ID,
        referral_token_account="referral", event_authority="event",
        program=METEORA_DAMM_V2_PROGRAM_ID, remaining_accounts=(),
        input_vault="vault-a", output_vault="vault-b",
        input_mint="mint-a", output_mint="mint-b",
        input_token_program=TOKEN_2022_PROGRAM_ID,
        output_token_program=TOKEN_2022_PROGRAM_ID,
    )
    event = DammV2EvtSwap2(
        pool=bytes(32), trade_direction="A_TO_B",
        collect_fee_mode="BOTH_TOKEN", has_referral=False,
        amount_0=100, amount_1=90, swap_mode="EXACT_IN",
        swap_result=DammV2SwapResult(
            included_fee_input_amount=95, excluded_fee_input_amount=90,
            amount_left=0, output_amount=90, next_sqrt_price=1 << 64,
            claiming_fee=2, protocol_fee=1, compounding_fee=1, referral_fee=0,
        ),
        included_transfer_fee_amount_in=100,
        included_transfer_fee_amount_out=90,
        excluded_transfer_fee_amount_out=90,
        current_timestamp=1_700_000_000,
        reserve_a_amount=1_000, reserve_b_amount=2_000,
    )
    association = DammV2SwapEventAssociation(
        status="MATCHED", instruction_index=2, inner_instruction_index=1,
        cpi_path=(0,), stack_height=3, instruction=None,
        event_inner_instruction_index=5, event_cpi_path=(0, 0),
        event_stack_height=4, event=event,
    )
    return DammV2SwapTransferContext(association, accounts)


def _transfer(source, destination, mint, amount, fee=None):
    return SolanaTokenTransfer(
        program_id=TOKEN_2022_PROGRAM_ID, program_name="Token-2022",
        instruction_type="TRANSFER_CHECKED_WITH_FEE" if fee is not None else "TRANSFER_CHECKED",
        instruction_index=2, inner_instruction_index=2, stack_height=4,
        cpi_path=(0, 0), source_account=source,
        destination_account=destination, authority="authority", mint=mint,
        amount_raw=amount, decimals=6, execution_status="EXECUTED",
        source_format="compiled", fee_amount_raw=fee,
    )


def _inputs(wallet_owner="wallet-1"):
    context = _context()
    input_transfer = _transfer("user-a", "vault-a", "mint-a", 100, 5)
    output_transfer = _transfer("vault-b", "user-b", "mint-b", 90, 0)
    evidence = DammV2TransferEvidence(
        status="ATTRIBUTED", instruction_index=2, inner_instruction_index=1,
        cpi_path=(0,), input_transfer=input_transfer,
        output_transfer=output_transfer, referral_transfer=None,
        reason="attributed", transfer_fee_review_required=False,
    )
    deltas = SolanaTokenBalanceDeltaResult((
        SolanaTokenAccountBalanceDelta(0, "user-a", "mint-a", wallet_owner, 1_000, 900, -100, 6),
        SolanaTokenAccountBalanceDelta(1, "vault-a", "mint-a", "pool-owner", 1_000, 1_095, 95, 6),
        SolanaTokenAccountBalanceDelta(2, "vault-b", "mint-b", "pool-owner", 2_000, 1_910, -90, 6),
        SolanaTokenAccountBalanceDelta(3, "user-b", "mint-b", wallet_owner, 500, 590, 90, 6),
    ), ())
    reconciliation = DammV2EconomicReconciliation("RECONCILED", 1, (), "ok")
    return context, evidence, deltas, reconciliation


class DammV2SwapDomainAdapterTests(unittest.TestCase):
    def test_builds_separate_domain_contracts_only_after_reconciliation(self):
        context, evidence, deltas, reconciliation = _inputs()
        bundles = build_damm_v2_swap_domain_bundles(
            contexts=[context], transfer_evidence=[evidence],
            balance_deltas=deltas, reconciliation=reconciliation,
            monitored_wallet="wallet-1", signature="signature-1",
            observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
            parser_version="smr-test",
        )
        self.assertEqual(len(bundles), 1)
        bundle = bundles[0]
        self.assertEqual(bundle.observation.input_amount, Decimal("0.000100"))
        self.assertEqual(bundle.observation.output_amount, Decimal("0.000090"))
        self.assertEqual(bundle.observation.wallet_address, "wallet-1")
        self.assertEqual(bundle.classification.side, "UNKNOWN")
        self.assertEqual(bundle.classification.confidence, Decimal("0"))
        self.assertEqual(bundle.evidence.venue, "Meteora DAMM v2")
        self.assertEqual(bundle.observation.operation_id, bundle.classification.operation_id)
        self.assertEqual(bundle.observation.operation_id, bundle.evidence.operation_id)

    def test_rejects_non_reconciled_batch(self):
        context, evidence, deltas, _ = _inputs()
        result = DammV2EconomicReconciliation("INCOMPLETE", 1, (), "delta mismatch")
        with self.assertRaisesRegex(ValueError, "RECONCILED"):
            build_damm_v2_swap_domain_bundles(
                contexts=[context], transfer_evidence=[evidence],
                balance_deltas=deltas, reconciliation=result,
                monitored_wallet="wallet-1", signature="signature-1",
                observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
                parser_version="smr-test",
            )

    def test_rejects_wallet_owner_mismatch(self):
        context, evidence, deltas, reconciliation = _inputs(wallet_owner="other-wallet")
        with self.assertRaisesRegex(ValueError, "propriedade"):
            build_damm_v2_swap_domain_bundles(
                contexts=[context], transfer_evidence=[evidence],
                balance_deltas=deltas, reconciliation=reconciliation,
                monitored_wallet="wallet-1", signature="signature-1",
                observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
                parser_version="smr-test",
            )


    def test_rejects_untrusted_transfer_cpi_path(self):
        context, evidence, deltas, reconciliation = _inputs()
        invalid_transfer = replace(evidence.input_transfer, cpi_path_valid=False)
        invalid_evidence = replace(evidence, input_transfer=invalid_transfer)
        with self.assertRaisesRegex(ValueError, "proveniência CPI"):
            build_damm_v2_swap_domain_bundles(
                contexts=[context], transfer_evidence=[invalid_evidence],
                balance_deltas=deltas, reconciliation=reconciliation,
                monitored_wallet="wallet-1", signature="signature-1",
                observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
                parser_version="smr-test",
            )


    def test_adapter_bundle_round_trips_through_existing_sqlite_event_store(self):
        context, evidence, deltas, reconciliation = _inputs()
        bundles = build_damm_v2_swap_domain_bundles(
            contexts=[context], transfer_evidence=[evidence],
            balance_deltas=deltas, reconciliation=reconciliation,
            monitored_wallet="wallet-1", signature="signature-1",
            observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
            parser_version="smr-test",
        )
        store = SQLiteEventStore(":memory:")
        try:
            store.save_observation(
                "wallet-1", "signature-1", {"meta": {"err": None}}, [],
                parse_status="parsed", parser_version="smr-test",
            )
            bundle = bundles[0]
            self.assertTrue(store.save_swap_bundle(
                bundle.observation, bundle.classification, bundle.evidence
            ))
            persisted = store.get_swap_bundle(bundle.observation.operation_id)
            self.assertEqual(persisted["observation"], bundle.observation)
            self.assertEqual(persisted["classification"], bundle.classification)
            self.assertEqual(persisted["evidence"], bundle.evidence)
        finally:
            store.close()


    def test_rejects_event_cpi_path_not_descending_from_swap(self):
        context, evidence, deltas, reconciliation = _inputs()
        invalid_association = replace(
            context.association, event_cpi_path=(9, 9)
        )
        invalid_context = replace(context, association=invalid_association)
        with self.assertRaisesRegex(ValueError, "identidade CPI"):
            build_damm_v2_swap_domain_bundles(
                contexts=[invalid_context], transfer_evidence=[evidence],
                balance_deltas=deltas, reconciliation=reconciliation,
                monitored_wallet="wallet-1", signature="signature-1",
                observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
                parser_version="smr-test",
            )


if __name__ == "__main__":
    unittest.main()
