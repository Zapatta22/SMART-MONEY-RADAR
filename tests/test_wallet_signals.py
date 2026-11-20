import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from smart_money_radar.domain.models import (
    SwapClassification,
    SwapEvidence,
    SwapObservation,
    build_swap_operation_id,
)
from smart_money_radar.domain.swap_bundle_builder import SwapDomainBundle
from smart_money_radar.services.wallet_signals import WalletSignalService
from smart_money_radar.storage.event_store import SQLiteEventStore


class WalletSignalTests(unittest.TestCase):
    def setUp(self):
        self.store = SQLiteEventStore(":memory:")
        self.addCleanup(self.store.close)
        self.service = WalletSignalService(self.store)
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def add(self, signature, sides, *, occurred, available, pool="pool-a"):
        self.store.save_observation(
            "wallet", signature, {"meta": {"err": None}}, [],
            parse_status="no_events", parser_version="1", advance_checkpoint=False,
        )
        bundles = []
        for index, (direction, classification) in enumerate(sides):
            operation_id = build_swap_operation_id("solana", signature, index)
            input_mint, output_mint = ("quote", "base") if direction == "BUY" else ("base", "quote")
            observation = SwapObservation(
                operation_id, "solana", "wallet", signature, input_mint, output_mint,
                Decimal(10), Decimal(2), self.start + timedelta(seconds=occurred), "1",
            )
            label = SwapClassification(operation_id, classification, Decimal("0.90"), "fixture")
            evidence = SwapEvidence(operation_id, "program", None, index, evidence=(f"pool_state:{pool}",))
            self.store.save_swap_bundle(observation, label, evidence)
            bundles.append(SwapDomainBundle(observation, label, evidence))
        with patch("smart_money_radar.storage.event_store.datetime", wraps=datetime) as clock:
            clock.now.return_value = self.start + timedelta(seconds=available)
            self.store.mark_processed("wallet", signature, replay_bundles=tuple(bundles))

    def report(self, at):
        return self.service.get_report(
            wallet="wallet", program="program", pool="pool-a", base_mint="base", quote_mint="quote",
            as_of=self.start + timedelta(seconds=at), window=timedelta(minutes=1),
            max_publication_delay=timedelta(seconds=5), min_confidence=Decimal("0.8"),
            min_transactions=2,
        )

    def test_direction_uses_distinct_transactions_and_clocks(self):
        self.add("first", [("BUY", "BUY"), ("BUY", "BUY")], occurred=1, available=2)
        self.add("future", [("BUY", "BUY")], occurred=2, available=4)
        before = self.report(3)
        self.assertEqual(before.direction, "INSUFFICIENT")
        self.assertEqual([item.signature for item in before.evidence], ["first"])
        self.assertEqual(len(before.evidence[0].operation_ids), 2)
        after = self.report(4)
        self.assertEqual(after.direction, "BUY")
        self.assertEqual([item.signature for item in after.evidence], ["first", "future"])

    def test_rejects_opposite_hops_mismatched_classification_and_delayed_evidence(self):
        self.add("mixed-hops", [("BUY", "BUY"), ("SELL", "SELL")], occurred=1, available=2)
        self.add("wrong-class", [("SELL", "BUY")], occurred=2, available=3)
        self.add("late", [("BUY", "BUY")], occurred=3, available=20)
        self.add("other-pool", [("BUY", "BUY")], occurred=3, available=4, pool="pool-b")
        result = self.report(21)
        self.assertEqual(result.direction, "INSUFFICIENT")
        self.assertEqual(result.evidence, ())
        self.assertEqual([(item.signature, item.reasons) for item in result.excluded], [
            ("mixed-hops", ("opposing_directions",)),
            ("wrong-class", ("direction_unverified",)),
            ("late", ("late_publication",)),
        ])

    def test_opposing_transactions_are_reported_as_mixed(self):
        self.add("first", [("BUY", "BUY")], occurred=1, available=2)
        self.add("second", [("BUY", "BUY")], occurred=2, available=3)
        self.add("opposing", [("SELL", "SELL")], occurred=3, available=4)
        self.assertEqual(self.report(4).direction, "MIXED")
