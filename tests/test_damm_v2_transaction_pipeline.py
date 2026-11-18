import unittest
from datetime import datetime, timezone

from smart_money_radar.data_sources.damm_v2_transaction_pipeline import (
    process_damm_v2_transaction,
)


def _raw_transaction():
    return {
        "result": {
            "transaction": {
                "signatures": ["signature"],
                "message": {
                    "accountKeys": [],
                    "instructions": [],
                }
            },
            "meta": {
                "err": None,
                "innerInstructions": [],
                "preTokenBalances": [],
                "postTokenBalances": [],
            },
        }
    }


class DammV2TransactionPipelineTests(unittest.TestCase):
    def _process(self, raw):
        return process_damm_v2_transaction(
            raw,
            monitored_wallet="wallet",
            signature="signature",
            observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
            parser_version="test",
        )

    def test_valid_transaction_without_damm_v2_swaps_is_noop(self):
        result = self._process(_raw_transaction())
        self.assertEqual(result.status, "NO_DAMM_V2_SWAPS")
        self.assertEqual(result.bundles, ())

    def test_missing_execution_status_fails_closed(self):
        raw = _raw_transaction()
        del raw["result"]["meta"]["err"]
        result = self._process(raw)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("meta.err ausente", result.reason)

    def test_missing_inner_instruction_metadata_fails_closed(self):
        raw = _raw_transaction()
        del raw["result"]["meta"]["innerInstructions"]
        result = self._process(raw)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("meta.innerInstructions ausente/nulo", result.reason)

    def test_null_inner_instruction_metadata_fails_closed(self):
        raw = _raw_transaction()
        raw["result"]["meta"]["innerInstructions"] = None
        result = self._process(raw)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("meta.innerInstructions ausente/nulo", result.reason)

    def test_missing_loaded_addresses_for_lookup_table_fails_closed(self):
        raw = _raw_transaction()
        raw["result"]["transaction"]["message"]["addressTableLookups"] = [{
            "accountKey": "lookup-table",
            "writableIndexes": [0],
            "readonlyIndexes": [],
        }]
        result = self._process(raw)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("meta.loadedAddresses ausente", result.reason)

    def test_loaded_address_count_must_match_lookup_indexes(self):
        raw = _raw_transaction()
        raw["result"]["transaction"]["message"]["addressTableLookups"] = [{
            "accountKey": "lookup-table",
            "writableIndexes": [0],
            "readonlyIndexes": [],
        }]
        raw["result"]["meta"]["loadedAddresses"] = {
            "writable": [],
            "readonly": [],
        }
        result = self._process(raw)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("não corresponde à quantidade", result.reason)

    def test_loaded_addresses_without_lookup_tables_fail_closed(self):
        raw = _raw_transaction()
        raw["result"]["meta"]["loadedAddresses"] = {
            "writable": ["unexpected-address"],
            "readonly": [],
        }
        result = self._process(raw)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("sem addressTableLookups", result.reason)

    def test_mixed_account_key_formats_fail_closed(self):
        raw = _raw_transaction()
        raw["result"]["transaction"]["message"]["accountKeys"] = [
            {"pubkey": "parsed-key", "signer": True},
            "compiled-key",
        ]
        result = self._process(raw)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("mistura formatos", result.reason)

    def test_missing_transaction_signatures_fails_closed(self):
        raw = _raw_transaction()
        del raw["result"]["transaction"]["signatures"]
        result = self._process(raw)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("primeira assinatura única", result.reason)

    def test_secondary_signature_cannot_be_used_as_transaction_id(self):
        raw = _raw_transaction()
        raw["result"]["transaction"]["signatures"] = [
            "different-primary-signature", "signature"
        ]
        result = self._process(raw)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("primeira assinatura única", result.reason)

    def test_duplicate_transaction_signatures_fail_closed(self):
        raw = _raw_transaction()
        raw["result"]["transaction"]["signatures"] = ["signature", "signature"]
        result = self._process(raw)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("primeira assinatura única", result.reason)

    def test_failed_on_chain_transaction_fails_closed(self):
        raw = _raw_transaction()
        raw["result"]["meta"]["err"] = {"InstructionError": [0, "Custom"]}
        result = self._process(raw)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("falhou on-chain", result.reason)

    def test_missing_transaction_metadata_fails_closed(self):
        result = self._process({"result": {"transaction": {}}})
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("transaction/meta ausentes", result.reason)

    def test_wallet_signature_and_parser_version_are_required(self):
        raw = _raw_transaction()
        with self.assertRaises(ValueError):
            process_damm_v2_transaction(
                raw, monitored_wallet=" ", signature="signature",
                observed_at=datetime.now(timezone.utc), parser_version="1",
            )
        with self.assertRaises(ValueError):
            process_damm_v2_transaction(
                raw, monitored_wallet="wallet", signature=" ",
                observed_at=datetime.now(timezone.utc), parser_version="1",
            )
        with self.assertRaises(ValueError):
            process_damm_v2_transaction(
                raw, monitored_wallet="wallet", signature="signature",
                observed_at=datetime.now(timezone.utc), parser_version=" ",
            )


if __name__ == "__main__":
    unittest.main()
