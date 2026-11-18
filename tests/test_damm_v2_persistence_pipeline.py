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


if __name__ == "__main__":
    unittest.main()
