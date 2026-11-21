"""Offline supervisor lock handling and bounded Android-compatible soak checks."""

import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
from unittest.mock import patch

from smart_money_radar.services.operational_controls import LocalOperationalControls
from smart_money_radar.services.persistent_supervisor import (
    PersistentSupervisor,
    SupervisorPolicy,
    read_supervisor_status,
)
from smart_money_radar.storage.event_store import SQLiteEventStore
from tools.benchmark_cm36_supervisor import measure


class SupervisorRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "supervisor.sqlite"
        self.store = SQLiteEventStore(self.path)
        self.addCleanup(self.store.close)
        self.now = datetime(2026, 11, 21, tzinfo=timezone.utc)
        key = b"test-local-control" * 2
        controls = LocalOperationalControls(self.store, operator_capability=key)
        for radar in ("launch", "smart_money"):
            controls.apply(
                capability=key, event_id=f"start-{radar}", action="START",
                radar=radar, actor="test", reason="offline test", at=self.now,
            )
        self.runner = PersistentSupervisor(
            self.store,
            policy=SupervisorPolicy(lease_seconds=2, interval_seconds=0.2),
            clock=self.now.timestamp,
        )
        self.lock = sqlite3.connect(self.path)
        self.addCleanup(self.lock.close)

    def test_retries_only_contended_radar_after_first_radar_commits(self):
        stop = Event()
        calls = []
        original_step = self.runner.step

        def step(radar):
            if radar == "smart_money" and radar not in calls:
                self.lock.execute("BEGIN IMMEDIATE")
            calls.append(radar)
            return original_step(radar)

        def unlock(_):
            self.lock.rollback()
            return False

        with patch.object(self.runner, "step", side_effect=step), patch.object(
            stop, "wait", side_effect=unlock,
        ) as wait:
            self.assertEqual(self.runner.run(stop, max_cycles=1), 1)
        self.assertEqual(calls, ["launch", "smart_money", "smart_money"])
        wait.assert_called_once()
        status = read_supervisor_status(self.store, now=self.now.timestamp())
        self.assertEqual(status["status"], "STOPPED")
        self.assertEqual(
            {radar: (task["cycles"], task["failures"]) for radar, task in status["radars"].items()},
            {"launch": (1, 0), "smart_money": (1, 0)},
        )

    def test_sustained_write_lock_ends_with_sqlite_error_and_no_lease(self):
        self.lock.execute("BEGIN IMMEDIATE")
        started = monotonic()
        with self.assertRaises(sqlite3.OperationalError) as raised:
            self.runner.run(Event(), max_cycles=1)
        elapsed = monotonic() - started
        self.assertEqual(raised.exception.sqlite_errorcode & 0xFF, sqlite3.SQLITE_BUSY)
        self.assertLess(elapsed, 2.0)
        self.lock.rollback()
        self.assertEqual(read_supervisor_status(self.store)["status"], "NOT_STARTED")

    def test_stop_signal_during_lock_wait_preserves_completed_peer(self):
        stop = Event()
        calls = []
        original_step = self.runner.step

        def step(radar):
            calls.append(radar)
            if radar == "smart_money":
                self.lock.execute("BEGIN IMMEDIATE")
            return original_step(radar)

        def cancel(_):
            stop.set()
            self.lock.rollback()
            return True

        with patch.object(self.runner, "step", side_effect=step), patch.object(
            stop, "wait", side_effect=cancel,
        ):
            self.assertEqual(self.runner.run(stop, max_cycles=1), 0)
        self.assertEqual(calls, ["launch", "smart_money"])
        status = read_supervisor_status(self.store, now=self.now.timestamp())
        self.assertEqual(status["status"], "STOPPED")
        self.assertEqual(status["radars"]["launch"]["cycles"], 1)
        self.assertEqual(status["radars"]["smart_money"]["cycles"], 0)

    def test_extended_busy_code_retries_but_non_lock_error_is_not_retried(self):
        extended_busy = sqlite3.OperationalError("busy snapshot")
        extended_busy.sqlite_errorcode = sqlite3.SQLITE_BUSY_SNAPSHOT
        broken = sqlite3.OperationalError("database is locked")
        broken.sqlite_errorcode = sqlite3.SQLITE_IOERR
        stop = Event()
        with patch.object(
            self.runner, "acquire", side_effect=[extended_busy, broken]
        ) as acquire:
            with self.assertRaises(sqlite3.OperationalError) as raised:
                self.runner.run(stop, max_cycles=1)
        self.assertIs(raised.exception, broken)
        self.assertEqual(acquire.call_count, 2)

    def test_cleanup_error_keeps_original_failure(self):
        with patch.object(self.runner, "cycle", side_effect=ValueError("cycle failed")), patch.object(
            self.runner, "stop", side_effect=sqlite3.OperationalError("shutdown failed"),
        ):
            with self.assertRaisesRegex(ValueError, "cycle failed") as raised:
                self.runner.run(Event(), max_cycles=1)
        self.assertIn("supervisor shutdown SQLite error: shutdown failed", raised.exception.__notes__)

    def test_cleanup_error_propagates_inside_unrelated_exception_handler(self):
        with patch.object(self.runner, "stop", side_effect=sqlite3.OperationalError("shutdown failed")):
            try:
                raise ValueError("unrelated caller error")
            except ValueError:
                with self.assertRaisesRegex(sqlite3.OperationalError, "shutdown failed"):
                    self.runner.run(Event(), max_cycles=1)


class SupervisorSoakTests(unittest.TestCase):
    def test_accelerated_soak_reopens_one_archive_and_preserves_each_radar_count(self):
        result = measure(cycles=5, restart_every=2, max_wall_seconds=10)
        self.assertEqual(result["completion"], "CYCLE_LIMIT")
        self.assertEqual(result["cycles_by_radar"], {"launch": 5, "smart_money": 5})
        self.assertEqual((result["restarts"], result["last_generation"]), (2, 3))
        self.assertEqual(result["sqlite_integrity"], ["ok"])
        self.assertFalse(result["autonomy_24h_verified"])

    def test_wall_limit_allows_zero_completed_cycles(self):
        result = measure(cycles=5, max_wall_seconds=1e-9, realtime=True)
        self.assertEqual(result["completion"], "WALL_TIME_LIMIT")
        self.assertEqual(result["cycles_by_radar"], {"launch": 0, "smart_money": 0})
        self.assertEqual(result["sqlite_integrity"], ["ok"])
        self.assertIsNone(result["cycle_mean_ms"])
