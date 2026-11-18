import unittest

from smart_money_radar.domain.damm_v2_persistence_pipeline import (
    process_damm_v2_observation,
)
from smart_money_radar.storage.event_store import SQLiteEventStore


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


if __name__ == "__main__":
    unittest.main()
