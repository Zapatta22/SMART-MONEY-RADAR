"""Cutoff-accurate CPMM estimates, never asserted executable."""
import hashlib
import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal

from smart_money_radar.services.cpmm_theoretical_quote import theoretical_cpmm_quote

NOW=datetime(2026,11,20,15,tzinfo=timezone.utc)
RAW=b'{"getMultipleAccounts":"fixture"}'

def record():
    return {
        "pool":"pool","slot":12,"commitment":"finalized",
        "captured_at":(NOW-timedelta(seconds=3)).isoformat(),
        "available_at":(NOW-timedelta(seconds=2)).isoformat(),
        "raw_sha256":hashlib.sha256(RAW).hexdigest(),
        "reserve_in":"1000","reserve_out":"2500","fee_bps":"30",
        "input_mint":"base","output_mint":"quote",
        "input_decimals":9,"output_decimals":6,
    }

def estimate(**updates):
    args=dict(snapshot_record=record(),raw_payload=RAW,source_id="source",
              quote_id="quote-1",expected_pool="pool",expected_slot=12,
              input_mint="base",output_mint="quote",amount_in=Decimal("10"),
              cutoff=NOW,fee_provenance_verified=True)
    args.update(updates)
    return theoretical_cpmm_quote(**args)

class CpmmTheoreticalQuoteTests(unittest.TestCase):
    def test_valid_model_stays_theoretical_even_with_fee_claim(self):
        q=estimate()
        self.assertEqual(q.status,"THEORETICAL_ONLY")
        self.assertIsNotNone(q.estimate)
        self.assertFalse(q.observed_market_quote)
        self.assertFalse(q.executable_price_verified)
        self.assertEqual(q.estimate.source,"MODEL_ESTIMATE_NOT_OBSERVED")

    def test_other_pool_rejected(self):
        with self.assertRaisesRegex(ValueError,"pool"):
            estimate(expected_pool="other")

    def test_slot_conflict_rejected(self):
        with self.assertRaisesRegex(ValueError,"slot"):
            estimate(expected_slot=13)

    def test_old_reserves_block_estimate(self):
        q=estimate(cutoff=NOW+timedelta(hours=2))
        self.assertEqual(q.status,"BLOCKED")
        self.assertIn("reserve_snapshot_stale",q.reasons)

    def test_notional_exceeding_reserves_blocked(self):
        q=estimate(amount_in=Decimal("1001"))
        self.assertEqual(q.status,"BLOCKED")
        self.assertIn("input_amount_exceeds_effective_reserve",q.reasons)

    def test_unknown_fee_source_blocks_output(self):
        q=estimate(fee_provenance_verified=False)
        self.assertEqual(q.status,"BLOCKED")
        self.assertIsNone(q.estimate)

    def test_future_reserves_rejected(self):
        with self.assertRaisesRegex(ValueError,"posterior"):
            estimate(cutoff=NOW-timedelta(minutes=1))

    def test_bad_hash_rejected(self):
        with self.assertRaisesRegex(ValueError,"hash"):
            estimate(raw_payload=b"tampered")

    def test_replay_deterministic(self):
        self.assertEqual(estimate(),estimate())

    def test_missing_fee_field_is_rejected(self):
        x=record()
        del x["fee_bps"]
        with self.assertRaises(ValueError):
            estimate(snapshot_record=x)

if __name__=="__main__":
    unittest.main()
