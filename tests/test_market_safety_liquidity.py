"""Conservative safety and reserve audits, with no assumed RPC authentication."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

from smart_money_radar.services.market_safety_liquidity import (
    MarketEvidenceEnvelope, TokenSafetySnapshot, LiquiditySnapshot,
    assess_token_liquidity,
)

AT = datetime(2026, 11, 20, 15, tzinfo=timezone.utc)
RAW = b'{"pool":"fixture","slot":12}'


def envelope(tag, *, authenticated=False, available=AT, observed=None, slot=12):
    return MarketEvidenceEnvelope(
        evidence_id=tag, source_id="fixture-provider", token_mint="base", pool="pool",
        slot=slot, observed_at=observed or AT - timedelta(seconds=3),
        available_at=available, commitment="finalized",
        integrity_sha256=sha256(RAW).hexdigest(), raw_payload=RAW,
        provider_authenticated=authenticated,
    )


def token(*, authenticated=False, concentration="0.1", mint=None, freeze=None,
          risk="NONE_EVIDENCED"):
    return TokenSafetySnapshot(
        envelope("token-evidence", authenticated=authenticated),
        mint_authority=mint, freeze_authority=freeze,
        token_program="Tokenkeg", concentration_fraction=Decimal(concentration),
        concentration_audited=True, liquidity_withdrawal_risk=risk,
        mint_authority_audited=True, freeze_authority_audited=True,
        token_program_audited=True,
    )


class SafetyLiquidityContractsTests(unittest.TestCase):
    def args(self):
        return dict(token_mint="base", pool="pool", as_of=AT,
                    min_liquidity_quote=Decimal("100"),
                    max_concentration_fraction=Decimal("0.40"))

    def test_missing_information_cannot_mean_safe(self):
        result = assess_token_liquidity(token=token(), liquidity=None, **self.args())
        self.assertEqual(result.token_safety, "UNKNOWN")
        self.assertFalse(result.liquidity_verified)
        self.assertIn("liquidity_unknown", result.reasons)

    def test_mint_authority_is_hard_block(self):
        result = assess_token_liquidity(
            token=token(mint="actor"), liquidity=None, **self.args())
        self.assertEqual(result.token_safety, "CONFLICTED")
        self.assertIn("mint_authority_active", result.mandatory_blocks)

    def test_freeze_authority_is_hard_block(self):
        result = assess_token_liquidity(
            token=token(freeze="actor"), liquidity=None, **self.args())
        self.assertIn("freeze_authority_active", result.mandatory_blocks)

    def test_excessive_concentration_blocks(self):
        result = assess_token_liquidity(
            token=token(concentration="0.70"), liquidity=None, **self.args())
        self.assertIn("excessive_concentration", result.mandatory_blocks)

    def test_flagged_liquidity_withdrawal_blocks(self):
        result = assess_token_liquidity(
            token=token(risk="FLAGGED"), liquidity=None, **self.args())
        self.assertIn("liquidity_withdrawal_risk", result.mandatory_blocks)

    def test_unverified_rpc_origin_stays_unknown(self):
        result = assess_token_liquidity(
            token=token(authenticated=False), liquidity=None, **self.args())
        self.assertIn("provider_not_authenticated", result.reasons)
        self.assertFalse(result.source_authenticated)

    def test_hash_tampering_is_rejected(self):
        tampered = replace(token(), envelope=replace(
            envelope("token-evidence"), integrity_sha256="0"*64))
        with self.assertRaisesRegex(ValueError, "hash"):
            assess_token_liquidity(token=tampered, liquidity=None, **self.args())

    def test_future_information_is_rejected(self):
        late = replace(token(), envelope=envelope(
            "token-evidence", available=AT+timedelta(seconds=2)))
        with self.assertRaisesRegex(ValueError, "futura"):
            assess_token_liquidity(token=late, liquidity=None, **self.args())

    def test_stale_data_is_not_verified(self):
        old = replace(token(), envelope=envelope(
            "token-evidence", observed=AT-timedelta(hours=2),
            available=AT-timedelta(hours=1)))
        result = assess_token_liquidity(token=old, liquidity=None, **self.args())
        self.assertIn("stale_evidence", result.reasons)
        self.assertEqual(result.token_safety, "UNKNOWN")

    def test_no_token_evidence_is_unknown(self):
        result = assess_token_liquidity(token=None, liquidity=None, **self.args())
        self.assertEqual(result.token_safety, "UNKNOWN")
        self.assertEqual(result.evidence_ids, ())
        self.assertFalse(result.source_authenticated)


if __name__ == "__main__":
    unittest.main()
