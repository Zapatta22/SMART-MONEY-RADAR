import hashlib
import json
import unittest

from smart_money_radar.data_sources.solana_transaction_evidence_bundle import (
    build_solana_transaction_evidence_bundle,
)


def _transaction(signature="signature-1", slot=123):
    return {
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [],
                "instructions": [],
            },
        },
        "meta": {
            "err": None,
            "innerInstructions": [],
            "preTokenBalances": [],
            "postTokenBalances": [],
        },
        "slot": slot,
    }


class SolanaTransactionEvidenceBundleTests(unittest.TestCase):
    def test_builds_complete_bundle_from_one_rpc_payload(self):
        raw = _transaction()
        bundle = build_solana_transaction_evidence_bundle(
            raw, source_id="geyser-provider-a"
        )

        expected_hash = hashlib.sha256(
            json.dumps(
                raw,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

        self.assertEqual(bundle.identity.transaction_signature, "signature-1")
        self.assertEqual(bundle.identity.slot, 123)
        self.assertEqual(bundle.identity.source_id, "geyser-provider-a")
        self.assertEqual(bundle.identity.payload_sha256, expected_hash)
        self.assertTrue(bundle.instruction_inventory.complete)
        self.assertTrue(bundle.balance_deltas.complete)
        self.assertEqual(bundle.transfers, ())
        self.assertTrue(bundle.structurally_complete)

    def test_accepts_standard_rpc_result_wrapper(self):
        raw = {"jsonrpc": "2.0", "result": _transaction()}
        bundle = build_solana_transaction_evidence_bundle(
            raw, source_id="rpc-a"
        )

        self.assertEqual(bundle.identity.transaction_signature, "signature-1")
        self.assertEqual(bundle.identity.slot, 123)
        self.assertTrue(bundle.structurally_complete)

    def test_rejects_missing_source_identity(self):
        with self.assertRaisesRegex(ValueError, "source_id"):
            build_solana_transaction_evidence_bundle(
                _transaction(), source_id=" "
            )

    def test_rejects_missing_transaction_signature(self):
        raw = _transaction(signature="")
        with self.assertRaisesRegex(ValueError, "assinatura"):
            build_solana_transaction_evidence_bundle(
                raw, source_id="rpc-a"
            )

    def test_rejects_invalid_slot(self):
        for slot in (None, -1, True, "123"):
            with self.subTest(slot=slot):
                with self.assertRaisesRegex(ValueError, "slot"):
                    build_solana_transaction_evidence_bundle(
                        _transaction(slot=slot), source_id="rpc-a"
                    )

    def test_preserves_incomplete_decoder_evidence_as_ineligible(self):
        raw = _transaction()
        raw["meta"].pop("postTokenBalances")
        bundle = build_solana_transaction_evidence_bundle(
            raw, source_id="rpc-a"
        )

        self.assertFalse(bundle.balance_deltas.complete)
        self.assertFalse(bundle.structurally_complete)

    def test_rejects_non_json_payload_instead_of_hashing_repr(self):
        raw = _transaction()
        raw["non_json"] = object()
        with self.assertRaisesRegex(ValueError, "canonicalizado"):
            build_solana_transaction_evidence_bundle(
                raw, source_id="rpc-a"
            )


if __name__ == "__main__":
    unittest.main()
