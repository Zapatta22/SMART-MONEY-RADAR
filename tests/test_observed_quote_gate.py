"""Economics and timestamp rejection tests, all offline and deterministic."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

from smart_money_radar.services.observed_quote_gate import ObservedQuoteEvidence, assess_observed_quote

NOW=datetime(2026,11,20,15,tzinfo=timezone.utc)
RAW=b"quote-fixture"

def sample(**changes):
    x=ObservedQuoteEvidence(
        quote_id="q1",source_id="fixture",pool="pool",slot=11,
        market_at=NOW-timedelta(seconds=3), observed_at=NOW-timedelta(seconds=2),
        available_at=NOW, bid=Decimal("0.99"),ask=Decimal("1.01"),
        bid_size=Decimal("500"),ask_size=Decimal("500"),
        volume=Decimal("200"),fee_bps=Decimal("30"),
        max_slippage_bps=Decimal("40"),raw_payload=RAW,
        raw_sha256=sha256(RAW).hexdigest(),observed_claimed=True,
        provider_attested=False,depth_attested=False,
    )
    return replace(x,**changes)

def assess(q):
    return assess_observed_quote(q,pool="pool",cutoff=NOW,
                                 min_liquidity=Decimal("100"),
                                 proposed_notional=Decimal("100"))

class ObservedQuoteGateTests(unittest.TestCase):
    def test_unsigned_claim_stays_unknown_no_economic_fills(self):
        a=assess(sample())
        self.assertEqual(a.status,"UNKNOWN")
        self.assertIsNone(a.tick)
        self.assertFalse(a.economics_supported)
        self.assertIn("provider_not_attested",a.reasons)

    def test_explicit_attestation_is_still_paper_only(self):
        q=sample(provider_attested=True,depth_attested=True)
        x=assess(q)
        self.assertEqual(x.status,"CANDIDATE_PAPER_ONLY")
        self.assertFalse(x.economics_supported)
        self.assertEqual(x.tick.quote_id,q.quote_id)
        self.assertFalse(x.tick.entry_allowed)

    def test_other_pool_rejected(self):
        with self.assertRaisesRegex(ValueError,"pool"):
            assess_observed_quote(sample(),pool="other",cutoff=NOW,
                                  min_liquidity=Decimal(100),proposed_notional=Decimal(100))

    def test_future_quote_rejected(self):
        with self.assertRaisesRegex(ValueError,"cutoff"):
            assess(sample(available_at=NOW+timedelta(seconds=1)))

    def test_invalid_hash_rejected(self):
        with self.assertRaisesRegex(ValueError,"hash"):
            assess(sample(raw_sha256="0"*64))

    def test_missing_fee_and_slippage_are_unknown(self):
        for q in (sample(fee_bps=None),sample(max_slippage_bps=None)):
            self.assertEqual(assess(q).status,"UNKNOWN")

    def test_insufficient_depth_is_rejected(self):
        a=assess(sample(ask_size=Decimal(1)))
        self.assertEqual(a.status,"REJECTED")
        self.assertIn("insufficient_market_depth",a.reasons)

    def test_model_quote_cannot_be_observed(self):
        a=assess(sample(observed_claimed=False))
        self.assertIn("indicative_or_model_quote",a.reasons)
        self.assertIsNone(a.tick)

    def test_non_monotonic_clocks_rejected(self):
        with self.assertRaisesRegex(ValueError,"temporal"):
            assess(sample(observed_at=NOW-timedelta(seconds=4)))

    def test_determinism(self):
        q=sample(provider_attested=True,depth_attested=True)
        self.assertEqual(assess(q),assess(q))

if __name__=="__main__":
    unittest.main()
