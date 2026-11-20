"""Real prospective CPMM four-account evidence regression — not 2026-11-18 state.

Exact request/response bytes were captured by one public Solana RPC call,
and archived after an offline recheck by GitHub Actions. No network tests.
"""
import hashlib
import json
import unittest
from datetime import datetime,timezone
from pathlib import Path

from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
from smart_money_radar.services.prospective_cpmm_account_snapshot import (
    inspect_prospective_cpmm_response,
)

BASE=Path(__file__).resolve().parents[1]/"data/evidence/mainnet/2026-11-20"
CAPTURE=BASE/"prospective-slot-471856996"
SIG="23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM"
EXPECTED_REQUEST_SHA="2ee9db161ff7928efee3e21ac4ac93d63daeec3cab22838a94c582b1a10ed718"
EXPECTED_RESPONSE_SHA="2645d85a94cdd728f7485929b59fbdd475a1d200cb403c8f4a893e50a8f44562"

class RealProspectiveCpmmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((CAPTURE/"manifest.json").read_bytes())
        cls.request=(CAPTURE/"request.raw.json").read_bytes()
        cls.response=(CAPTURE/"response.raw.json").read_bytes()
        cls.first=json.loads((BASE/"first-proof.manifest.json").read_bytes())
        raw=(BASE/(SIG+".raw.json")).read_bytes()
        cls.accounts=decode_raydium_cpmm_swaps(json.loads(raw))[0].accounts

    def verify(self,response=None,request=None):
        m=self.manifest
        a=self.accounts
        return inspect_prospective_cpmm_response(
            response_raw=self.response if response is None else response,
            request_raw=self.request if request is None else request,
            source_id="solana-public-mainnet-triton",endpoint=m["endpoint"],
            observed_at=datetime.fromisoformat(m["observed_at"]),
            available_at=datetime.fromisoformat(m["available_at"]),
            pool=a.pool_state,amm_config=a.amm_config,
            input_vault=a.input_vault,output_vault=a.output_vault,
            input_mint=a.input_token_mint,output_mint=a.output_token_mint,
            authority=a.authority,
            input_token_program=a.input_token_program,
            output_token_program=a.output_token_program,
            original_swap_slot=self.first["slot_observed"],
        )

    def test_original_raw_hashes_exact(self):
        self.assertEqual(hashlib.sha256(self.request).hexdigest(),EXPECTED_REQUEST_SHA)
        self.assertEqual(hashlib.sha256(self.response).hexdigest(),EXPECTED_RESPONSE_SHA)
        self.assertEqual(self.manifest["request_sha256"],EXPECTED_REQUEST_SHA)
        self.assertEqual(self.manifest["response_sha256"],EXPECTED_RESPONSE_SHA)

    def test_response_slot_is_after_historical_swap(self):
        self.assertEqual(self.first["slot_observed"],471039497)
        self.assertEqual(self.manifest["context_slot"],471856996)
        self.assertGreater(self.manifest["context_slot"],self.first["slot_observed"])

    def test_four_accounts_scope_exact_original_pool(self):
        req=json.loads(self.request)
        a=self.accounts
        self.assertEqual(req["method"],"getMultipleAccounts")
        self.assertEqual(req["params"][0],[
            a.pool_state,a.amm_config,a.input_vault,a.output_vault])
        self.assertEqual(req["params"][1]["commitment"],"finalized")

    def test_current_account_decoders_and_fee_buckets(self):
        q=self.verify()
        self.assertEqual(q.status,"RPC_DECLARED_PROSPECTIVE_ONLY")
        self.assertEqual(q.effective_input_raw,76473066869631)
        self.assertEqual(q.effective_output_raw,257014075604)
        self.assertEqual(q.input_vault_raw,76503529653334)
        self.assertEqual(q.output_vault_raw,257443240033)
        self.assertEqual(q.declared_trade_fee_rate,2500)
        self.assertEqual(q.declared_creator_fee_rate,500)
        self.assertEqual(list(q.account_sha256),self.manifest["account_sha256"])

    def test_no_pre_swap_or_operational_promotion(self):
        q=self.verify()
        self.assertFalse(q.pre_swap_state_of_original_tx)
        self.assertFalse(q.provider_independently_authenticated)
        self.assertFalse(q.chronological_instruction_order_proven)
        self.assertFalse(q.executable_quote_proven)
        self.assertFalse(q.operational_authorized)
        self.assertFalse(self.manifest["historical_original_swap_state_verified"])

    def test_available_at_is_capture_time_not_old_blocktime(self):
        m=self.manifest
        first_available=datetime.fromisoformat(self.first["available_at"])
        new_available=datetime.fromisoformat(m["available_at"])
        self.assertGreater(new_available,first_available)
        self.assertGreater(new_available,datetime(2026,11,18,19,tzinfo=timezone.utc))

    def test_tampered_original_response_no_longer_matches_hash(self):
        mutated=self.response+b" "
        self.assertNotEqual(hashlib.sha256(mutated).hexdigest(),EXPECTED_RESPONSE_SHA)

    def test_deterministic_reconstruction(self):
        self.assertEqual(self.verify(),self.verify())

if __name__=="__main__":
    unittest.main()
