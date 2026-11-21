"""CM66 informational Launch qualification regressions."""
import hashlib
import json
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from smart_money_radar.services.cm38j_launch_integration import launch_metric_receipts
from smart_money_radar.services.market_volume_audit import SwapVolumeEvidence

class LaunchEconomicQualificationTests(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def run_receipts(self, swaps=()):
        return launch_metric_receipts(token_mint="token", pool="pool",
            quote_mint="quote", at=self.at, strategy="immediate", swaps=swaps)

    def swap(self, signature, side="BUY", delta=1, raw=b"rpc"):
        return SwapVolumeEvidence(evidence_id=signature+side, signature=signature,
            source_id="rpc", pool="pool", token_mint="token", quote_mint="quote",
            slot=1, occurred_at=self.at-timedelta(seconds=delta),
            available_at=self.at, commitment="finalized", quote_amount=Decimal("10"),
            side=side, raw_payload=raw, raw_sha256=hashlib.sha256(raw).hexdigest())

    def test_missing_and_blocked(self):
        result=self.run_receipts()
        q=result["economic_qualification"]
        self.assertEqual(q["status"], "NOT_COMPUTABLE")
        self.assertIsNone(q["volume_quote"])
        self.assertFalse(q["prospective_paper_authorized"])
        self.assertEqual(result["modes"], {"immediate":"BLOCKED","confirmed":"BLOCKED"})

    def test_volume_and_cutoff_provenance(self):
        q=self.run_receipts((self.swap("a"),self.swap("b","SELL")))["economic_qualification"]
        self.assertEqual(q["volume_quote"],"20")
        self.assertEqual(q["quality"],"UNKNOWN")
        self.assertEqual([x["side"] for x in q["evidence"]],["BUY","SELL"])
        digest=q.pop("sha256")
        self.assertEqual(digest, hashlib.sha256(json.dumps(q,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest())

    def test_stale_excluded_and_future_rejected(self):
        self.assertEqual(self.run_receipts((self.swap("a",delta=301),))["economic_qualification"]["evidence"],[])
        with self.assertRaises(ValueError):
            self.run_receipts((self.swap("a",delta=-1),))

    def test_conflicting_signature_not_qualified(self):
        q=self.run_receipts((self.swap("a"),self.swap("a","SELL")))["economic_qualification"]
        self.assertIsNone(q["volume_quote"])
        self.assertIn("contradictory_duplicate_signature",q["risk_flags"])
        self.assertFalse(q["operational_authorized"])


class LaunchArchiveTests(unittest.TestCase):
    def test_empty_archive_does_not_attest(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from smart_money_radar.storage.event_store import SQLiteEventStore
        from smart_money_radar.services.cm38j_launch_integration import _resolve_launch_rpc
        with TemporaryDirectory() as tmp:
            store = SQLiteEventStore(Path(tmp) / "test.sqlite")
            try:
                result = _resolve_launch_rpc(store, [{"kind":"swap","evidence_id":"absent"}],
                    datetime(2025,1,1,tzinfo=timezone.utc))
                self.assertEqual(result["status"],"UNKNOWN")
                self.assertEqual(result["links"],[{"evidence_id":"absent","status":"UNKNOWN"}])
            finally:
                store.close()
