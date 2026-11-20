"""Local RAW binding adversarial tests, never proof of finalized RPC authority."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json

from smart_money_radar.domain.models import (
    SwapClassification, SwapEvidence, SwapObservation, build_swap_operation_id,
)
from smart_money_radar.domain.swap_bundle_builder import SwapDomainBundle
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.receipt_raw_link import inspect_receipt_raw

T = datetime(2026, 1, 1, tzinfo=timezone.utc)


class ReceiptRawLinkTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = SQLiteEventStore(Path(tmp.name) / "archive.sqlite")
        self.addCleanup(self.store.close)
        self.operation_id = build_swap_operation_id("solana", "tx-a", 0)
        payload = {"slot": 15, "transaction": {"signatures": ["tx-a"]},
                   "meta": {"err": None}}
        self.payload = payload
        self.store.save_observation("wallet", "tx-a", payload, [],
            parse_status="no_events", parser_version="1", advance_checkpoint=False)
        obs = SwapObservation(
            self.operation_id, "solana", "wallet", "tx-a", "quote", "base",
            Decimal("10"), Decimal("2"), T + timedelta(seconds=1), "1")
        cls = SwapClassification(
            self.operation_id, "BUY", Decimal("0.9"), "fixture")
        ev = SwapEvidence(
            self.operation_id, "program", None, 0,
            evidence=("pool_state:pool",))
        self.store.save_swap_bundle(obs, cls, ev)
        with patch("smart_money_radar.storage.event_store.datetime", wraps=datetime) as clk:
            clk.now.return_value = T + timedelta(seconds=2)
            self.store.mark_processed("wallet", "tx-a", replay_bundles=(
                SwapDomainBundle(obs, cls, ev),))
        self.row = dict(operation_id=self.operation_id, signature="tx-a",
                        available_at=(T + timedelta(seconds=2)).isoformat())

    def inspect(self, **params):
        args = dict(wallet="wallet", row=self.row, pool="pool",
                    source_id="program", as_of=T + timedelta(seconds=30))
        args.update(params)
        return inspect_receipt_raw(self.store, **args)

    def test_local_hash_and_signature_link_never_attest_finality(self):
        result = self.inspect()
        self.assertEqual(result.signature, "tx-a")
        self.assertIsNotNone(result.local_payload_sha256)
        self.assertFalse(result.provider_authenticated)
        self.assertFalse(result.finalized_attested)
        self.assertEqual(result.status, "UNKNOWN")
        self.assertIn("finalization_not_attested", result.reasons)

    def test_missing_raw_keeps_unknown(self):
        with patch.object(self.store, "get_raw_transaction", return_value=None):
            result = self.inspect()
        self.assertIn("transaction_raw_missing", result.reasons)

    def test_bad_hash_does_not_pass(self):
        r = self.inspect(expected_raw_sha256="0"*64)
        self.assertIn("local_sha256_mismatch", r.reasons)

    def test_wrong_source_or_pool_is_blocked(self):
        self.assertIn("source_identity_conflict",
                      self.inspect(source_id="other").reasons)
        self.assertIn("pool_identity_unproven",
                      self.inspect(pool="other").reasons)

    def test_expected_slot_mismatch(self):
        self.assertIn("expected_slot_mismatch",
                      self.inspect(expected_slot=10).reasons)

    def test_receipt_after_cutoff_rejected(self):
        with self.assertRaisesRegex(ValueError, "futuro"):
            self.inspect(as_of=T+timedelta(seconds=1))

    def test_transaction_without_embedded_signature_cannot_be_bound(self):
        with patch.object(self.store, "get_raw_transaction",
                          return_value={"slot": 15, "meta": {"err":None}}):
            result = self.inspect()
        self.assertIn("transaction_signature_unbound", result.reasons)

    def test_same_snapshot_is_deterministic(self):
        self.assertEqual(self.inspect(), self.inspect())


if __name__ == "__main__":
    unittest.main()
