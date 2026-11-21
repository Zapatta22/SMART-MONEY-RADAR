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
    _base58, decode_cpmm_swap_event, reconcile_observed_swap_event,
)
from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID
from smart_money_radar.data_sources.solana_token_transfer_decoder import SPL_TOKEN_PROGRAM_ID
from smart_money_radar.services.launch_cpmm_historical_reconciliation import (
    reconcile_launch_historical_swap,
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

    def test_swap_event_from_nested_program_is_not_cpmm_evidence(self):
        def move_into_inner_invocation(tx):
            logs = tx["result"]["meta"]["logMessages"]
            event = "Program data: " + self.event_encoded
            position = logs.index(event)
            invocation = f"Program {SPL_TOKEN_PROGRAM_ID} invoke [2]"
            logs.pop(position)
            logs.insert(logs.index(invocation, position) + 1, event)

        with self.assertRaisesRegex(ValueError, "único"):
            self.modified(move_into_inner_invocation)

    def test_failed_cpmm_log_rejects_event_even_with_successful_transaction_metadata(self):
        def mark_swap_failed(tx):
            logs = tx["result"]["meta"]["logMessages"]
            success = f"Program {RAYDIUM_CPMM_PROGRAM_ID} success"
            logs[logs.index(success)] = f"Program {RAYDIUM_CPMM_PROGRAM_ID} failed: fixture error"

        with self.assertRaisesRegex(ValueError, "sem sucesso"):
            self.modified(mark_swap_failed)

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

    def test_launch_historical_reconciliation_uses_scoped_transfer_not_instruction_minimum(self):
        swap, = decode_raydium_cpmm_swaps(self.obj)
        mints = {swap.accounts.input_token_mint: 6, swap.accounts.output_token_mint: 9}
        receipt = reconcile_launch_historical_swap(
            transaction_raw=self.raw, manifest=self.manifest, cutoff=CUT, swap=swap,
            quote_mint=swap.accounts.output_token_mint, pool_decimals=mints,
        )
        self.assertEqual(receipt["status"], "OBSERVED_EVENT_AND_TRANSFERS_RECONCILED_UNATTESTED")
        self.assertEqual(receipt["side"], "SELL")
        self.assertEqual(receipt["quote_amount_raw"], "98099917")
        self.assertEqual(receipt["quote_amount_normalized"], "0.098099917")
        self.assertEqual(receipt["token_amount_normalized"], "19727.477255")
        self.assertEqual(receipt["output_transfer"]["inner_instruction_index"], 1)
        self.assertEqual(receipt["trade_fee_raw"], "49318694")
        self.assertEqual(receipt["creator_fee_raw"], "49075")
        self.assertEqual(receipt["creator_fee_mint"], swap.accounts.output_token_mint)
        self.assertFalse(receipt["historical_fee_rates_verified"])
        self.assertFalse(receipt["quote_available_before_swap"])

    def test_launch_historical_reconciliation_rejects_transfer_amount_and_decimal_conflicts(self):
        tx = json.loads(self.raw)
        swap, = decode_raydium_cpmm_swaps(tx)
        mints = {swap.accounts.input_token_mint: 6, swap.accounts.output_token_mint: 9}
        instructions = next(group["instructions"] for group in tx["result"]["meta"]["innerInstructions"]
                            if group["index"] == swap.instruction_index)
        instructions[1]["data"] = _base58(bytes([12]) + (98099916).to_bytes(8, "little") + bytes([9]))
        invalid_transfer = json.dumps(tx).encode()
        for raw, decimals, reason in (
            (invalid_transfer, mints, "historical_event_transfer_mismatch"),
            (self.raw, {**mints, swap.accounts.output_token_mint: 8},
             "historical_and_prospective_mint_decimals_disagree"),
        ):
            with self.subTest(reason=reason):
                manifest = {**self.manifest, "raw_sha256": hashlib.sha256(raw).hexdigest()}
                receipt = reconcile_launch_historical_swap(
                    transaction_raw=raw, manifest=manifest, cutoff=CUT, swap=swap,
                    quote_mint=swap.accounts.output_token_mint, pool_decimals=decimals,
                )
                self.assertEqual(receipt["status"], "CONFLICTED")
                self.assertEqual(receipt["reason"], reason)
                self.assertNotIn("quote_amount_raw", receipt)

    def test_launch_historical_reconciliation_excludes_evidence_until_cutoff(self):
        swap, = decode_raydium_cpmm_swaps(self.obj)
        receipt = reconcile_launch_historical_swap(
            transaction_raw=self.raw, manifest=self.manifest,
            cutoff=datetime(2026, 11, 20, 18, 24, tzinfo=timezone.utc),
            swap=swap, quote_mint=swap.accounts.output_token_mint,
            pool_decimals={swap.accounts.input_token_mint: 6, swap.accounts.output_token_mint: 9},
        )
        self.assertEqual(receipt["status"], "UNAVAILABLE")
        self.assertNotIn("signature", receipt)
        self.assertNotIn("event_raw_sha256", receipt)


if __name__=="__main__":
    unittest.main()
