"""Exercise the simulation module from SQLite receipts and independent quote files."""

import hashlib
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from smart_money_radar.cli import main
from smart_money_radar.domain.models import (
    SwapClassification, SwapEvidence, SwapObservation, build_swap_operation_id,
)
from smart_money_radar.domain.swap_bundle_builder import SwapDomainBundle
from smart_money_radar.storage.event_store import SQLiteEventStore


class PaperAcceptanceTests(unittest.TestCase):
    def test_compares_both_modes_from_archived_signals_without_future_quotes(self):
        origin = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def at(second):
            return origin + timedelta(seconds=second)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "archive.sqlite"
            store = SQLiteEventStore(db)
            for signature, side, event_time, receipt_time in (
                ("entry", "BUY", 2, 3), ("exit", "SELL", 8, 9),
            ):
                first, second = ("quote", "base") if side == "BUY" else ("base", "quote")
                operation = build_swap_operation_id("solana", signature, 0)
                observation = SwapObservation(
                    operation, "solana", "wallet", signature, first, second,
                    Decimal(10), Decimal(1), at(event_time), "acceptance-fixture",
                )
                classification = SwapClassification(operation, side, Decimal("0.95"), "fixture")
                evidence = SwapEvidence(operation, "program", None, 0)
                store.save_observation(
                    "wallet", signature, {"meta": {"err": None}}, [], parse_status="no_events",
                    parser_version="v1", advance_checkpoint=False,
                )
                store.save_swap_bundle(observation, classification, evidence)
                with patch("smart_money_radar.storage.event_store.datetime", wraps=datetime) as clock:
                    clock.now.return_value = at(receipt_time)
                    store.mark_processed("wallet", signature, replay_bundles=(
                        SwapDomainBundle(observation, classification, evidence),
                    ))
            store.close()

            scenario = root / "scenario.json"
            market = {"program": "program", "base_mint": "base", "quote_mint": "quote"}
            scenario.write_text(json.dumps({
                "config": {"initial_cash": "1000", "max_entry_cash": "100", "max_exposure": "0.1",
                           "fee_bps": "100", "stop_loss": "0.3", "take_profit": "0.8"},
                "market": {**market, "wallet": "wallet", "min_confidence": "0.8",
                           "signal_ttl_seconds": 20},
            }))
            quotes = root / "quotes.json"
            quotes.write_text(json.dumps({
                **market, "source": "synthetic-acceptance",
                "quotes": [
                    {"quote_id": f"q{second}", "market_at": at(second).isoformat(),
                     "available_at": at(second).isoformat(), "bid": str(bid), "ask": str(ask),
                     "bid_size": "100", "ask_size": "100", "volume": str(volume)}
                    for second, bid, ask, volume in (
                        (4, 9, 10, 10), (5, 10, 11, 20), (6, 11, 12, 30),
                        (10, 11, 12, 30), (11, 13, 14, 30),
                    )
                ],
            }))
            args = ["paper-replay", str(scenario), "--archive", str(db), "--quotes", str(quotes)]

            def run(*options):
                output = StringIO()
                with redirect_stdout(output):
                    main([*args, *options])
                return json.loads(output.getvalue())

            before = run("--as-of", at(6).isoformat())
            full = run()
            self.assertEqual(full, run())
            comparison = full["comparison"]
            self.assertEqual(comparison["closed_trades"], {"immediate": 1, "confirmed": 1})
            self.assertEqual(comparison["scenario_sha256"], hashlib.sha256(scenario.read_bytes()).hexdigest())
            self.assertEqual(full["archive"]["quote_archive"]["quotes"], 5)
            self.assertEqual(before["archive"]["quote_archive"]["quotes"], 3)
            fee_rate = Decimal(".01")
            with localcontext() as context:
                context.prec = 40
                for mode, buy_at, expected_ask in (("immediate", 5, 11), ("confirmed", 6, 12)):
                    result = full[mode]
                    buy, sell = result["fills"]
                    self.assertEqual(before[mode]["fills"], [buy])
                    self.assertEqual((buy["quote_id"], sell["quote_id"]), (f"q{buy_at}", "q11"))
                    self.assertEqual(Decimal(buy["price"]), expected_ask)
                    self.assertEqual(Decimal(sell["price"]), 13)
                    for fill in result["fills"]:
                        self.assertLess(datetime.fromisoformat(fill["decision_at"]),
                                        datetime.fromisoformat(fill["market_at"]))
                    expected_proceeds = Decimal(100) / (1 + fee_rate) / expected_ask * 13 * (1 - fee_rate)
                    self.assertEqual(Decimal(result["final_equity"]), Decimal(900) + expected_proceeds)
                    self.assertEqual(Decimal(result["average_fill_delay_seconds"]), 1)
                    self.assertGreater(Decimal(result["total_fees"]), 0)
                    self.assertGreater(Decimal(result["max_drawdown"]), 0)
            self.assertLess(Decimal(comparison["equity_delta"]), 0)
