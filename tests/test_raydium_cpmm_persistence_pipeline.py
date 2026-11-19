import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from smart_money_radar.domain.models import (
    ObservedTransaction,
    SwapClassification,
    SwapEvidence,
    SwapObservation,
    build_swap_operation_id,
)
from smart_money_radar.domain.normalization import NormalizedObservation
from smart_money_radar.domain.swap_bundle_builder import SwapDomainBundle
from smart_money_radar.domain.raydium_cpmm_persistence_pipeline import (
    process_raydium_cpmm_observation,
)
from smart_money_radar.storage.event_store import SQLiteEventStore


class RaydiumCpmmPersistencePipelineTests(unittest.TestCase):
    def setUp(self):
        self.store = SQLiteEventStore(":memory:")
        self.wallet = "wallet-pipeline"
        self.signature = "signature-pipeline"
        self.payload = {
            "meta": {"err": None},
            "transaction": {"message": {"accountKeys": [], "instructions": []}},
            "blockTime": 1794960000,
            "slot": 123,
        }
        self.timestamp = datetime(2026, 11, 18, tzinfo=timezone.utc)
        envelope = ObservedTransaction(
            chain="solana",
            wallet_address=self.wallet,
            signature=self.signature,
            observed_at=self.timestamp,
            raw_transaction=self.payload,
            parser_version="1",
            parse_status="no_events",
            slot=123,
            occurred_at=self.timestamp,
        )
        self.normalized = NormalizedObservation(
            transaction=envelope, token_deltas=(), activity_events=()
        )

    def tearDown(self):
        self.store.close()

    def _swap(self):
        return SimpleNamespace(
            instruction_index=0,
            inner_instruction_index=None,
            cpi_path=(0,),
        )

    def _bundle(self):
        operation_id = build_swap_operation_id(
            "solana", self.signature, 0, (0,)
        )
        observation = SwapObservation(
            operation_id=operation_id,
            chain="solana",
            wallet_address=self.wallet,
            signature=self.signature,
            input_mint="mint-in",
            output_mint="mint-out",
            input_amount=Decimal("1"),
            output_amount=Decimal("2"),
            observed_at=self.timestamp,
            parser_version="1",
        )
        classification = SwapClassification(
            operation_id=operation_id,
            side="UNKNOWN",
            confidence=Decimal("0"),
            reason="No configured reference mint.",
        )
        evidence = SwapEvidence(
            operation_id=operation_id,
            program_id="raydium-cpmm-program",
            venue="Raydium CPMM",
            instruction_index=0,
            cpi_path=(0,),
            evidence=("fixture-backed reconciliation",),
        )
        return SwapDomainBundle(observation, classification, evidence)

    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.normalize_transaction")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.decode_raydium_cpmm_swaps")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.decode_solana_token_transfers")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.decode_token_account_balance_deltas")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.reconcile_raydium_cpmm_swaps")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.build_swap_domain_bundles")
    def test_matched_swap_is_persisted_before_checkpoint(
        self, build, reconcile, deltas, transfers, decode, normalize
    ):
        normalize.return_value = self.normalized
        decode.return_value = [self._swap()]
        transfers.return_value = [object()]
        deltas.return_value = [object()]
        reconcile.return_value = [SimpleNamespace(
            swap=self._swap(), status="MATCHED",
            reason="All transfer and balance evidence reconciled.",
        )]
        build.return_value = [self._bundle()]

        result = process_raydium_cpmm_observation(
            self.store, self.payload, wallet_address=self.wallet,
            signature=self.signature,
        )

        self.assertEqual(result.status, "processed")
        self.assertEqual(result.saved_bundles, 1)
        self.assertTrue(result.checkpoint_advanced)
        self.assertTrue(self.store.has_processed_signature(self.wallet, self.signature))
        bundle = self._bundle()
        self.assertIsNotNone(self.store.get_swap_bundle(bundle.observation.operation_id))
        normalize.assert_called_once()
        attempts = self.store.get_swap_reconciliation_attempts(
            self.wallet, self.signature
        )
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["status"], "MATCHED")
        self.assertEqual(
            attempts[0]["reason"],
            "All transfer and balance evidence reconciled.",
        )

    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.normalize_transaction")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.decode_raydium_cpmm_swaps")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.decode_solana_token_transfers")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.decode_token_account_balance_deltas")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.reconcile_raydium_cpmm_swaps")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.build_swap_domain_bundles")
    def test_unresolved_swap_keeps_checkpoint_pending(
        self, build, reconcile, deltas, transfers, decode, normalize
    ):
        normalize.return_value = self.normalized
        decode.return_value = [self._swap()]
        transfers.return_value = [object()]
        deltas.return_value = [object()]
        reconcile.return_value = [SimpleNamespace(
            swap=self._swap(), status="INCOMPLETE",
            reason="Missing token-account delta.",
        )]
        build.return_value = []

        result = process_raydium_cpmm_observation(
            self.store, self.payload, wallet_address=self.wallet,
            signature=self.signature,
        )

        self.assertEqual(result.status, "pending_reconciliation")
        self.assertEqual(result.unresolved_swaps, 1)
        self.assertFalse(result.checkpoint_advanced)
        self.assertFalse(self.store.has_processed_signature(self.wallet, self.signature))
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
        attempts = self.store.get_swap_reconciliation_attempts(
            self.wallet, self.signature
        )
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["status"], "INCOMPLETE")
        self.assertEqual(attempts[0]["reason"], "Missing token-account delta.")

    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.normalize_transaction")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.decode_raydium_cpmm_swaps")
    def test_transaction_without_cpmm_swaps_advances_checkpoint(self, decode, normalize):
        normalize.return_value = self.normalized
        decode.return_value = []

        result = process_raydium_cpmm_observation(
            self.store, self.payload, wallet_address=self.wallet,
            signature=self.signature,
        )

        self.assertEqual(result.status, "no_cpmm_swaps")
        self.assertTrue(result.checkpoint_advanced)
        self.assertTrue(self.store.has_processed_signature(self.wallet, self.signature))

    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.normalize_transaction")
    def test_normalization_failure_archives_raw_payload_without_checkpoint(self, normalize):
        normalize.side_effect = ValueError("invalid normalized transaction")

        with self.assertRaisesRegex(ValueError, "invalid normalized transaction"):
            process_raydium_cpmm_observation(
                self.store, self.payload, wallet_address=self.wallet,
                signature=self.signature,
            )

        self.assertFalse(self.store.has_processed_signature(self.wallet, self.signature))
        self.assertIsNotNone(self.store.get_raw_transaction(self.wallet, self.signature))
        metadata = self.store.get_observation_metadata(self.wallet, self.signature)
        self.assertEqual(metadata["parse_status"], "parse_error")


    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.normalize_transaction")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.decode_raydium_cpmm_swaps")
    def test_reconstruction_failure_sets_parse_error_and_keeps_checkpoint(
        self, decode, normalize
    ):
        normalize.return_value = self.normalized
        decode.side_effect = ValueError("malformed CPMM instruction")

        with self.assertRaisesRegex(ValueError, "malformed CPMM instruction"):
            process_raydium_cpmm_observation(
                self.store, self.payload, wallet_address=self.wallet,
                signature=self.signature,
            )

        self.assertFalse(self.store.has_processed_signature(self.wallet, self.signature))
        metadata = self.store.get_observation_metadata(self.wallet, self.signature)
        self.assertEqual(metadata["parse_status"], "parse_error")
        self.assertEqual(metadata["parse_error"], "ValueError")

    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.normalize_transaction")
    def test_rejects_signature_mismatch_before_persistence(self, normalize):
        payload = {
            **self.payload,
            "transaction": {
                "signatures": ["another-signature"],
                "message": {"accountKeys": [], "instructions": []},
            },
        }
        with self.assertRaisesRegex(ValueError, "não corresponde"):
            process_raydium_cpmm_observation(
                self.store, payload, wallet_address=self.wallet,
                signature=self.signature,
            )
        normalize.assert_not_called()
        self.assertFalse(self.store.has_processed_signature(self.wallet, self.signature))


    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.normalize_transaction")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.decode_raydium_cpmm_swaps")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.decode_solana_token_transfers")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.decode_token_account_balance_deltas")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.reconcile_raydium_cpmm_swaps")
    @patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.build_swap_domain_bundles")
    def test_missing_reconciliation_result_keeps_checkpoint_pending(
        self, build, reconcile, deltas, transfers, decode, normalize
    ):
        normalize.return_value = self.normalized
        decode.return_value = [self._swap()]
        transfers.return_value = [object()]
        deltas.return_value = [object()]
        reconcile.return_value = []
        build.return_value = []

        result = process_raydium_cpmm_observation(
            self.store, self.payload, wallet_address=self.wallet,
            signature=self.signature,
        )

        self.assertEqual(result.status, "pending_reconciliation")
        self.assertEqual(result.unresolved_swaps, 1)
        self.assertFalse(result.checkpoint_advanced)
        self.assertFalse(self.store.has_processed_signature(self.wallet, self.signature))
        attempts = self.store.get_swap_reconciliation_attempts(
            self.wallet, self.signature
        )
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["status"], "UNRESOLVED")
        self.assertIn("não retornou resultado", attempts[0]["reason"])


if __name__ == "__main__":
    unittest.main()
