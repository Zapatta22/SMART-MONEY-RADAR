import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from smart_money_radar.data_sources.raydium_cpmm_accounts import RaydiumCpmmAccounts
from smart_money_radar.data_sources.raydium_cpmm_analyzer import RaydiumCpmmDecodedSwap
from smart_money_radar.data_sources.raydium_cpmm_decoder import RaydiumCpmmSwapBaseInput
from smart_money_radar.data_sources.raydium_cpmm_transfer_reconciliation import (
    RaydiumCpmmSwapReconciliation,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID,
    SolanaTokenTransfer,
)
from smart_money_radar.domain.models import build_swap_operation_id
from smart_money_radar.domain.swap_bundle_builder import build_swap_domain_bundles


WALLET = "wallet-1"
INPUT_MINT = "quote-mint"
OUTPUT_MINT = "asset-mint"
OBSERVED_AT = datetime(2026, 11, 18, tzinfo=timezone.utc)


def _matched():
    accounts = RaydiumCpmmAccounts(
        payer="fee-payer",
        authority="pool-authority",
        amm_config="amm-config",
        pool_state="pool-state",
        input_token_account="user-input",
        output_token_account="user-output",
        input_vault="input-vault",
        output_vault="output-vault",
        input_token_program=SPL_TOKEN_PROGRAM_ID,
        output_token_program=SPL_TOKEN_PROGRAM_ID,
        input_token_mint=INPUT_MINT,
        output_token_mint=OUTPUT_MINT,
        observation_state="observation",
    )
    swap = RaydiumCpmmDecodedSwap(
        instruction_index=4,
        instruction=RaydiumCpmmSwapBaseInput(999999, 1),
        accounts=accounts,
        cpi_path=(2, 1),
        stack_height=4,
        inner_instruction_index=7,
    )
    input_transfer = SolanaTokenTransfer(
        program_id=SPL_TOKEN_PROGRAM_ID,
        program_name="SPL Token",
        instruction_type="TRANSFER_CHECKED",
        instruction_index=4,
        inner_instruction_index=8,
        stack_height=5,
        cpi_path=(2, 1, 0),
        source_account="user-input",
        destination_account="input-vault",
        authority="wallet-1",
        mint=INPUT_MINT,
        amount_raw=1250000,
        decimals=6,
        execution_status="EXECUTED",
        source_format="compiled",
    )
    output_transfer = SolanaTokenTransfer(
        program_id=SPL_TOKEN_PROGRAM_ID,
        program_name="SPL Token",
        instruction_type="TRANSFER_CHECKED",
        instruction_index=4,
        inner_instruction_index=9,
        stack_height=5,
        cpi_path=(2, 1, 1),
        source_account="output-vault",
        destination_account="user-output",
        authority="pool-authority",
        mint=OUTPUT_MINT,
        amount_raw=900000,
        decimals=6,
        execution_status="EXECUTED",
        source_format="compiled",
    )
    return RaydiumCpmmSwapReconciliation(
        swap=swap,
        status="MATCHED",
        reason="test evidence",
        wallet_address=WALLET,
        input_amount_raw=1250000,
        output_amount_raw=900000,
        input_decimals=6,
        output_decimals=6,
        input_transfer=input_transfer,
        output_transfer=output_transfer,
    )


class SwapDomainBundleBuilderTests(unittest.TestCase):
    def _build(self, matched=None, reference_mints=()):
        return build_swap_domain_bundles(
            [matched or _matched()],
            chain="solana",
            signature="signature-1",
            monitored_wallet=WALLET,
            observed_at=OBSERVED_AT,
            parser_version="smr-test",
            reference_mints=reference_mints,
        )

    def test_builds_exact_decimal_amounts_and_deterministic_operation_id(self):
        bundle = self._build(reference_mints=[INPUT_MINT])[0]
        self.assertEqual(bundle.observation.input_amount, Decimal("1.25"))
        self.assertEqual(bundle.observation.output_amount, Decimal("0.9"))
        self.assertEqual(
            bundle.observation.operation_id,
            build_swap_operation_id("solana", "signature-1", 4, (2, 1)),
        )
        self.assertEqual(bundle.observation.wallet_address, WALLET)
        self.assertEqual(bundle.observation.observed_at, OBSERVED_AT)

    def test_classifies_buy_only_when_input_is_explicit_reference_mint(self):
        bundle = self._build(reference_mints=[INPUT_MINT])[0]
        self.assertEqual(bundle.classification.side, "BUY")
        self.assertEqual(bundle.classification.confidence, Decimal("1"))
        self.assertEqual(bundle.classification.operation_id, bundle.observation.operation_id)

    def test_classifies_sell_only_when_output_is_explicit_reference_mint(self):
        bundle = self._build(reference_mints=[OUTPUT_MINT])[0]
        self.assertEqual(bundle.classification.side, "SELL")

    def test_keeps_unknown_when_no_reference_mint_is_configured(self):
        bundle = self._build()[0]
        self.assertEqual(bundle.classification.side, "UNKNOWN")
        self.assertEqual(bundle.classification.confidence, Decimal("0"))

    def test_keeps_unknown_when_both_sides_are_reference_mints(self):
        bundle = self._build(reference_mints=[INPUT_MINT, OUTPUT_MINT])[0]
        self.assertEqual(bundle.classification.side, "UNKNOWN")

    def test_builds_rayidum_evidence_with_instruction_and_cpi_identity(self):
        bundle = self._build()[0]
        self.assertEqual(bundle.evidence.venue, "Raydium CPMM")
        self.assertEqual(bundle.evidence.instruction_index, 4)
        self.assertEqual(bundle.evidence.cpi_path, (2, 1))
        self.assertTrue(any(item.startswith("input_transfer:4:8") for item in bundle.evidence.evidence))
        self.assertTrue(any(item.startswith("output_transfer:4:9") for item in bundle.evidence.evidence))

    def test_ignores_ambiguous_and_incomplete_reconciliations(self):
        matched = _matched()
        ambiguous = RaydiumCpmmSwapReconciliation(
            swap=matched.swap, status="AMBIGUOUS", reason="not unique"
        )
        incomplete = RaydiumCpmmSwapReconciliation(
            swap=matched.swap, status="INCOMPLETE", reason="missing transfer"
        )
        result = build_swap_domain_bundles(
            [ambiguous, incomplete],
            chain="solana",
            signature="signature-1",
            monitored_wallet=WALLET,
            observed_at=OBSERVED_AT,
            parser_version="smr-test",
        )
        self.assertEqual(result, [])

    def test_rejects_wallet_mismatch_in_matched_reconciliation(self):
        matched = _matched()
        mismatched = RaydiumCpmmSwapReconciliation(
            swap=matched.swap, status="MATCHED", reason="test",
            wallet_address="other-wallet",
            input_amount_raw=matched.input_amount_raw,
            output_amount_raw=matched.output_amount_raw,
            input_decimals=matched.input_decimals,
            output_decimals=matched.output_decimals,
            input_transfer=matched.input_transfer,
            output_transfer=matched.output_transfer,
        )
        with self.assertRaisesRegex(ValueError, "não pertence"):
            self._build(matched=mismatched)

    def test_rejects_matched_result_missing_amount_evidence(self):
        matched = _matched()
        incomplete = RaydiumCpmmSwapReconciliation(
            swap=matched.swap, status="MATCHED", reason="invalid test",
            wallet_address=WALLET,
        )
        with self.assertRaisesRegex(ValueError, "sem quantidades"):
            self._build(matched=incomplete)

    def test_rejects_matched_result_when_amount_or_transfer_identity_disagrees(self):
        matched = _matched()
        wrong_amount = replace(matched, input_amount_raw=matched.input_amount_raw + 1)
        with self.assertRaisesRegex(ValueError, "Quantidade de entrada"):
            self._build(matched=wrong_amount)

        wrong_accounts = replace(
            matched,
            input_transfer=replace(matched.input_transfer, destination_account="other-vault"),
        )
        with self.assertRaisesRegex(ValueError, "Contas da transferência de entrada"):
            self._build(matched=wrong_accounts)

        wrong_cpi = replace(
            matched,
            output_transfer=replace(matched.output_transfer, cpi_path=(9, 9)),
        )
        with self.assertRaisesRegex(ValueError, "descendente do CPI"):
            self._build(matched=wrong_cpi)

    def test_rejects_duplicate_operation_ids(self):
        with self.assertRaisesRegex(ValueError, "operation_id duplicado"):
            build_swap_domain_bundles(
                [_matched(), _matched()],
                chain="solana",
                signature="signature-1",
                monitored_wallet=WALLET,
                observed_at=OBSERVED_AT,
                parser_version="smr-test",
            )

    def test_requires_domain_metadata(self):
        with self.assertRaisesRegex(ValueError, "obrigatórios"):
            build_swap_domain_bundles(
                [_matched()],
                chain="",
                signature="signature-1",
                monitored_wallet=WALLET,
                observed_at=OBSERVED_AT,
                parser_version="smr-test",
            )

    def test_rejects_invalid_reference_mint(self):
        with self.assertRaisesRegex(ValueError, "reference_mints"):
            self._build(reference_mints=[INPUT_MINT, ""])


if __name__ == "__main__":
    unittest.main()
