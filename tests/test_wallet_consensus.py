"""Independent multiwallet consensus tests: no actionable inference from address count."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from smart_money_radar.services.wallet_consensus import WalletConsensusService


class FakeSignals:
    def __init__(self, reports):
        self.reports = reports
        self.calls = []
    def get_report(self, **kwargs):
        self.calls.append(kwargs)
        return self.reports[kwargs["wallet"]]


def report(direction, signatures=(), excluded=()):
    return SimpleNamespace(
        direction=direction,
        evidence=tuple(SimpleNamespace(signature=s) for s in signatures),
        excluded=tuple(excluded),
    )


class WalletConsensusTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 20, tzinfo=timezone.utc)
        self.args = dict(wallets=("alpha", "beta"), program="cpmm", pool="pool",
                         base_mint="base", quote_mint="quote", as_of=self.now,
                         window=timedelta(hours=1),
                         max_publication_delay=timedelta(seconds=5),
                         min_confidence=Decimal("0.8"), min_transactions_per_wallet=2)

    def test_matching_buy_wallets_are_summary_not_permission_to_trade(self):
        fake = FakeSignals({
            "alpha": report("BUY", ("a1", "a2")),
            "beta": report("BUY", ("b1", "b2")),
        })
        outcome = WalletConsensusService(fake).get_report(**self.args)
        self.assertEqual(outcome.direction, "BUY")
        self.assertEqual(outcome.eligible_wallets, 2)
        self.assertEqual(outcome.supporting_signatures, 4)
        self.assertEqual(outcome.rejected_wallets, ())
        self.assertFalse(outcome.independence_verified)
        self.assertFalse(outcome.actionable)
        self.assertIn("wallet_independence_unverified", outcome.reasons)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual({x["as_of"] for x in fake.calls}, {self.now})
        self.assertEqual({x["pool"] for x in fake.calls}, {"pool"})

    def test_contradictory_wallets_are_mixed(self):
        fake = FakeSignals({
            "alpha": report("BUY", ("a", "b")),
            "beta": report("SELL", ("c", "d")),
        })
        outcome = WalletConsensusService(fake).get_report(**self.args)
        self.assertEqual(outcome.direction, "MIXED")
        self.assertFalse(outcome.actionable)
        self.assertIn("conflicting_directions", outcome.reasons)

    def test_insufficient_wallet_report_does_not_count_as_support(self):
        fake = FakeSignals({
            "alpha": report("BUY", ("a", "b")),
            "beta": report("INSUFFICIENT", ("c",)),
        })
        outcome = WalletConsensusService(fake).get_report(**self.args)
        self.assertEqual(outcome.direction, "INSUFFICIENT")
        self.assertEqual(outcome.eligible_wallets, 1)
        self.assertEqual(outcome.rejected_wallets, ("beta",))
        self.assertIn("insufficient_distinct_wallets", outcome.reasons)

    def test_shared_signature_is_counted_once(self):
        fake = FakeSignals({
            "alpha": report("BUY", ("same", "a")),
            "beta": report("BUY", ("same", "b")),
        })
        outcome = WalletConsensusService(fake).get_report(**self.args)
        self.assertEqual(outcome.supporting_signatures, 3)
        self.assertFalse(outcome.actionable)

    def test_duplicate_wallet_or_not_enough_wallets_rejected(self):
        fake = FakeSignals({"alpha": report("BUY")})
        for wallets in (("alpha", "alpha"), (), ("alpha",)):
            with self.subTest(wallets=wallets):
                with self.assertRaises(ValueError):
                    WalletConsensusService(fake).get_report(**{
                        **self.args, "wallets": wallets,
                    } if wallets != ("alpha",) else {
                        **self.args, "wallets": wallets, "min_wallets": 1,
                    })

    def test_consensus_as_of_after_future_evidence_is_controlled_by_upstream(self):
        fake = FakeSignals({
            "alpha": report("BUY", ("a", "b")),
            "beta": report("BUY", ("c", "d")),
        })
        service = WalletConsensusService(fake)
        service.get_report(**self.args)
        self.assertTrue(all(
            call["as_of"] == self.now
            and call["window"] == self.args["window"]
            and call["min_confidence"] == self.args["min_confidence"]
            for call in fake.calls
        ))


if __name__ == "__main__":
    unittest.main()
