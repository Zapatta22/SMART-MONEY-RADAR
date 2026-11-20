"""Real observed Raydium CPMM SwapEvent, exact integer math and fail-closed tests.

The original bytes are archived in PR #100. These tests do not contact RPC.
"""
import base64
import hashlib
import json
import unittest
from datetime import datetime,timezone
from pathlib import Path

from smart_money_radar.services.cpmm_swap_event_evidence import (
    decode_cpmm_swap_event, reconcile_observed_swap_event,
)

ROOT=Path(__file__).resolve().parents[1]/"data/evidence/mainnet/2026-11-20"
SIG="23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM"
POOL="CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu"
CUT=datetime(2026,11,20,19,tzinfo=timezone.utc)


class RealCpmmSwapEventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=(ROOT/(SIG+".raw.json")).read_bytes()
        cls.manifest=json.loads((ROOT/"first-proof.manifest.json").read_bytes())
        cls.obj=json.loads(cls.raw)
        cls.event_encoded=next(
            line[len("Program data: "):]
            for line in cls.obj["result"]["meta"]["logMessages"]
            if line.startswith("Program data: ")
        )
        cls.event_raw=base64.b64decode(cls.event_encoded)

    def proof(self,*,raw=None,manifest=None,cutoff=CUT):
        return reconcile_observed_swap_event(
            transaction_raw=self.raw if raw is None else raw,
            manifest=self.manifest if manifest is None else manifest,
            cutoff=cutoff)

    def modified(self,fn):
        obj=json.loads(self.raw)
        fn(obj)
        raw=json.dumps(obj,separators=(",",":")).encode()
        m=dict(self.manifest,raw_sha256=hashlib.sha256(raw).hexdigest())
        return self.proof(raw=raw,manifest=m)

    def test_real_anchor_discriminator_and_exact_170_byte_layout(self):
        event=decode_cpmm_swap_event(self.event_raw)
        self.assertEqual(len(self.event_raw),170)
        self.assertEqual(event.pool,POOL)
        self.assertEqual(event.input_vault_before_raw,62350461617001)
        self.assertEqual(event.output_vault_before_raw,311084308598)
        self.assertTrue(event.base_input)
        self.assertFalse(event.creator_fee_on_input)

    def test_real_event_fee_and_amounts(self):
        ev=self.proof().event
        self.assertEqual(ev.input_amount_raw,19727477255)
        self.assertEqual(ev.output_amount_raw,98099917)
        self.assertEqual(ev.trade_fee_raw,49318694)
        self.assertEqual(ev.creator_fee_raw,49075)
        self.assertEqual(ev.input_transfer_fee_raw,0)
        self.assertEqual(ev.output_transfer_fee_raw,0)

    def test_exact_constant_product_economic_reconciliation(self):
        x=self.proof()
        self.assertEqual(x.calculated_gross_output_raw,98148992)
        self.assertEqual(x.calculated_net_output_raw,98099917)
        self.assertEqual(x.observed_output_raw,98099917)
        self.assertEqual(x.difference_raw,0)
        self.assertEqual(x.instruction_index,3)

    def test_no_promoted_historical_quote_or_finality(self):
        x=self.proof()
        self.assertEqual(x.status,"OBSERVED_EVENT_INTEGER_RECONCILED_UNATTESTED")
        self.assertFalse(x.network_provider_independently_authenticated)
        self.assertFalse(x.historical_poolstate_snapshot_verified)
        self.assertFalse(x.historical_ammconfig_snapshot_verified)
        self.assertFalse(x.trade_fee_rate_verified_from_ammconfig)
        self.assertFalse(x.quote_available_before_swap)
        self.assertFalse(x.executable_quote_proven)
        self.assertFalse(x.replay_eligible)

    def test_historical_cutoff_before_rpc_capture_blocks(self):
        with self.assertRaisesRegex(ValueError,"cutoff"):
            self.proof(cutoff=datetime(2026,11,18,19,tzinfo=timezone.utc))

    def test_raw_tampering_rejected(self):
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            self.proof(raw=self.raw+b" ")

    def test_discriminator_mismatch_rejected(self):
        blob=b"X"+self.event_raw[1:]
        with self.assertRaisesRegex(ValueError,"discriminador"):
            decode_cpmm_swap_event(blob)

    def test_event_truncation_rejected(self):
        with self.assertRaisesRegex(ValueError,"tamanho"):
            decode_cpmm_swap_event(self.event_raw[:-1])

    def test_invalid_bool_rejected(self):
        raw=bytearray(self.event_raw)
        raw[8+32+6*8]=2
        with self.assertRaisesRegex(ValueError,"booleano"):
            decode_cpmm_swap_event(bytes(raw))

    def test_duplicate_event_logs_rejected(self):
        def dup(x):
            logs=x["result"]["meta"]["logMessages"]
            line="Program data: "+self.event_encoded
            logs.insert(logs.index(line),line)
        with self.assertRaisesRegex(ValueError,"único"):
            self.modified(dup)

    def test_event_outside_cpmm_context_rejected(self):
        def remove_begin(x):
            logs=x["result"]["meta"]["logMessages"]
            logs.remove("Program CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C invoke [1]")
        with self.assertRaisesRegex(ValueError,"sem início"):
            self.modified(remove_begin)

    def test_wrong_pool_from_event_rejected(self):
        def bad(x):
            logs=x["result"]["meta"]["logMessages"]
            event=bytearray(self.event_raw)
            event[8:40]=bytes(32)
            logs[logs.index("Program data: "+self.event_encoded)]="Program data: "+base64.b64encode(event).decode()
        with self.assertRaisesRegex(ValueError,"não coincide"):
            self.modified(bad)

    def test_event_amount_inconsistent_with_vault_delta_rejected(self):
        def bad(x):
            logs=x["result"]["meta"]["logMessages"]
            event=bytearray(self.event_raw)
            off=8+32+8*2
            event[off:off+8]=(19727477254).to_bytes(8,"little")
            logs[logs.index("Program data: "+self.event_encoded)]="Program data: "+base64.b64encode(event).decode()
        with self.assertRaisesRegex(ValueError,"deltas"):
            self.modified(bad)

    def test_event_trade_fee_inconsistent_with_curve_rejected(self):
        def bad(x):
            logs=x["result"]["meta"]["logMessages"]
            event=bytearray(self.event_raw)
            off=8+32+6*8+1+64
            event[off:off+8]=(49318694+1000000).to_bytes(8,"little")
            logs[logs.index("Program data: "+self.event_encoded)]="Program data: "+base64.b64encode(event).decode()
        with self.assertRaisesRegex(ValueError,"econômica"):
            self.modified(bad)

    def test_event_replay_is_deterministic(self):
        self.assertEqual(self.proof(),self.proof())


if __name__=="__main__":
    unittest.main()
