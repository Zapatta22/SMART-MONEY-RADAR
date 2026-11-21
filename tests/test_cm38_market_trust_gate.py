"""Offline trust dimensions and prospective fail-closed preflight."""
from dataclasses import replace
from datetime import datetime,timezone
from hashlib import sha256
import unittest
from smart_money_radar.services.solana_rpc_verification import RpcTransactionEvidence
from smart_money_radar.services.market_trust_gate import evaluate_market_trust,prospective_preflight

class MarketTrustTests(unittest.TestCase):
    def test_local_hash_and_declared_flags_never_attest_finality(self):
        now=datetime.now(timezone.utc)
        a=RpcTransactionEvidence(signature="1"*64,slot=1,pool=None,source_id="declared",endpoint_host="a.invalid",
            observed_at=now,available_at=now,raw_sha256=sha256(b"raw").hexdigest(),raw_payload=b"raw",
            commitment_requested="finalized",status="RPC_CONSISTENT_UNATTESTED",reasons=(),
            provider_authenticated=True,independently_finalized=True)
        b=replace(a,source_id="second",endpoint_host="b.invalid")
        result=evaluate_market_trust([a,b],assessment="CROSS_SOURCE_CONSISTENT_UNATTESTED")
        self.assertEqual(result["payload_integrity"],"LOCAL_SHA256_MATCH")
        self.assertEqual(result["finalization"],"UNKNOWN")
        self.assertEqual(result["independence"],"UNKNOWN")
        tampered=evaluate_market_trust([replace(a,raw_payload=b"tampered")],assessment="VERIFIED")
        self.assertNotEqual(tampered["payload_integrity"],"LOCAL_SHA256_MATCH")
    def test_no_claim_unlocks_prospective_engine(self):
        result=prospective_preflight(radar="launch",assessment={"radar":"launch","provider_authenticated":True,
            "independently_finalized":True,"prospective_paper_authorized":True})
        self.assertFalse(result["prospective_authorized"])
        self.assertEqual(result["eligible_ticks"],0)
        with self.assertRaises(ValueError):prospective_preflight(radar="smart_money",assessment={"radar":"launch"})
