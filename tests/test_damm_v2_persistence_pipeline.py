import unittest

from smart_money_radar.domain.damm_v2_persistence_pipeline import (
    process_damm_v2_observation,
)
from smart_money_radar.storage.event_store import SQLiteEventStore

from smart_money_radar.data_sources.damm_v2_decoder import (
    EVENT_CPI_TAG,
    EVT_SWAP2_DISCRIMINATOR,
    METEORA_DAMM_V2_PROGRAM_ID,
    SWAP_DISCRIMINATOR,
    SWAP2_DISCRIMINATOR,
)

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data):
    zeros = len(data) - len(data.lstrip(bytes([0])))
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = ALPHABET[remainder] + encoded
    return "1" * zeros + (encoded or ("" if zeros else "1"))


def _u64(value):
    return value.to_bytes(8, "little")


def _damm_swap_event_raw():
    swap_data = SWAP_DISCRIMINATOR + _u64(100) + _u64(90)
    event_body = (
        bytes(32) + bytes((0, 0, 0))
        + _u64(100) + _u64(90) + bytes((0,))
        + _u64(100) + _u64(0) + _u64(0) + _u64(90) + bytes(16)
        + _u64(0) + _u64(0) + _u64(0) + _u64(0)
        + _u64(0) + _u64(0) + _u64(0)
        + _u64(1) + _u64(2) + _u64(3)
    )
    event_data = EVENT_CPI_TAG + EVT_SWAP2_DISCRIMINATOR + event_body
    def instruction(data, height):
        return {
            "programId": METEORA_DAMM_V2_PROGRAM_ID,
            "accounts": [0],
            "data": _b58encode(data),
            "stackHeight": height,
        }
    raw = _raw()
    raw["transaction"]["message"] = {
        "accountKeys": ["payer"],
        "instructions": [{
            "programId": "aggregator", "accounts": [], "data": _b58encode(b"route")
        }],
    }
    raw["meta"]["innerInstructions"] = [{
        "index": 0,
        "instructions": [instruction(swap_data, 2), instruction(event_data, 3)],
    }]
    return raw


def _raw(meta=None):
    return {
        "slot": 123,
        "blockTime": 1795000000,
        "transaction": {
            "signatures": ["signature"],
            "message": {"accountKeys": [], "instructions": []},
        },
        "meta": meta or {
            "err": None,
            "innerInstructions": [],
            "preTokenBalances": [],
            "postTokenBalances": [],
        },
    }


def _damm_two_swap2_one_invalid_accounts_raw():
    event_body = (
        bytes(32) + bytes((0, 0, 0))
        + _u64(100) + _u64(90) + bytes((0,))
        + _u64(100) + _u64(0) + _u64(0) + _u64(90) + bytes(16)
        + _u64(0) + _u64(0) + _u64(0) + _u64(0)
        + _u64(0) + _u64(0) + _u64(0)
        + _u64(1) + _u64(2) + _u64(3)
    )
    event_data = EVENT_CPI_TAG + EVT_SWAP2_DISCRIMINATOR + event_body
    keys = [
        "authority", "1" * 32, "user-in", "user-out", "vault-a", "vault-b",
        "mint-a", "mint-b", "payer",
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        "referral", "event-authority", METEORA_DAMM_V2_PROGRAM_ID,
    ]
    def compiled(data, accounts, height):
        return {
            "programId": METEORA_DAMM_V2_PROGRAM_ID,
            "accounts": accounts,
            "data": _b58encode(data),
            "stackHeight": height,
        }
    raw = _raw()
    raw["transaction"]["message"] = {
        "accountKeys": keys,
        "instructions": [{
            "programId": "aggregator", "accounts": [], "data": _b58encode(b"route")
        }],
    }
    raw["meta"]["innerInstructions"] = [{
        "index": 0,
        "instructions": [
            compiled(SWAP2_DISCRIMINATOR + _u64(100) + _u64(90) + bytes((0,)), list(range(14)), 2),
            compiled(event_data, [0], 3),
            compiled(SWAP2_DISCRIMINATOR + _u64(200) + _u64(180) + bytes((0,)), [0], 2),
            compiled(event_data, [0], 3),
        ],
    }]
    return raw


class DammV2PersistencePipelineTests(unittest.TestCase):
    def setUp(self):
        self.store = SQLiteEventStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_no_damm_v2_swap_archives_observation_without_checkpoint(self):
        result = process_damm_v2_observation(
            self.store, _raw(), wallet_address="wallet", signature="signature"
        )
        self.assertEqual(result.status, "no_damm_v2_swaps")
        self.assertTrue(result.ready_for_next_venue)
        self.assertIsNotNone(
            self.store.get_raw_transaction("wallet", "signature")
        )
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )
        self.assertIsNone(self.store.get_checkpoint("wallet"))

    def test_missing_inner_instruction_metadata_stays_pending_for_replay(self):
        raw = _raw()
        del raw["meta"]["innerInstructions"]
        result = process_damm_v2_observation(
            self.store, raw, wallet_address="wallet", signature="signature"
        )
        self.assertEqual(result.status, "pending_reconciliation")
        self.assertFalse(result.ready_for_next_venue)
        self.assertEqual(result.unresolved_swaps, 1)
        self.assertIsNotNone(
            self.store.get_raw_transaction("wallet", "signature")
        )
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )
        self.assertIsNone(self.store.get_checkpoint("wallet"))
        self.assertEqual(
            self.store.get_pending_signatures("wallet"), ["signature"]
        )

    def test_failed_on_chain_is_delegated_to_checkpoint_coordinator(self):
        result = process_damm_v2_observation(
            self.store,
            _raw({"err": {"InstructionError": [0, "Custom"]}}),
            wallet_address="wallet",
            signature="signature",
        )
        self.assertEqual(result.status, "failed_on_chain")
        self.assertTrue(result.ready_for_next_venue)
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )

    def test_signature_mismatch_is_rejected_before_persistence(self):
        with self.assertRaises(ValueError):
            process_damm_v2_observation(
                self.store, _raw(), wallet_address="wallet",
                signature="different-signature",
            )
        self.assertIsNone(
            self.store.get_raw_transaction("wallet", "different-signature")
        )

    def test_matched_event_with_invalid_account_inventory_is_audited_and_blocks_checkpoint(self):
        result = process_damm_v2_observation(
            self.store,
            _damm_swap_event_raw(),
            wallet_address="wallet",
            signature="signature",
        )
        self.assertEqual(result.status, "pending_reconciliation")
        self.assertFalse(result.ready_for_next_venue)
        self.assertEqual(result.decoded_swaps, 1)
        self.assertEqual(result.unresolved_swaps, 1)
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )
        self.assertEqual(
            self.store.get_pending_signatures("wallet"),
            ["signature"],
        )
        attempts = self.store.get_swap_reconciliation_attempts(
            "wallet", "signature"
        )
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["status"], "INCOMPLETE")
        self.assertIn("14 contas", attempts[0]["reason"])

    def test_normalization_error_archives_raw_without_checkpoint(self):
        from unittest.mock import patch
        with patch(
            "smart_money_radar.domain.damm_v2_persistence_pipeline.normalize_transaction",
            side_effect=ValueError("invalid normalized payload"),
        ):
            with self.assertRaisesRegex(ValueError, "invalid normalized payload"):
                process_damm_v2_observation(
                    self.store, _raw(), wallet_address="wallet",
                    signature="signature",
                )
        self.assertIsNotNone(
            self.store.get_raw_transaction("wallet", "signature")
        )
        self.assertEqual(
            self.store.get_observation_metadata("wallet", "signature")["parse_status"],
            "parse_error",
        )
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )


    def test_partial_multi_bundle_write_retries_idempotently_after_second_bundle_failure(self):
        from datetime import datetime, timezone
        from decimal import Decimal
        from types import SimpleNamespace
        from unittest.mock import patch

        from smart_money_radar.domain.models import (
            SwapClassification, SwapEvidence, SwapObservation,
            build_swap_operation_id,
        )

        observed_at = datetime(2026, 11, 18, tzinfo=timezone.utc)
        bundles = []
        associations = []
        for instruction_index, cpi_path in ((2, (0,)), (3, (1,))):
            operation_id = build_swap_operation_id(
                "solana", "signature", instruction_index, cpi_path
            )
            observation = SwapObservation(
                operation_id=operation_id,
                chain="solana",
                wallet_address="wallet",
                signature="signature",
                input_mint="input-mint",
                output_mint="output-mint",
                input_amount=Decimal("1.25"),
                output_amount=Decimal("2.50"),
                observed_at=observed_at,
                parser_version="pipeline-retry-test",
            )
            classification = SwapClassification(
                operation_id=operation_id,
                side="UNKNOWN",
                confidence=Decimal("0"),
                reason="Direction is intentionally unclassified.",
            )
            evidence = SwapEvidence(
                operation_id=operation_id,
                program_id="damm-v2-program",
                venue="Meteora DAMM v2",
                instruction_index=instruction_index,
                cpi_path=cpi_path,
                evidence=("synthetic reconciled pipeline contract",),
            )
            bundles.append(SimpleNamespace(
                observation=observation,
                classification=classification,
                evidence=evidence,
            ))
            associations.append(SimpleNamespace(
                instruction=object(),
                instruction_index=instruction_index,
                cpi_path=cpi_path,
                inner_instruction_index=0,
                status="MATCHED",
            ))

        reconciled = SimpleNamespace(
            status="RECONCILED",
            reason="Both operations reconciled.",
            associations=associations,
            bundles=bundles,
        )
        original_save = self.store.save_swap_bundle
        calls = 0

        def fail_on_second_bundle_once(observation, classification, evidence):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("forced second bundle write failure")
            return original_save(observation, classification, evidence)

        with patch(
            "smart_money_radar.domain.damm_v2_persistence_pipeline.process_damm_v2_transaction",
            return_value=reconciled,
        ), patch.object(
            self.store,
            "save_swap_bundle",
            side_effect=fail_on_second_bundle_once,
        ):
            with self.assertRaisesRegex(RuntimeError, "second bundle write failure"):
                process_damm_v2_observation(
                    self.store, _raw(), wallet_address="wallet",
                    signature="signature", observed_at=observed_at,
                )

        first_id, second_id = [
            bundle.observation.operation_id for bundle in bundles
        ]
        self.assertIsNotNone(self.store.get_swap_bundle(first_id))
        self.assertIsNone(self.store.get_swap_bundle(second_id))
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )
        self.assertIsNone(self.store.get_checkpoint("wallet"))
        self.assertEqual(
            self.store.get_pending_signatures("wallet"), ["signature"]
        )

        with patch(
            "smart_money_radar.domain.damm_v2_persistence_pipeline.process_damm_v2_transaction",
            return_value=reconciled,
        ):
            retry = process_damm_v2_observation(
                self.store, _raw(), wallet_address="wallet",
                signature="signature", observed_at=observed_at,
            )

        self.assertEqual(retry.status, "reconciled")
        self.assertTrue(retry.ready_for_next_venue)
        self.assertEqual(retry.decoded_swaps, 2)
        self.assertEqual(retry.reconciled_swaps, 2)
        self.assertEqual(retry.saved_bundles, 1)
        self.assertIsNotNone(self.store.get_swap_bundle(first_id))
        self.assertIsNotNone(self.store.get_swap_bundle(second_id))
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )
        self.assertIsNone(self.store.get_checkpoint("wallet"))
        attempts = self.store.get_swap_reconciliation_attempts(
            "wallet", "signature"
        )
        self.assertEqual(len(attempts), 4)
        self.assertTrue(all(item["status"] == "MATCHED" for item in attempts))


    def test_two_real_swap2_associations_block_entire_batch_when_second_account_decode_fails(self):
        raw = _damm_two_swap2_one_invalid_accounts_raw()
        result = process_damm_v2_observation(
            self.store, raw, wallet_address="wallet", signature="signature"
        )

        self.assertEqual(result.status, "pending_reconciliation")
        self.assertEqual(result.decoded_swaps, 2)
        self.assertEqual(result.reconciled_swaps, 0)
        self.assertEqual(result.unresolved_swaps, 2)
        self.assertFalse(result.ready_for_next_venue)
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )
        self.assertIsNone(self.store.get_checkpoint("wallet"))
        self.assertEqual(
            self.store.get_pending_signatures("wallet"), ["signature"]
        )
        attempts = self.store.get_swap_reconciliation_attempts(
            "wallet", "signature"
        )
        self.assertEqual(len(attempts), 2)
        self.assertEqual([item["status"] for item in attempts], ["INCOMPLETE", "INCOMPLETE"])
        self.assertTrue(all("14 contas" in item["reason"] for item in attempts))
        from smart_money_radar.domain.models import build_swap_operation_id
        for instruction_index, cpi_path in ((0, (0,)), (0, (2,))):
            operation_id = build_swap_operation_id(
                "solana", "signature", instruction_index, cpi_path
            )
            self.assertIsNone(self.store.get_swap_bundle(operation_id))


if __name__ == "__main__":
    unittest.main()
