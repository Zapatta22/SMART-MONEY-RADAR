"""Offline fixtures validate bounded Solana public RPC adapter and provenance."""
import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import Mock
from urllib.error import URLError

from smart_money_radar.services.solana_rpc_verification import verify_transaction_rpc_response, reconcile_rpc_sources
from smart_money_radar.services.solana_public_rpc_read import fetch_public_finalized_transaction

SIG="1"*64
NOW=datetime(2026,11,20,15,tzinfo=timezone.utc)

def raw(signature=SIG,slot=100, result=True, pool="pool"):
    tx={"slot":slot,"transaction":{"signatures":[signature],"message":{
        "instructions":[{"programId":"program","accounts":[pool]}]}},
        "meta":{"err":None}}
    return json.dumps({"jsonrpc":"2.0","id":1,"result":tx if result else None}).encode()

def check(**changes):
    args=dict(raw_payload=raw(),signature=SIG,source_id="a",endpoint_host="rpc.example",
              observed_at=NOW,available_at=NOW,expected_slot=100,
              expected_pool="pool",requested_commitment="finalized")
    args.update(changes)
    return verify_transaction_rpc_response(**args)

class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*_): return False
    def read(self,n=-1): return self.data

class SolanaRpcVerificationTests(unittest.TestCase):
    def test_locally_consistent_rpc_is_never_independent_attestation(self):
        e=check()
        self.assertEqual(e.status,"RPC_CONSISTENT_UNATTESTED")
        self.assertFalse(e.provider_authenticated)
        self.assertFalse(e.independently_finalized)
        self.assertEqual(e.pool,"pool")

    def test_not_found_unknown(self):
        self.assertEqual(check(raw_payload=raw(result=False)).status,"UNKNOWN")

    def test_unfinalized_request_not_a_pass(self):
        e=check(requested_commitment="confirmed")
        self.assertEqual(e.status,"UNKNOWN")
        self.assertIn("finalized_not_requested",e.reasons)

    def test_bad_slot_conflicted(self):
        self.assertEqual(check(raw_payload=raw(slot=101)).status,"CONFLICTED")

    def test_wrong_signature_conflicted(self):
        self.assertEqual(check(raw_payload=raw(signature="2"*64)).status,"CONFLICTED")

    def test_other_pool_is_unknown(self):
        e=check(expected_pool="different")
        self.assertIn("pool_instruction_unresolved",e.reasons)
        self.assertEqual(e.status,"UNKNOWN")

    def test_cross_source_conflict(self):
        e=check()
        other=check(raw_payload=raw(slot=101),expected_slot=None,source_id="b")
        status,reasons=reconcile_rpc_sources((e,other))
        self.assertEqual(status,"CONFLICTED")
        self.assertIn("contradictory_slots",reasons)

    def test_cross_source_agreement_still_unattested(self):
        e=check()
        other=check(source_id="b")
        status,_=reconcile_rpc_sources((e,other))
        self.assertEqual(status,"CROSS_SOURCE_CONSISTENT_UNATTESTED")

    def test_no_network_without_explicit_opt_in(self):
        opener=Mock()
        result=fetch_public_finalized_transaction(
            endpoint="https://rpc.example",signature=SIG,opener=opener)
        self.assertEqual(result.status,"BLOCKED")
        opener.assert_not_called()

    def test_one_read_collects_raw_and_hash(self):
        data=raw()
        opener=Mock(return_value=Response(data))
        e=fetch_public_finalized_transaction(
            endpoint="https://rpc.example",signature=SIG,enabled=True,opener=opener)
        self.assertEqual(e.requests_sent,1)
        self.assertEqual(e.status,"RPC_CONSISTENT_UNATTESTED")
        self.assertEqual(e.evidence.raw_payload,data)
        self.assertFalse(e.evidence.provider_authenticated)
        self.assertIn(b"getTransaction",opener.call_args.args[0].data)

    def test_rpc_unavailable_is_unknown_not_safe(self):
        opener=Mock(side_effect=URLError("network down"))
        e=fetch_public_finalized_transaction(
            endpoint="https://rpc.example",signature=SIG,enabled=True,opener=opener)
        self.assertEqual(e.status,"UNKNOWN")
        self.assertIn("rpc_unavailable",e.reasons)

    def test_rpc_null_not_found(self):
        e=fetch_public_finalized_transaction(
            endpoint="https://rpc.example",signature=SIG,enabled=True,
            opener=Mock(return_value=Response(raw(result=False))))
        self.assertEqual(e.status,"UNKNOWN")

if __name__=="__main__": unittest.main()
