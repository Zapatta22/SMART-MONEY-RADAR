"""Independent adversarial tests for RAW -> quote identity and time linkage."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

from smart_money_radar.services.evidence_chain import bind_evidence_chain
from smart_money_radar.services.receipt_raw_link import ReceiptRawLink
from smart_money_radar.services.observed_quote_gate import (
    ObservedQuoteEvidence, assess_observed_quote,
)

NOW = datetime(2026, 11, 20, 15, tzinfo=timezone.utc)
RAW = b"fixture-quote"


def receipt(**kw):
    x = ReceiptRawLink(
        operation_id="op1", signature="sig1", wallet="wallet", pool="pool",
        source_id="source", slot=20, observed_at=NOW-timedelta(seconds=3),
        available_at=NOW-timedelta(seconds=2), local_payload_sha256="a"*64,
        status="UNKNOWN", reasons=("provider_authentication_unavailable",
                                    "finalization_not_attested"),
    )
    return replace(x, **kw)


def quote(**kw):
    x = ObservedQuoteEvidence(
        quote_id="q1", source_id="source", pool="pool", slot=20,
        market_at=NOW-timedelta(seconds=3),
        observed_at=NOW-timedelta(seconds=2), available_at=NOW,
        bid=Decimal("1"), ask=Decimal("1.01"),
        bid_size=Decimal("200"), ask_size=Decimal("200"),
        volume=Decimal("100"), fee_bps=Decimal("25"),
        max_slippage_bps=Decimal("40"), raw_payload=RAW,
        raw_sha256=sha256(RAW).hexdigest(),
        observed_claimed=True, provider_attested=True, depth_attested=True,
    )
    return replace(x, **kw)


def bind(r=None, q=None, **kw):
    r = r or receipt()
    q = q if q is not None else quote()
    gate = assess_observed_quote(
        q, pool=q.pool, cutoff=NOW+timedelta(seconds=2),
        min_liquidity=Decimal("100"), proposed_notional=Decimal("50"),
    )
    p = dict(receipt=r, quote=q, quote_gate=gate,
             cutoff=NOW+timedelta(seconds=2), expected_pool="pool",
             expected_source="source")
    p.update(kw)
    return bind_evidence_chain(**p)


class EvidenceChainTests(unittest.TestCase):
    def test_locally_linked_still_never_authenticated_or_executable(self):
        result=bind()
        self.assertEqual(result.status, "LOCALLY_LINKED_UNATTESTED")
        self.assertFalse(result.provider_authenticated)
        self.assertFalse(result.finalized_attested)
        self.assertFalse(result.executable_price_verified)
        self.assertIn("receipt_finality_unknown", result.reasons)

    def test_missing_quote_id_or_gate_never_complete(self):
        r=receipt()
        x=bind_evidence_chain(receipt=r,quote=None,quote_gate=None,
                              cutoff=NOW,expected_pool="pool")
        self.assertEqual(x.status,"INCOMPLETE")
        self.assertIsNone(x.quote_id)

    def test_slot_mismatch_blocks(self):
        x=bind(q=quote(slot=21))
        self.assertEqual(x.status,"CONFLICTED")
        self.assertIn("transaction_quote_slot_mismatch",x.reasons)

    def test_cross_source_conflict_blocks(self):
        x=bind(q=quote(source_id="other"))
        self.assertEqual(x.status,"CONFLICTED")
        self.assertIn("cross_source_identity_conflict",x.reasons)

    def test_future_quote_is_not_eligible(self):
        q=quote(available_at=NOW+timedelta(seconds=5))
        gate=assess_observed_quote(q,pool="pool",
                                  cutoff=NOW+timedelta(seconds=10),
                                  min_liquidity=Decimal("100"),
                                  proposed_notional=Decimal("50"))
        x=bind_evidence_chain(receipt=receipt(),quote=q,quote_gate=gate,
                              cutoff=NOW,expected_pool="pool")
        self.assertEqual(x.status,"CONFLICTED")
        self.assertIn("quote_after_cutoff",x.reasons)

    def test_tampered_quote_hash_is_conflict(self):
        q=quote(raw_sha256="0"*64)
        from smart_money_radar.services.observed_quote_gate import QuoteGateResult
        gate=QuoteGateResult("UNKNOWN",("quote_hash_invalid",),"q1","source","pool",20,NOW,None)
        x=bind_evidence_chain(receipt=receipt(),quote=q,quote_gate=gate,
                              cutoff=NOW,expected_pool="pool")
        self.assertIn("quote_raw_hash_mismatch",x.reasons)
        self.assertEqual(x.status,"CONFLICTED")

    def test_wrong_pool_prohibited(self):
        x=bind(r=receipt(pool="else"))
        self.assertIn("receipt_pool_mismatch",x.reasons)
        self.assertEqual(x.status,"CONFLICTED")

    def test_duplicate_case_is_deterministic(self):
        self.assertEqual(bind(),bind())


if __name__=="__main__":
    unittest.main()
