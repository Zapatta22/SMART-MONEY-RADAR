"""Real captured CPMM vault deltas + synthetic witness adversarial controls."""
import hashlib
import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from smart_money_radar.services.historical_cpmm_state import (
    reconstruct_tx_vaults, HistoricalAccountWitness, inspect_historical_witnesses,
)

ROOT=Path(__file__).resolve().parents[1]/"data/evidence/mainnet/2026-11-20"
SIG="23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM"
CUT=datetime(2026,11,20,19,tzinfo=timezone.utc)

class HistoricalCpmmStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=(ROOT/(SIG+".raw.json")).read_bytes()
        cls.manifest=json.loads((ROOT/"first-proof.manifest.json").read_bytes())

    def build(self,**kwargs):
        options=dict(original_raw=self.raw,manifest=self.manifest,cutoff=CUT)
        options.update(kwargs)
        return reconstruct_tx_vaults(**options)

    def test_real_transaction_yields_exact_historical_vault_deltas(self):
        s=self.build()
        self.assertEqual(s.slot,471039497)
        self.assertEqual(s.input_vault.delta_raw,19727477255)
        self.assertEqual(s.output_vault.delta_raw,-98099917)
        self.assertEqual(s.input_vault.pre_raw,62368009739127)
        self.assertEqual(s.output_vault.pre_raw,313591578802)
        self.assertEqual(s.solana_network_fee_lamports,27000)

    def test_no_effective_reserves_or_trade_fee_inferred(self):
        s=self.build()
        self.assertIsNone(s.reserve_effective_in)
        self.assertIsNone(s.reserve_effective_out)
        self.assertIsNone(s.cpmm_trade_fee_rate)
        self.assertFalse(s.economic_replay_eligible)
        self.assertEqual(s.status,"PARTIAL_HISTORICAL_TX_ONLY")
        self.assertEqual(s.balance_scope,"TRANSACTION_PRE_POST_NOT_PRE_SWAP")
        self.assertIn("instruction_level_prestate_not_proven",s.reasons)

    def test_captured_later_cannot_backfill_decision_on_event_day(self):
        with self.assertRaisesRegex(ValueError,"cutoff"):
            self.build(cutoff=datetime(2026,11,18,19,tzinfo=timezone.utc))

    def test_modified_raw_rejected_before_decoding(self):
        with self.assertRaisesRegex(ValueError,"SHA"):
            self.build(original_raw=self.raw.replace(b"471039497",b"471039498"))

    def test_wrong_slot_and_signature_fail_closed(self):
        for change in (dict(slot_observed=471039496),dict(signature_requested="wrong")):
            m=dict(self.manifest,**change)
            with self.assertRaisesRegex(ValueError,"assinatura ou slot"):
                self.build(manifest=m)

    def test_wrong_cpmm_pool_rejected(self):
        m=json.loads(json.dumps(self.manifest))
        m["decoded_cpmm_swaps"][0]["pool"]="different"
        with self.assertRaisesRegex(ValueError,"identidade CPMM"):
            self.build(manifest=m)

    def test_missing_historical_vault_post_balance_rejected(self):
        p=json.loads(self.raw)
        p["result"]["meta"]["postTokenBalances"]=[
            row for row in p["result"]["meta"]["postTokenBalances"]
            if row["accountIndex"]!=1]
        modified=json.dumps(p,separators=(",",":")).encode()
        m=dict(self.manifest,raw_sha256=hashlib.sha256(modified).hexdigest())
        with self.assertRaisesRegex(ValueError,"saldo pré/pós"):
            self.build(original_raw=modified,manifest=m)

    def test_missing_required_account_witnesses_blocked(self):
        result=inspect_historical_witnesses(self.build(),(),cutoff=CUT)
        self.assertEqual(result.status,"UNKNOWN")
        self.assertEqual(len(result.missing),4)
        self.assertFalse(result.economic_replay_eligible)

    def witness(self,role="POOL_STATE",**changes):
        state=self.build()
        ids=dict(POOL_STATE=state.pool,AMM_CONFIG=state.amm_config,
                 INPUT_VAULT=state.input_vault.address,
                 OUTPUT_VAULT=state.output_vault.address)
        raw=b"synthetic historical account (not on-chain evidence)"
        x=HistoricalAccountWitness(
            account_id=ids[role],role=role,slot=state.slot,
            available_at=state.available_at,
            source_id="synthetic",raw_bytes=raw,
            sha256_hex=hashlib.sha256(raw).hexdigest(),
            provenance="UNKNOWN",pre_swap_order_proven=False)
        return replace(x,**changes)

    def test_after_swap_slot_rejected(self):
        x=self.witness(slot=self.build().slot+1)
        result=inspect_historical_witnesses(self.build(),(x,),cutoff=CUT)
        self.assertEqual(result.status,"CONFLICTED")
        self.assertIn("historical_slot_after_swap",result.reasons)

    def test_historical_witness_after_cutoff_rejected(self):
        x=self.witness(available_at=CUT+timedelta(seconds=1))
        result=inspect_historical_witnesses(self.build(),(x,),cutoff=CUT)
        self.assertEqual(result.status,"CONFLICTED")
        self.assertIn("historical_data_after_cutoff",result.reasons)

    def test_wrong_account_or_tampered_witness_rejected(self):
        for x in (self.witness(account_id="other"),
                  self.witness(sha256_hex="0"*64)):
            self.assertEqual(
                inspect_historical_witnesses(self.build(),(x,),cutoff=CUT).status,
                "CONFLICTED")

    def test_complete_synthetic_claims_do_not_unlock_economics(self):
        witnesses=tuple(self.witness(role=role,
            provenance="INDEPENDENTLY_ATTESTED",pre_swap_order_proven=True)
            for role in ("POOL_STATE","AMM_CONFIG","INPUT_VAULT","OUTPUT_VAULT"))
        result=inspect_historical_witnesses(self.build(),witnesses,cutoff=CUT)
        self.assertEqual(result.status,"LOCALLY_CONSISTENT_UNATTESTED")
        self.assertFalse(result.economic_replay_eligible)
        self.assertIn("external_attestation_not_cryptographically_checked",result.reasons)

    def test_duplicate_witness_invalid(self):
        w=self.witness()
        result=inspect_historical_witnesses(self.build(),(w,w),cutoff=CUT)
        self.assertEqual(result.status,"CONFLICTED")
        self.assertIn("role_invalid_or_duplicated",result.reasons)

    def test_deterministic_reconstruction(self):
        self.assertEqual(self.build(),self.build())

if __name__=="__main__":
    unittest.main()
