"""Adversarial comparison tests for existing immediate/confirmed paper engine."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smart_money_radar.domain.paper_replay import ReplayTick, PaperConfig
from smart_money_radar.services.replay_mode_comparator import compare_gated_replay_modes

START = datetime(2026,11,20,tzinfo=timezone.utc)
CONFIG = PaperConfig(initial_cash=Decimal("100"), max_entry_cash=Decimal("20"),
                     max_exposure=Decimal("0.3"), fee_bps=Decimal("30"),
                     slippage_bps=Decimal("20"))


def frames():
    return tuple(
        ReplayTick(START+timedelta(seconds=i), Decimal(str(p)), Decimal(str(v)),
                   "BUY" if i==0 else "NONE", entry_allowed=True,
                   market_at=START+timedelta(seconds=i))
        for i,(p,v) in enumerate(((1,10),(1.1,20),(1.2,25),(1.3,30),(1.4,30)))
    )


def compare(rows, **updates):
    params=dict(ticks=rows, config=CONFIG, cutoffs=tuple(t.at for t in rows),
                eligible=tuple(True for _ in rows),
                observed_quotes=tuple(True for _ in rows))
    params.update(updates)
    return compare_gated_replay_modes(**params)


class ReplayModeComparatorTests(unittest.TestCase):
    def test_same_costs_and_slippage_reused_for_both_modes(self):
        report=compare(frames())
        self.assertEqual(report.observations,5)
        self.assertEqual(report.missing_prices,0)
        self.assertEqual(report.comparison_status,"PAPER_MODEL_ONLY_NOT_PROVEN_MARKET")
        self.assertGreaterEqual(report.immediate.total_fees,0)
        self.assertGreaterEqual(report.confirmed.total_fees,0)
        self.assertEqual(report.comparison["basis"],"confirmed_minus_immediate")
        self.assertEqual(report,compare(frames()))

    def test_confirmation_mode_is_distinct_from_immediate(self):
        report=compare(frames())
        self.assertTrue(any(d.action=="schedule_buy" for d in report.immediate.decisions))
        self.assertTrue(any(d.action=="await_confirmation" for d in report.confirmed.decisions))

    def test_missing_price_is_removed_from_both_modes(self):
        rows=frames()
        report=compare(rows,observed_quotes=(True, False, True, True, True))
        self.assertEqual(report.missing_prices,1)
        self.assertEqual(report.observations,4)

    def test_no_evidence_means_no_fills(self):
        rows=frames()
        report=compare(rows,observed_quotes=tuple(False for _ in rows))
        self.assertEqual(report.immediate.fills,())
        self.assertEqual(report.confirmed.fills,())
        self.assertEqual(report.missing_prices,len(rows))

    def test_future_quote_is_rejected(self):
        rows=frames()
        cutoffs=tuple(t.at-timedelta(seconds=1) for t in rows)
        with self.assertRaisesRegex(ValueError,"indisponível"):
            compare(rows,cutoffs=cutoffs)

    def test_out_of_order_is_rejected(self):
        rows=frames()
        cutoffs=(rows[1].at,rows[0].at,*[t.at for t in rows[2:]])
        with self.assertRaises(ValueError):
            compare(rows,cutoffs=cutoffs)

    def test_blocked_risk_applies_in_both_modes(self):
        rows=frames()
        result=compare(rows,eligible=tuple(False for _ in rows))
        self.assertEqual(result.immediate.fills,())
        self.assertEqual(result.confirmed.fills,())
        self.assertGreaterEqual(result.rejected_evidence,1)

    def test_reprocess_identically(self):
        rows=frames()
        self.assertEqual(compare(rows),compare(tuple(rows)))


if __name__ == "__main__":
    unittest.main()
