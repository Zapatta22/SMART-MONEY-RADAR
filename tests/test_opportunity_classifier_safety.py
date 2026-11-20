"""Adversarial, deterministic contract tests for the non-executable opportunity classifier."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smart_money_radar.services.opportunity_classifier import (
    OpportunityEvidence, classify_opportunity, rank_opportunities,
)
from smart_money_radar.services.wallet_consensus import WalletConsensusReport, WalletConsensusMember


def wallet_consensus(direction="BUY", *, independent=False, signatures=4, wallets=2):
    members = tuple(
        WalletConsensusMember(
            wallet=f"wallet-{i}", direction=direction,
            signatures=(f"signature-{i}",), excluded_count=0,
        ) for i in range(wallets)
    )
    return WalletConsensusReport(
        direction=direction, eligible_wallets=wallets,
        supporting_signatures=signatures, rejected_wallets=(),
        members=members, independence_verified=independent,
        actionable=False, reasons=(),
    )


def evidence(**changes):
    record = OpportunityEvidence(
        token_mint="token", chain="solana", pool="pool",
        as_of=datetime(2026, 11, 20, tzinfo=timezone.utc),
        source_id="attested-source",
        source_status="VERIFIED", history_coverage="COMPLETE",
        token_safety="VERIFIED",
        liquidity_quote=Decimal("50000"),
        volume_quote=Decimal("15000"),
        liquidity_verified=True, volume_verified=True,
        price_confirmation=True, volume_confirmation=True,
        wallet_independence_verified=True,
    )
    return replace(record, **changes)


class OpportunityClassifierSafetyTests(unittest.TestCase):
    def test_positive_independent_wallets_are_informational_simulation_candidate(self):
        report = classify_opportunity(evidence(), wallet_consensus(independent=True))
        self.assertEqual(report.verdict, "PRIORITY")
        self.assertGreaterEqual(report.score, 70)
        self.assertEqual(report.data_quality, "VERIFIED")
        self.assertEqual(dict(report.modes), {
            "immediate": "SIMULATION_CANDIDATE",
            "confirmed": "SIMULATION_CANDIDATE",
        })
        self.assertFalse(report.operational_authorized)

    def test_related_wallets_are_unknown_despite_high_score(self):
        report = classify_opportunity(evidence(
            wallet_independence_verified=False,
        ), wallet_consensus(independent=False, wallets=5, signatures=20))
        self.assertEqual(report.verdict, "UNKNOWN")
        self.assertGreaterEqual(report.score, 80)
        self.assertEqual(dict(report.modes), {
            "immediate": "BLOCKED", "confirmed": "BLOCKED",
        })

    def test_contradiction_blocks_even_when_liquidity_high(self):
        report = classify_opportunity(evidence(), wallet_consensus(
            direction="MIXED", independent=True, wallets=5, signatures=20))
        self.assertEqual(report.verdict, "REJECTED")
        self.assertIn("contradictory_wallet_signals", report.reasons)
        self.assertFalse(report.operational_authorized)

    def test_unknown_liquidity_blocks_both_modes(self):
        report = classify_opportunity(evidence(
            liquidity_quote=None, liquidity_verified=False,
        ), wallet_consensus(independent=True))
        self.assertEqual(report.verdict, "UNKNOWN")
        self.assertIn("liquidity_unknown", report.reasons)
        self.assertEqual(dict(report.modes)["immediate"], "BLOCKED")

    def test_critical_block_overrides_high_score(self):
        report = classify_opportunity(evidence(
            mandatory_blocks=("mint_authority_active",)
        ), wallet_consensus(independent=True, wallets=5, signatures=30))
        self.assertEqual(report.verdict, "REJECTED")
        self.assertGreaterEqual(report.score, 80)
        self.assertIn("mint_authority_active", report.reasons)
        self.assertFalse(report.operational_authorized)

    def test_gap_or_unverified_source_never_promoted(self):
        for changes in (
            {"source_status": "CONFLICTED"},
            {"source_status": "UNKNOWN"},
            {"history_coverage": "UNKNOWN"},
            {"history_coverage": "PARTIAL"},
            {"history_coverage": "GAP"},
            {"token_safety": "CONFLICTED"},
            {"token_safety": "UNKNOWN"},
        ):
            with self.subTest(changes=changes):
                report = classify_opportunity(
                    evidence(**changes), wallet_consensus(independent=True))
                self.assertIn(report.verdict, ("UNKNOWN", "REJECTED"))
                self.assertEqual(dict(report.modes)["immediate"], "BLOCKED")

    def test_high_score_does_not_override_manipulation_flags(self):
        r = classify_opportunity(
            evidence(manipulation_flags=("sybil_cluster",)),
            wallet_consensus(independent=True, wallets=5, signatures=30),
        )
        self.assertEqual(r.verdict, "REJECTED")
        self.assertIn("manipulation:sybil_cluster", r.reasons)
        self.assertFalse(r.operational_authorized)

    def test_two_modes_preserve_confirmation_boundary(self):
        record = classify_opportunity(evidence(
            price_confirmation=None, volume_confirmation=None
        ), wallet_consensus(independent=True))
        self.assertEqual(record.verdict, "PRIORITY")
        self.assertEqual(dict(record.modes), {
            "immediate": "SIMULATION_CANDIDATE", "confirmed": "BLOCKED",
        })
        self.assertFalse(record.operational_authorized)

    def test_duplicate_hops_cannot_be_counted_twice_by_classifier(self):
        consensus = wallet_consensus(independent=True, wallets=2, signatures=2)
        first = classify_opportunity(evidence(), consensus)
        again = classify_opportunity(evidence(), consensus)
        self.assertEqual(first, again)
        self.assertEqual(first.unique_signatures, 2)
        self.assertEqual(dict(first.score_breakdown)["evidence_signatures"], 6)

    def test_reprocessing_historical_snapshot_is_deterministic(self):
        date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        record = evidence(as_of=date)
        a = classify_opportunity(record, wallet_consensus(independent=True))
        b = classify_opportunity(record, wallet_consensus(independent=True))
        self.assertEqual(a, b)
        self.assertEqual(a.as_of, date)

    def test_rank_prioritizes_verdict_before_score(self):
        high_risk = classify_opportunity(
            evidence(token_mint="unsafe", mandatory_blocks=("critical",)),
            wallet_consensus(independent=True, wallets=5, signatures=30),
        )
        safe = classify_opportunity(
            evidence(token_mint="safe"), wallet_consensus(independent=True))
        ranked = rank_opportunities((high_risk, safe))
        self.assertEqual([item.token_mint for item in ranked], ["safe", "unsafe"])

    def test_invalid_numeric_and_source_contracts_rejected(self):
        for changed in (
            {"liquidity_quote": Decimal("NaN")},
            {"volume_quote": Decimal("-1")},
            {"source_status": "GUESSED"},
            {"token_mint": ""},
            {"chain": "ethereum"},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    classify_opportunity(evidence(**changed), wallet_consensus(independent=True))

    def test_contradiction_is_rejected_even_when_independence_is_unknown(self):
        record = classify_opportunity(
            evidence(wallet_independence_verified=False),
            wallet_consensus(direction="MIXED", independent=False),
        )
        self.assertEqual(record.verdict, "REJECTED")
        self.assertIn("contradictory_wallet_signals", record.reasons)
        self.assertEqual(dict(record.modes)["immediate"], "BLOCKED")

    def test_zero_liquidity_and_volume_are_unknown_not_safe(self):
        for change in ({"liquidity_quote": Decimal(0)},
                       {"volume_quote": Decimal(0)}):
            with self.subTest(change=change):
                record = classify_opportunity(
                    evidence(**change), wallet_consensus(independent=True),
                )
                self.assertEqual(record.verdict, "UNKNOWN")
                self.assertEqual(dict(record.modes)["immediate"], "BLOCKED")

    def test_scope_and_liquidity_immutability(self):
        source = evidence()
        report = classify_opportunity(source, wallet_consensus(independent=True))
        self.assertEqual(report.token_mint, source.token_mint)
        self.assertEqual(report.pool, source.pool)
        self.assertEqual(report.source_id, source.source_id)
        self.assertEqual(report.liquidity_quote, Decimal("50000"))
        self.assertEqual(report.volume_quote, Decimal("15000"))
        self.assertFalse(report.operational_authorized)


if __name__ == "__main__":
    unittest.main()
