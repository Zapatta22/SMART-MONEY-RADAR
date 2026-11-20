"""Integration tests for fail-closed market evidence and historical classification."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

from smart_money_radar.services.market_opportunity_bridge import classify_with_market_evidence
from smart_money_radar.services.opportunity_classifier import OpportunityEvidence
from smart_money_radar.services.wallet_consensus import WalletConsensusReport

T = datetime(2026,11,20,15,tzinfo=timezone.utc)


def base(**changes):
    return replace(OpportunityEvidence(
        token_mint="base", chain="solana", pool="pool", as_of=T, source_id="provider",
        source_status="VERIFIED", history_coverage="COMPLETE", token_safety="VERIFIED",
        liquidity_quote=Decimal(99999), volume_quote=Decimal(99999),
        liquidity_verified=True, volume_verified=True,
        price_confirmation=True, volume_confirmation=True,
        wallet_independence_verified=True,
    ), **changes)


def consensus():
    return WalletConsensusReport(
        direction="BUY", eligible_wallets=4, supporting_signatures=5,
        rejected_wallets=(), members=(), independence_verified=True,
        actionable=False, reasons=(),
    )


def classify(**kwargs):
    params=dict(base=base(), consensus=consensus(), safety=None, liquidity=None,
                swaps=(), quote_mint="quote", min_liquidity_quote=Decimal(100),
                max_concentration_fraction=Decimal("0.4"))
    params.update(kwargs)
    return classify_with_market_evidence(**params)


class MarketEvidenceBridgeTests(unittest.TestCase):
    def test_caller_verified_claims_are_downgraded_without_market_evidence(self):
        result=classify()
        self.assertEqual(result.classification.verdict, "UNKNOWN")
        self.assertEqual(result.classification.data_quality, "UNKNOWN")
        self.assertEqual(result.classification.score_breakdown[0][0], "direction")
        self.assertEqual(result.classification.liquidity_quote, None)
        self.assertEqual(result.classification.volume_quote, None)
        self.assertEqual(dict(result.classification.modes)["immediate"], "BLOCKED")
        self.assertFalse(result.classification.operational_authorized)

    def test_existing_risk_block_cannot_be_overridden(self):
        result=classify(base=base(mandatory_blocks=("mint_authority_active",)))
        self.assertEqual(result.classification.verdict, "REJECTED")
        self.assertIn("mint_authority_active", result.classification.reasons)

    def test_unknown_market_provenance_does_not_promote_positive_consensus(self):
        result=classify(base=base(
            liquidity_quote=Decimal(1_000_000),
            volume_quote=Decimal(1_000_000),
        ))
        self.assertEqual(result.classification.verdict, "UNKNOWN")
        self.assertFalse(result.classification.operational_authorized)
        self.assertFalse(result.safety.source_authenticated)

    def test_market_source_conflict_is_never_assumed_safe(self):
        from smart_money_radar.services.market_safety_liquidity import (
            MarketSafetyFinding,
        )
        from unittest.mock import patch
        finding=MarketSafetyFinding(
            token_safety="VERIFIED", liquidity_quote=Decimal("1000"),
            liquidity_verified=True, mandatory_blocks=(), reasons=(),
            evidence_ids=("token",), observed_at=T, available_at=T,
            slot=100, source_id="different-provider", source_authenticated=True,
        )
        with patch(
            "smart_money_radar.services.market_opportunity_bridge.assess_token_liquidity",
            return_value=finding,
        ):
            result=classify()
        self.assertEqual(result.classification.verdict, "REJECTED")
        self.assertIn("source_provenance_unverified", result.classification.reasons)
        self.assertEqual(dict(result.classification.modes)["immediate"], "BLOCKED")

    def test_replay_is_deterministic_without_new_evidence(self):
        a=classify()
        b=classify()
        self.assertEqual(a, b)

    def test_invalid_volume_window_does_not_silently_pass(self):
        with self.assertRaises(ValueError):
            classify(volume_window=timedelta(seconds=0))


if __name__ == "__main__":
    unittest.main()
