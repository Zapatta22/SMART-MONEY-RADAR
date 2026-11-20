"""Adversarial RPC agreement on preserved real CPMM evidence; no network calls."""
import hashlib
import json
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path

from smart_money_radar.services.rpc_source_comparison import (
    RpcSourceRecord,compare_rpc_records,
)

BASE=Path(__file__).resolve().parents[1]/"data/evidence/mainnet/2026-11-20"
SIG="23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM"
POOL="CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu"
NOW=datetime(2026,11,20,19,tzinfo=timezone.utc)

class RpcSourceComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=(BASE/(SIG+".raw.json")).read_bytes()
    def source(self,source_id,operator,raw=None,**changes):
        raw=self.raw if raw is None else raw
        x=RpcSourceRecord(
            source_id=source_id,infrastructure_operator=operator,
            raw=raw,claimed_raw_sha256=hashlib.sha256(raw).hexdigest(),
            available_at=NOW-timedelta(minutes=1),
            commitment_requested="finalized",
        )
        return replace(x,**changes)
    def compare(self,**changes):
        options=dict(first=self.source("rpc-a","operator-a"),
                     second=self.source("rpc-b","operator-b"),
                     signature=SIG,slot=471039497,pool=POOL,cutoff=NOW)
        options.update(changes)
        return compare_rpc_records(**options)
    def changed(self,mutate):
        obj=json.loads(self.raw)
        mutate(obj["result"])
        return json.dumps(obj,separators=(",",":")).encode()

    def test_two_matching_rpc_payloads_are_not_independent_finality(self):
        x=self.compare()
        self.assertEqual(x.status,"CORROBORATED_UNATTESTED")
        self.assertTrue(x.identity_equal)
        self.assertFalse(x.independent_provider_proven)
        self.assertFalse(x.independently_finalized)
        self.assertFalse(x.operational_authorized)
        self.assertFalse(x.historic_pool_reserves_verified)

    def test_actual_second_source_null_is_unknown_not_slot_conflict(self):
        raw=b'{"jsonrpc":"2.0","result":null,"id":1}\n'
        s=self.source("rpc-b","operator-b",raw)
        x=self.compare(second=s)
        self.assertEqual(x.status,"UNKNOWN")
        self.assertIn("source_transaction_not_available",x.reasons)
        self.assertNotIn("signature_slot_or_success_conflict",x.reasons)

    def test_shared_infrastructure_blocks_independence(self):
        s=self.source("rpc-b","operator-a")
        x=self.compare(second=s)
        self.assertEqual(x.status,"UNKNOWN")
        self.assertIn("shared_rpc_infrastructure",x.reasons)

    def test_unknown_operator_blocks_independence(self):
        self.assertEqual(self.compare(second=self.source("rpc-b",None)).status,"UNKNOWN")

    def test_source_label_reuse_is_not_a_second_provider(self):
        self.assertEqual(self.compare(second=self.source("rpc-a","operator-b")).status,"UNKNOWN")

    def test_signature_mismatch_is_conflicted(self):
        raw=self.changed(lambda d: d["transaction"]["signatures"].__setitem__(0,"2"*64))
        x=self.compare(second=self.source("rpc-b","operator-b",raw))
        self.assertEqual(x.status,"CONFLICTED")
        self.assertIn("signature_slot_or_success_conflict",x.reasons)

    def test_slot_mismatch_conflicted(self):
        raw=self.changed(lambda d:d.__setitem__("slot",471039498))
        self.assertEqual(self.compare(second=self.source("rpc-b","operator-b",raw)).status,"CONFLICTED")

    def test_pool_mismatch_is_conflicted(self):
        self.assertEqual(self.compare(pool="unrelated-pool").status,"CONFLICTED")

    def test_fee_mismatch_is_conflicted(self):
        raw=self.changed(lambda d:d["meta"].__setitem__("fee",123))
        x=self.compare(second=self.source("rpc-b","operator-b",raw))
        self.assertIn("economic_or_identity_fields_divergent",x.reasons)
        self.assertEqual(x.status,"CONFLICTED")

    def test_raw_hash_tampering_conflicted(self):
        x=self.compare(second=self.source("rpc-b","operator-b",
                                           claimed_raw_sha256="0"*64))
        self.assertEqual(x.status,"CONFLICTED")
        self.assertIn("source_raw_sha_mismatch",x.reasons)

    def test_future_availability_conflicted(self):
        x=self.compare(second=self.source("rpc-b","operator-b",
                              available_at=NOW+timedelta(seconds=1)))
        self.assertIn("source_unavailable_at_cutoff",x.reasons)
        self.assertEqual(x.status,"CONFLICTED")

    def test_unfinalized_request_never_corroborates(self):
        x=self.compare(second=self.source("rpc-b","operator-b",
                                          commitment_requested="confirmed"))
        self.assertEqual(x.status,"UNKNOWN")

    def test_invalid_rpc_json_root_fails_closed(self):
        raw=b'[]'
        s=self.source("rpc-b","operator-b",raw)
        x=self.compare(second=s)
        self.assertEqual(x.status,"CONFLICTED")
        self.assertIn("source_json_invalid",x.reasons)

    def test_same_inputs_reproduce_identical_comparison(self):
        self.assertEqual(self.compare(),self.compare())

if __name__=="__main__":
    unittest.main()
