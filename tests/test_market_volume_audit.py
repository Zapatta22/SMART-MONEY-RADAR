"""Adversarial offline volume evidence test fixtures: never synthesize provider trust."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

from smart_money_radar.services.market_volume_audit import SwapVolumeEvidence, audit_swap_volume


NOW = datetime(2026, 11, 20, 15, tzinfo=timezone.utc)


def swap(sig="tx-a", *, amount="100", side="BUY", wallet="wallet-a",
         available_at=NOW, occurred_at=None, source_authenticated=True,
         raw=None, slot=100, commitment="finalized"):
    raw = raw or f"raw-{sig}".encode()
    return SwapVolumeEvidence(
        evidence_id=f"evidence-{sig}", signature=sig, source_id="archive",
        pool="pool", token_mint="token", quote_mint="quote", slot=slot,
        occurred_at=occurred_at or NOW - timedelta(seconds=5),
        available_at=available_at, commitment=commitment,
        quote_amount=Decimal(amount), side=side, wallet=wallet,
        raw_payload=raw, raw_sha256=sha256(raw).hexdigest(),
        source_authenticated=source_authenticated,
    )


def audit(*rows):
    return audit_swap_volume(
        tuple(rows), pool="pool", token_mint="token", quote_mint="quote",
        as_of=NOW, window=timedelta(minutes=5),
    )


class MarketVolumeAuditTests(unittest.TestCase):
    def test_distinct_finalized_swaps_are_aggregated_once(self):
        result = audit(swap(), swap("tx-b", amount="60", wallet="wallet-b"))
        self.assertEqual(result.quote_volume, Decimal("160"))
        self.assertEqual(result.unique_signatures, 2)
        self.assertEqual(result.duplicate_count, 0)
        self.assertTrue(result.volume_verified)

    def test_duplicate_signature_contributes_once(self):
        a = swap()
        duplicate = replace(a, evidence_id="another-receipt")
        result = audit(a, duplicate, swap("tx-b", amount="60", wallet="wallet-b"))
        self.assertEqual(result.quote_volume, Decimal("160"))
        self.assertEqual(result.duplicate_count, 1)

    def test_duplicate_signature_with_contradictory_amount_blocks(self):
        a = swap()
        contrary = replace(a, evidence_id="another-receipt", quote_amount=Decimal(500))
        result = audit(a, contrary, swap("tx-b", amount="60", wallet="wallet-b"))
        self.assertEqual(result.quality, "CONFLICTED")
        self.assertFalse(result.volume_verified)
        self.assertIn("contradictory_duplicate_signature", result.risk_flags)

    def test_unfinalized_and_unauthenticated_never_pass(self):
        for row in (swap(commitment="confirmed"),
                    swap(source_authenticated=False)):
            result = audit(row, swap("tx-b", amount="50", wallet="wallet-b"))
            self.assertEqual(result.quality, "UNKNOWN")
            self.assertFalse(result.volume_verified)

    def test_future_data_rejected(self):
        with self.assertRaisesRegex(ValueError, "futuros"):
            audit(swap(available_at=NOW + timedelta(seconds=1)))

    def test_old_data_never_increases_confirmed_volume(self):
        old = swap("old", occurred_at=NOW-timedelta(hours=2))
        result = audit(old, swap("tx-b", amount="50", wallet="wallet-b"))
        self.assertEqual(result.unique_signatures, 1)
        self.assertFalse(result.volume_verified)

    def test_bad_raw_hash_rejected(self):
        a = replace(swap(), raw_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "SHA"):
            audit(a)

    def test_concentrated_wallet_is_flagged(self):
        result = audit(swap(amount="999"), swap("tx-b", amount="1", wallet="wallet-b"))
        self.assertIn("concentrated_volume_by_wallet", result.risk_flags)
        self.assertFalse(result.volume_verified)

    def test_one_wallet_cannot_fake_multiple_market_participants(self):
        result = audit(swap(), swap("tx-b", wallet="wallet-a"))
        self.assertIn("independent_market_participants_unknown", result.reasons)
        self.assertFalse(result.volume_verified)

    def test_order_is_deterministic_when_ids_are_unique(self):
        a, b = swap(), swap("tx-b", amount="50", wallet="wallet-b")
        self.assertEqual(audit(a, b), audit(b, a))

    def test_scope_conflicts_are_errors(self):
        with self.assertRaises(ValueError):
            audit(replace(swap(), pool="other"))

    def test_invalid_quote_mint_is_rejected(self):
        with self.assertRaises(ValueError):
            audit_swap_volume((swap(),), pool="pool", token_mint="token",
                              quote_mint="token", as_of=NOW, window=timedelta(minutes=5))


if __name__ == "__main__":
    unittest.main()
