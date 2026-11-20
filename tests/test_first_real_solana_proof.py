"""Regression against original, non-anonymized Solana getTransaction RAW.

This file was captured by one public RPC request on 2026-11-20, not generated
by a fixture factory. Hash pinning detects accidental changes. An RPC result
returned with requested 'finalized' is still NOT independent finality proof.
"""
import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1] / "data/evidence/mainnet/2026-11-20"
SIG="23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM"
SHA="3325222e2c33f6735432f12065b348b4657ae9cfc2c1141061c7c78639724dad"
PROGRAM="CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"
POOL="CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu"
INPUT_VAULT="C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU"
OUTPUT_VAULT="8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG"

class FirstRealSolanaProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=(ROOT/(SIG+".raw.json")).read_bytes()
        cls.manifest=json.loads((ROOT/"first-proof.manifest.json").read_bytes())
        cls.tx=json.loads(cls.raw)["result"]
        cls.keys=cls.tx["transaction"]["message"]["accountKeys"]
        cls.swap=cls.manifest["decoded_cpmm_swaps"][0]
        cls.instruction=cls.tx["transaction"]["message"]["instructions"][cls.swap["instruction_index"]]
        cls.accounts=[cls.keys[i] for i in cls.instruction["accounts"]]

    def test_raw_bytes_sha256_pinned(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(),SHA)
        self.assertEqual(self.manifest["raw_sha256"],SHA)
        self.assertEqual(len(self.raw),7083)

    def test_real_signature_and_slot_match(self):
        self.assertEqual(self.tx["transaction"]["signatures"][0],SIG)
        self.assertEqual(self.manifest["signature_requested"],SIG)
        self.assertEqual(self.tx["slot"],self.manifest["slot_observed"])
        self.assertEqual(self.tx["slot"],471039497)

    def test_rpc_requested_finalized_but_unattested(self):
        self.assertEqual(self.manifest["requested_commitment"],"finalized")
        self.assertEqual(self.manifest["rpc_status"],"RPC_CONSISTENT_UNATTESTED")
        self.assertFalse(self.manifest["independently_finalized"])
        self.assertFalse(self.manifest["provider_authenticated"])
        self.assertIsNone(self.tx["meta"]["err"])

    def test_rpc_request_is_single_and_source_recorded(self):
        self.assertEqual(self.manifest["requests_sent"],1)
        self.assertEqual(self.manifest["rpc_endpoint"],"https://api.mainnet-beta.solana.com")
        self.assertEqual(self.manifest["rpc_source"],"solana-public-mainnet-triton")

    def test_verified_instruction_program_and_pool_account_identity(self):
        self.assertEqual(self.keys[self.instruction["programIdIndex"]],PROGRAM)
        self.assertEqual(self.accounts[3],POOL)
        self.assertEqual(self.swap["program_id"],PROGRAM)
        self.assertEqual(self.swap["pool"],POOL)
        self.assertEqual(len(self.accounts),13)

    def test_vaults_and_mints_are_bound_to_original_instruction(self):
        self.assertEqual(self.accounts[6],INPUT_VAULT)
        self.assertEqual(self.accounts[7],OUTPUT_VAULT)
        self.assertEqual(self.swap["input_vault"],INPUT_VAULT)
        self.assertEqual(self.swap["output_vault"],OUTPUT_VAULT)
        self.assertEqual(self.accounts[10],self.swap["input_mint"])
        self.assertEqual(self.accounts[11],self.swap["output_mint"])

    def test_historical_vault_deltas_from_transaction_meta(self):
        ledger={}
        for phase in ("pre","post"):
            for row in self.tx["meta"][phase+"TokenBalances"]:
                ledger.setdefault(row["accountIndex"],{})[phase]=int(row["uiTokenAmount"]["amount"])
        # The raw TX contains both vault balances at this slot. These are
        # NOT attested effective reserves after protocol/creator fees.
        self.assertEqual(ledger[3]["post"]-ledger[3]["pre"],19727477255)
        self.assertEqual(ledger[1]["post"]-ledger[1]["pre"],-98099917)
        self.assertEqual(self.tx["meta"]["fee"],27000)

    def test_transaction_and_collection_temporal_order(self):
        occurred=datetime.fromtimestamp(self.tx["blockTime"],tz=timezone.utc)
        observed=datetime.fromisoformat(self.manifest["observed_at"])
        available=datetime.fromisoformat(self.manifest["available_at"])
        self.assertLess(occurred,observed)
        self.assertLessEqual(observed,available)

    def test_no_execution_price_or_full_historical_reserves_promoted(self):
        self.assertFalse(self.manifest["historical_reserves_verified"])
        self.assertFalse(self.manifest["pool_state_verified"])
        self.assertFalse(self.manifest["vault_ownership_verified"])
        self.assertFalse(self.manifest["executable_quote_verified"])
        self.assertFalse(self.manifest["financial_execution_authorized"])

    def test_replay_determinism_on_immutable_raw(self):
        a=json.loads(self.raw)
        b=json.loads((ROOT/(SIG+".raw.json")).read_bytes())
        self.assertEqual(a,b)

if __name__=="__main__":
    unittest.main()
