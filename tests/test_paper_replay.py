import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from smart_money_radar.cli import main
from smart_money_radar.domain.paper_replay import PaperConfig, ReplayTick, replay_paper


class PaperReplayTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.config = PaperConfig(Decimal(1000), Decimal(300), Decimal("0.10"))

    def tick(self, offset, price, volume, signal="NONE", allowed=True, halted=False):
        return ReplayTick(self.start + timedelta(seconds=offset), Decimal(price),
                          Decimal(volume), signal, allowed, halted)

    def test_modes_fill_after_decision_and_compare_same_history(self):
        ticks = [self.tick(0, 10, 10, "BUY"), self.tick(1, 11, 11),
                 self.tick(2, 12, 12, "SELL"), self.tick(3, 13, 13)]
        immediate = replay_paper(ticks, config=self.config, mode="immediate")
        confirmed = replay_paper(ticks, config=self.config, mode="confirmed")
        buy, sell = immediate.fills
        self.assertEqual((buy.decision_at, buy.filled_at), (ticks[0].at, ticks[1].at))
        self.assertEqual((sell.decision_at, sell.filled_at), (ticks[2].at, ticks[3].at))
        self.assertTrue(all(fill.filled_at > fill.decision_at for fill in immediate.fills))
        self.assertEqual(immediate.average_fill_delay_seconds, Decimal(1))
        self.assertEqual(immediate.total_fees, 0)
        self.assertEqual(immediate.realized_pnl.quantize(Decimal(".01")), Decimal("18.18"))
        self.assertEqual(immediate.final_equity.quantize(Decimal(".01")), Decimal("1018.18"))
        self.assertEqual(confirmed.fills, ())
        self.assertEqual(confirmed.rejected_entries, 1)

    def test_confirmation_needs_price_and_volume_and_fills_on_next_tick(self):
        ticks = [self.tick(0, 10, 10, "BUY"), self.tick(1, 11, 10),
                 self.tick(2, 12, 10, "BUY"), self.tick(3, 13, 12),
                 self.tick(4, 14, 13)]
        result = replay_paper(ticks, config=self.config, mode="confirmed")
        fill, = result.fills
        self.assertEqual((fill.decision_at, fill.filled_at), (ticks[3].at, ticks[4].at))
        self.assertEqual(result.rejected_entries, 1)

    def test_entry_filter_applies_at_signal_confirmation_and_fill(self):
        ticks = [self.tick(0, 10, 10, "BUY", False), self.tick(1, 11, 11, "BUY"),
                 self.tick(2, 12, 12, allowed=False)]
        for mode in ("immediate", "confirmed"):
            with self.subTest(mode=mode):
                result = replay_paper(ticks, config=self.config, mode=mode)
                self.assertEqual(result.fills, ())
                self.assertEqual(result.rejected_entries, 2)

    def test_stop_waits_for_positive_volume_and_costs_reduce_equity(self):
        config = PaperConfig(Decimal(1000), Decimal(100), Decimal(1),
                             Decimal(100), Decimal(100))
        ticks = [self.tick(0, 10, 1, "BUY"), self.tick(1, 10, 1),
                 self.tick(2, 8, 1), self.tick(3, 7, 0), self.tick(4, 7, 1)]
        result = replay_paper(ticks, config=config, mode="immediate")
        buy, sell = result.fills
        self.assertEqual(buy.price, Decimal("10.10"))
        self.assertEqual(sell.price, Decimal("6.93"))
        self.assertEqual(sell.reason, "stop_loss")
        self.assertEqual(sell.filled_at, ticks[4].at)
        self.assertGreater(buy.fee, 0)
        self.assertGreater(result.max_drawdown, 0)

    def test_kill_switch_cancels_entry_and_schedules_exit(self):
        blocked = [self.tick(0, 10, 10, "BUY"), self.tick(1, 11, 11, halted=True)]
        for mode in ("immediate", "confirmed"):
            results = replay_paper(blocked, config=self.config, mode=mode)
            self.assertEqual(results.fills, ())
            self.assertEqual(results.decisions[-1].reason, "kill_switch")
        opened = [self.tick(0, 10, 10, "BUY"), self.tick(1, 10, 10),
                  self.tick(2, 10, 10, halted=True), self.tick(3, 10, 10, halted=True)]
        result = replay_paper(opened, config=self.config, mode="immediate")
        self.assertEqual(result.fills[-1].reason, "kill_switch")
        self.assertEqual(result.open_quantity, 0)

    def test_entry_price_ceiling_is_shared_and_records_rejections(self):
        config = PaperConfig(Decimal(1000), Decimal(100), Decimal(1),
                             max_entry_deviation_bps=Decimal(200))
        entries = {
            "immediate": [self.tick(0, 10, 10, "BUY"), self.tick(1, 11, 11)],
            "confirmed": [self.tick(0, 10, 10, "BUY"), self.tick(1, 11, 11), self.tick(2, 12, 12)],
        }
        for mode, ticks in entries.items():
            with self.subTest(mode=mode):
                result = replay_paper(ticks, config=config, mode=mode)
                self.assertEqual(result.fills, ())
                self.assertEqual(result.rejected_entries, 1)
                self.assertEqual(result.decisions[-1].reason, "entry_price_deviation")
                self.assertEqual(result.cash, config.initial_cash)

    def test_end_of_history_has_no_fabricated_fill_and_rejects_duplicate_time(self):
        first = self.tick(0, 10, 1, "BUY")
        self.assertEqual(replay_paper([first], config=self.config, mode="immediate").pending_side, "BUY")
        self.assertTrue(replay_paper([first], config=self.config, mode="confirmed").awaiting_confirmation)
        with self.assertRaisesRegex(ValueError, "estritamente crescente"):
            replay_paper([first, first], config=self.config, mode="immediate")

    def test_cli_runs_both_modes_without_network(self):
        scenario = {"config": {"initial_cash": "1000", "max_entry_cash": "100", "max_exposure": "0.1"},
                    "ticks": [{"at": self.start.isoformat(), "price": "10", "volume": "1",
                               "signal": "BUY", "entry_allowed": True}]}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text(json.dumps(scenario))
            stdout = StringIO()
            with redirect_stdout(stdout), patch(
                "smart_money_radar.cli.HeliusSettings.from_environment",
                side_effect=AssertionError("offline"),
            ):
                main(["paper-replay", str(path)])
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["immediate"]["pending_side"], "BUY")
            self.assertTrue(report["confirmed"]["awaiting_confirmation"])
