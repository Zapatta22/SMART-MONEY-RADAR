"""Regression coverage for configured CPMM models through the offline supervisor."""

import io
import json
import sqlite3
import unittest
from contextlib import redirect_stderr
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import test_real_cpmm_prospective_history as archived

from smart_money_radar import cli
from smart_money_radar.services.cm38j_launch_integration import launch_metric_receipts
from smart_money_radar.services.operational_controls import LocalOperationalControls
from smart_money_radar.services.persistent_supervisor import PersistentSupervisor
from smart_money_radar.services.radar_event_bridge import IntegratedRadarEvent
from smart_money_radar.services.radar_intelligence import IntelligenceScope, LaunchModelScenarios
from smart_money_radar.storage.cpmm_prospective_history import SQLiteCpmmProspectiveHistory
from smart_money_radar.storage.event_store import SQLiteEventStore


SOL = "So11111111111111111111111111111111111111112"
OTHER = "7ymF66Z6VhgNiwadtVhjTtT6U7iQRpSxeiRrhfufhigh"
AMOUNT_KEYS = (
    "input_amount_raw", "output_amount_raw", "trade_fee_raw", "creator_fee_raw",
    "protocol_fee_raw", "fund_fee_raw",
)
# Independent rounded results from the archived reserves with mode 1,
# 2500 trade, 500 creator, 120000 protocol and 40000 fund millionths.
EXPECTED = {
    SOL: {
        "buy_integer_model": (1000000000, 295505328562, 2500000, 500000, 300000, 100000),
        "sell_integer_model": (2000000, 6700, 5000, 4, 600, 200),
        "buy_integer_exact_output_model": (10114, 3000000, 26, 5, 3, 1),
        "sell_integer_exact_output_model": (1212639046756, 4000000000, 3031597617,
                                             2001001, 363791714, 121263904),
    },
    OTHER: {
        "buy_integer_model": (1000000, 3350, 2500, 2, 300, 100),
        "sell_integer_model": (2000000000, 588735679312, 5000000, 1000000, 600000, 200000),
        "buy_integer_exact_output_model": (905897044175, 3000000000, 2264742611,
                                            1500751, 271769113, 90589704),
        "sell_integer_exact_output_model": (13485, 4000000, 35, 6, 4, 1),
    },
}


class CPMMSupervisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archived.RealCpmmHistoryTests.setUpClass()

    def setUp(self):
        fixture = archived.RealCpmmHistoryTests()
        self.capture = fixture.capture()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive_path = Path(self.temp.name) / "archive.sqlite"
        history = SQLiteCpmmProspectiveHistory(self.archive_path)
        try:
            history.append_capture_with_original(
                self.capture, manifest_raw=fixture.bundles[0][0],
                original_transaction_raw=fixture.old, original_manifest=fixture.old_manifest,
                cutoff=archived.CUTOFF,
            )
        finally:
            history.close()
        self.original_slot = fixture.old_manifest["slot_observed"]

    def test_journals_both_strategies_and_preserves_independent_radar_on_restart(self):
        for token, quote in ((OTHER, SOL), (SOL, OTHER)):
            with self.subTest(token=token):
                pool = self.capture.observation.pool
                at = self.capture.observation.available_at
                launch = IntegratedRadarEvent(
                    id="fixture-launch", radar="launch", event_type="POOL_INITIALIZATION",
                    origin="FIXTURE_OFFLINE", source_id="fixture", provider=None,
                    signature=None, slot=self.original_slot - 1, pool=pool,
                    observed_at=at.isoformat(), available_at=at.isoformat(),
                    raw_sha256=None, raw_identity=None, coverage="UNKNOWN",
                    evidence_quality="UNKNOWN", verdict="UNKNOWN", direction=None,
                    reasons=(), source_reference="fixture-launch", token_mints=(token, quote),
                )
                smart = replace(
                    launch, id="fixture-smart", radar="smart_money", event_type="SWAP",
                    direction="BUY", source_reference="fixture-smart",
                    input_mint=quote, output_mint=token,
                )
                scope = IntelligenceScope(
                    token_mint=token, quote_mint=quote, min_liquidity_quote=Decimal("1"),
                    max_concentration_fraction=Decimal("0.4"),
                    launch_scenarios=LaunchModelScenarios(
                        buy_amount_in=Decimal("1"), sell_amount_in=Decimal("2"),
                        buy_amount_out=Decimal("3"), sell_amount_out=Decimal("4"),
                    ),
                )
                path = Path(self.temp.name) / f"{token}.sqlite"
                now = archived.CUTOFF.timestamp()
                with (
                    patch("smart_money_radar.services.persistent_supervisor.launch_events_from_archive",
                          return_value=[launch]),
                    patch("smart_money_radar.services.persistent_supervisor.smart_money_events_from_archive",
                          return_value=[smart]),
                ):
                    first = self.run_cycle(path, pool, scope, now, start=True)
                    self.assertEqual(self.run_cycle(path, pool, scope, now + 10, start=False), first)

                self.assertEqual(set(first), {"launch", "smart_money"})
                smart_decision = json.loads(first["smart_money"][0])["decision"]
                self.assertNotIn("economic_qualification", smart_decision)
                self.assertFalse(smart_decision["operational_authorized"])
                decision = json.loads(first["launch"][0])["decision"]
                self.assertFalse(decision["operational_authorized"])
                modes = decision["economic_qualification"]
                self.assertEqual(set(modes), {"immediate", "confirmed"})
                for mode, qualification in modes.items():
                    with self.subTest(mode=mode):
                        archive = qualification["account_archive"]
                        self.assertEqual(archive["capture_id"], self.capture.capture_id)
                        self.assertIn("buy_model", archive)
                        self.assertIn("sell_model", archive)
                        for key, expected in EXPECTED[quote].items():
                            model = archive[key]
                            input_mint, output_mint = (quote, token) if key.startswith("buy") else (token, quote)
                            self.assertEqual(model["status"], "MODEL_ESTIMATE")
                            self.assertEqual(model["mode"], "EXACT_OUTPUT" if "exact_output" in key else "EXACT_INPUT")
                            self.assertEqual((model["input_mint"], model["output_mint"]), (input_mint, output_mint))
                            self.assertEqual(model["creator_fee_on_input"], input_mint == SOL)
                            self.assertEqual(tuple(model[name] for name in AMOUNT_KEYS), tuple(map(str, expected)))
                            self.assertEqual(model["fee_provenance"], "POOL_AND_AMM_CONFIG_LOCAL_BYTES")
                            self.assertEqual(model["creator_fee_mode"], 1)
                            self.assertTrue(model["creator_fee_enabled"])
                            self.assertFalse(model["operational_authorized"])

    def run_cycle(self, path, pool, scope, now, *, start):
        store = SQLiteEventStore(path)
        history = SQLiteCpmmProspectiveHistory(self.archive_path, read_only=True)
        try:
            if start:
                capability = b"cm70-offline-journal-test-capability"
                controls = LocalOperationalControls(store, operator_capability=capability)
                for radar in ("launch", "smart_money"):
                    controls.apply(
                        capability=capability, event_id=f"start-{radar}", radar=radar,
                        action="START", actor="fixture", at=archived.CUTOFF,
                        reason="offline fixture",
                    )
            runner = PersistentSupervisor(
                store, clock=lambda: now, launch_history=history,
                scopes={("launch", pool): scope},
            )
            runner.acquire()
            try:
                result = runner.cycle()
                self.assertFalse(result["execution_enabled"])
                for task in result["tasks"].values():
                    self.assertEqual(task["status"], "READY")
                    self.assertEqual(task["processed_new"], int(start))
            finally:
                runner.stop()
        finally:
            history.close()
            store.close()
        with sqlite3.connect(path) as conn:
            return {
                radar: (payload, digest)
                for radar, payload, digest in conn.execute(
                    "SELECT radar, payload, payload_sha FROM cm36_decision_journal"
                )
            }

    def test_unavailable_and_conflicting_capture_cannot_produce_integer_model(self):
        history = SQLiteCpmmProspectiveHistory(self.archive_path)
        self.addCleanup(history.close)
        args = dict(
            token_mint=OTHER, quote_mint=SOL, pool=self.capture.observation.pool,
            strategy="confirmed", cpmm_history=history, amount_in=Decimal("1"),
        )
        before = self.capture.observation.available_at - timedelta(microseconds=1)
        receipt = launch_metric_receipts(**args, at=before)
        self.assertNotIn("buy_integer_model", receipt["economic_qualification"]["account_archive"])
        self.assertFalse(receipt["operational_authorized"])

        with history.connection:
            history.connection.execute(
                "UPDATE prospective_cpmm_captures SET slot=slot+1 WHERE capture_id=?",
                (self.capture.capture_id,),
            )
        receipt = launch_metric_receipts(**args, at=archived.CUTOFF)
        archive = receipt["economic_qualification"]["account_archive"]
        self.assertEqual(archive["status"], "CONFLICTED")
        self.assertNotIn("buy_integer_model", archive)
        self.assertFalse(receipt["operational_authorized"])

    def test_cli_passes_explicit_scenarios_and_opens_archive_read_only(self):
        path = Path(self.temp.name) / "cli.sqlite"
        pool = self.capture.observation.pool
        with (
            patch("smart_money_radar.services.persistent_supervisor.PersistentSupervisor") as runner,
            patch("smart_money_radar.storage.cpmm_prospective_history.SQLiteCpmmProspectiveHistory",
                  wraps=SQLiteCpmmProspectiveHistory) as history,
        ):
            cli.main([
                "supervisor-offline", str(path), "--launch-history", str(self.archive_path),
                "--launch-scope", pool, OTHER, SOL,
                "--launch-buy-in", "1.25", "--launch-sell-out", "0.5",
            ])
        history.assert_called_once_with(self.archive_path, read_only=True)
        self.assertEqual(set(runner.call_args.kwargs["scopes"]), {("launch", pool)})
        scope = runner.call_args.kwargs["scopes"][("launch", pool)]
        self.assertEqual((scope.token_mint, scope.quote_mint), (OTHER, SOL))
        self.assertEqual(scope.launch_scenarios, LaunchModelScenarios(
            buy_amount_in=Decimal("1.25"), sell_amount_out=Decimal("0.5"),
        ))
        self.assertEqual(runner.return_value.run.call_args.kwargs["max_cycles"], 1)
        archive_handle = runner.call_args.kwargs["launch_history"]
        with self.assertRaises(sqlite3.ProgrammingError):
            archive_handle.connection.execute("SELECT 1")

    def test_cli_rejects_amount_without_scope_and_history_before_opening_db(self):
        path = Path(self.temp.name) / "unopened.sqlite"
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["supervisor-offline", str(path), "--launch-buy-in", "1"])
        self.assertFalse(path.exists())
