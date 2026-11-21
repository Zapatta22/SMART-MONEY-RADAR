"""Offline host validation of the physical Android soak runner."""

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from smart_money_radar.storage.event_store import SQLiteEventStore
from tools import smr_android_soak as soak
from tools.verify_smr_android_soak import verify as verify_soak

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "tools" / "run_smr_android_soak.sh"


class AndroidSoakTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name)
        self.production = self.output / "outside.sqlite"
        with closing(sqlite3.connect(self.production)) as database, database:
            database.execute("CREATE TABLE production_marker (value TEXT)")
            database.execute("INSERT INTO production_marker VALUES ('untouched')")
        self.original = self.production.read_bytes()

    def start(self, duration, max_restarts=5):
        process = subprocess.Popen(
            [
                "bash", str(LAUNCHER), "--output-dir", str(self.output),
                "--duration-seconds", str(duration), "--interval-seconds", "0.1",
                "--max-restarts", str(max_restarts),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "SMR_DB_PATH": str(self.production),
                 "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]},
        )

        def cleanup():
            if process.poll() is None:
                process.terminate()
            try:
                process.communicate(timeout=7)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()

        self.addCleanup(cleanup)
        return process

    def workspace(self):
        (workspace,) = self.output.glob("smr-soak-*")
        return workspace

    def report(self, process, exit_code):
        stdout, stderr = process.communicate(timeout=8)
        if process.returncode != exit_code:
            reports = list(self.output.glob("smr-soak-*/report.json"))
            diagnostics = [p.read_text() for p in reports]
            self.fail(f"soak exit {process.returncode}, expected {exit_code}: {(stdout, stderr)}; reports={diagnostics}")
        workspace = self.workspace()
        self.assertEqual(workspace.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.production.read_bytes(), self.original)
        self.assertTrue((workspace / "worker.log").is_file())
        self.assertTrue((workspace / "offline-soak.sqlite").is_file())
        report = json.loads((workspace / "report.json").read_text())
        self.assertFalse(report["physical_android_verified"])
        self.assertFalse(report["autonomy_24h_verified"])
        self.assertFalse(report["target_24h_reached"])
        self.assertFalse(report["supervisor"]["execution_enabled"])
        self.assertFalse(report["supervisor"]["live_authorized"])
        return report

    def wait_for_worker(self, process):
        deadline = time.monotonic() + 3
        while process.poll() is None and time.monotonic() < deadline:
            for workspace in self.output.glob("smr-soak-*"):
                path = workspace / "worker.log"
                if path.is_file():
                    for line in path.read_text().splitlines():
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if entry.get("event") == "worker_started":
                            return entry["pid"]
            time.sleep(0.025)
        self.fail("offline soak worker did not start")

    def test_short_run_produces_local_report_and_progress_for_both_radars(self):
        # Allow the CI runner to initialize Python/SQLite before the deadline.
        process = self.start(2.0)
        report = self.report(process, 0)
        self.assertEqual(report["outcome"], "COMPLETED")
        self.assertGreaterEqual(report["elapsed_seconds"], 2.0)
        self.assertEqual(report["sqlite_integrity"], ["ok"])
        self.assertEqual(report["supervisor"]["lease"], "STOPPED")
        self.assertEqual(set(report["supervisor"]["radars"]), {"launch", "smart_money"})
        self.assertTrue(all(r["cycles"] >= 1 for r in report["supervisor"]["radars"].values()))
        progress = [
            json.loads(line) for line in (self.workspace() / "progress.jsonl").read_text().splitlines()
        ]
        self.assertEqual(progress[0]["event"], "started")
        self.assertEqual(progress[-1]["event"], "finished")

    def test_offline_evidence_gate_accepts_completed_soak_and_rejects_tampering(self):
        process = self.start(2.0)
        self.report(process, 0)
        workspace = self.workspace()
        accepted = verify_soak(workspace)
        self.assertTrue(accepted["accepted_offline"], accepted["issues"])
        self.assertFalse(accepted["physical_android_verified"])
        self.assertFalse(accepted["autonomy_24h_verified"])
        report_path = workspace / "report.json"
        report = json.loads(report_path.read_text())
        report["supervisor"]["radars"]["launch"]["cycles"] += 1
        report_path.write_text(json.dumps(report))
        rejected = verify_soak(workspace)
        self.assertFalse(rejected["accepted_offline"])
        self.assertIn("launch persisted cycles disagree with final report", rejected["issues"])

    def test_offline_evidence_gate_rejects_journal_report_disagreement(self):
        process = self.start(2.0)
        self.report(process, 0)
        workspace = self.workspace()
        journal = workspace / "progress.jsonl"
        entries = [json.loads(line) for line in journal.read_text().splitlines()]
        entries[-1]["radars"]["launch"]["cycles"] += 1
        journal.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
        rejected = verify_soak(workspace)
        self.assertFalse(rejected["accepted_offline"])
        self.assertIn("journal radar checkpoints disagree with report", rejected["issues"])

    def test_offline_evidence_gate_rejects_unhealthy_radar_and_short_duration(self):
        process = self.start(2.0)
        self.report(process, 0)
        workspace = self.workspace()
        report_path = workspace / "report.json"
        report = json.loads(report_path.read_text())
        report["supervisor"]["radars"]["launch"]["failures"] = 1
        report["elapsed_seconds"] = 0.5
        report_path.write_text(json.dumps(report))
        rejected = verify_soak(workspace)
        self.assertFalse(rejected["accepted_offline"])
        self.assertIn("launch final state is not healthy", rejected["issues"])
        self.assertIn("offline soak target duration not reached", rejected["issues"])

    def test_offline_evidence_gate_rejects_empty_worker_log(self):
        process = self.start(2.0)
        self.report(process, 0)
        workspace = self.workspace()
        (workspace / "worker.log").write_text("")
        rejected = verify_soak(workspace)
        self.assertFalse(rejected["accepted_offline"])
        self.assertIn("empty offline worker log", rejected["issues"])

    def test_offline_evidence_gate_rejects_artifact_manifest_tampering(self):
        process = self.start(2.0)
        self.report(process, 0)
        workspace = self.workspace()
        report_path = workspace / "report.json"
        report = json.loads(report_path.read_text())
        report["artifacts"]["sqlite"] = "../outside.sqlite"
        report_path.write_text(json.dumps(report))
        rejected = verify_soak(workspace)
        self.assertFalse(rejected["accepted_offline"])
        self.assertIn("unexpected offline artifact manifest", rejected["issues"])

    def test_offline_evidence_gate_rejects_false_24h_completion(self):
        process = self.start(2.0)
        self.report(process, 0)
        workspace = self.workspace()
        report_path = workspace / "report.json"
        report = json.loads(report_path.read_text())
        report["target_24h_reached"] = True
        report_path.write_text(json.dumps(report))
        rejected = verify_soak(workspace)
        self.assertFalse(rejected["accepted_offline"])
        self.assertIn("inconsistent 24-hour target claim", rejected["issues"])

    def test_offline_evidence_gate_rejects_checkpoint_hash_tampering(self):
        process = self.start(2.0)
        self.report(process, 0)
        workspace = self.workspace()
        import sqlite3
        with sqlite3.connect(workspace / "offline-soak.sqlite") as conn:
            conn.execute("UPDATE cm36_supervisor_tasks SET payload_sha=? WHERE radar=?",
                         ("0" * 64, "launch"))
        rejected = verify_soak(workspace)
        self.assertFalse(rejected["accepted_offline"])
        self.assertIn("launch persisted checkpoint hash mismatch", rejected["issues"])

    def test_offline_evidence_gate_rejects_lease_digest_tampering(self):
        process = self.start(2.0)
        self.report(process, 0)
        workspace = self.workspace()
        import sqlite3
        with sqlite3.connect(workspace / "offline-soak.sqlite") as conn:
            conn.execute("UPDATE cm36_supervisor_lease SET payload_sha=? WHERE singleton=1",
                         ("0" * 64,))
        rejected = verify_soak(workspace)
        self.assertFalse(rejected["accepted_offline"])
        self.assertIn("persisted supervisor lease hash mismatch", rejected["issues"])

    def test_offline_evidence_gate_rejects_missing_progress_journal(self):
        process = self.start(2.0)
        self.report(process, 0)
        workspace = self.workspace()
        (workspace / "progress.jsonl").unlink()
        rejected = verify_soak(workspace)
        self.assertFalse(rejected["accepted_offline"])
        self.assertIn("missing progress journal", rejected["issues"])

    def test_offline_evidence_gate_rejects_missing_sqlite_archive(self):
        process = self.start(2.0)
        self.report(process, 0)
        workspace = self.workspace()
        (workspace / "offline-soak.sqlite").unlink()
        rejected = verify_soak(workspace)
        self.assertFalse(rejected["accepted_offline"])
        self.assertIn("missing offline SQLite archive", rejected["issues"])

    def test_worker_crash_reopens_same_archive_after_fenced_lease_expires(self):
        process = self.start(4.5, max_restarts=2)
        worker = self.wait_for_worker(process)
        deadline = time.monotonic() + 1.5
        source = self.workspace() / "offline-soak.sqlite"
        while time.monotonic() < deadline:
            with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as database:
                if database.execute("SELECT count(*) FROM cm36_supervisor_tasks").fetchone()[0] == 2:
                    break
            time.sleep(0.025)
        else:
            self.fail("first worker did not persist both radar checkpoints")
        os.kill(worker, signal.SIGKILL)
        report = self.report(process, 0)
        self.assertEqual(report["outcome"], "COMPLETED")
        self.assertEqual(report["worker_restarts"], 1)
        self.assertEqual(report["worker_exit_codes"], [-signal.SIGKILL, 0])
        self.assertEqual(report["supervisor"]["generation"], 2)
        self.assertTrue(all(r["cycles"] > 1 for r in report["supervisor"]["radars"].values()))
        self.assertEqual(report["sqlite_integrity"], ["ok"])
        # The resumed generation must persist progress for both independent radars
        # in the same archive, not merely return a successful process exit.
        with closing(sqlite3.connect(self.workspace() / "offline-soak.sqlite")) as db:
            rows = db.execute(
                "SELECT radar, payload FROM cm36_supervisor_tasks"
            ).fetchall()
        self.assertEqual({radar for radar, _ in rows}, {"launch", "smart_money"})
        self.assertTrue(all(json.loads(payload)["cycles"] > 1 for _, payload in rows))

    def test_controller_termination_writes_interrupted_report(self):
        process = self.start(5)
        self.wait_for_worker(process)
        process.terminate()
        report = self.report(process, 130)
        self.assertEqual(report["outcome"], "INTERRUPTED")
        self.assertEqual(report["worker_exit_codes"], [0])
        self.assertEqual(report["sqlite_integrity"], ["ok"])

    def test_restart_budget_exhaustion_finishes_with_explicit_failure(self):
        process = self.start(5, max_restarts=0)
        worker = self.wait_for_worker(process)
        os.kill(worker, signal.SIGKILL)
        report = self.report(process, 1)
        self.assertEqual(report["outcome"], "FAILED")
        self.assertEqual(report["failure"], "worker restart limit reached")
        self.assertEqual(report["worker_restarts"], 0)

    def test_malformed_monitoring_and_final_sqlite_error_still_write_failed_report(self):
        store = SQLiteEventStore(self.output / "fixture.sqlite")
        self.addCleanup(store.close)
        with (self.output / "progress.jsonl").open("w") as journal, (
            self.output / "worker.log"
        ).open("ab") as worker_log, patch.object(
            soak, "read_supervisor_status", side_effect=[
                {"status": "ACTIVE", "radars": [], "live_authorized": False,
                 "execution_enabled": False},
                sqlite3.DatabaseError("fixture probe failed"),
            ],
        ):
            report = soak._monitor(self.output, store, journal, worker_log, Event(), 1, 0.1, 0)
        soak._write_report(self.output, report)
        report = json.loads((self.output / "report.json").read_text())
        self.assertEqual(report["outcome"], "FAILED")
        self.assertEqual(report["supervisor"]["lease"], "CONFLICTED")
        self.assertEqual(report["supervisor"]["probe_error"], "fixture probe failed")
        self.assertFalse(report["supervisor"]["live_authorized"])
        self.assertFalse(report["supervisor"]["execution_enabled"])

    def test_exhausted_restart_budget_precedes_conflicted_snapshot(self):
        """A dead worker with zero restarts must fail without reacquiring a lease."""
        class DeadWorker:
            pid = 43210
            returncode = -signal.SIGKILL

            def poll(self):
                return self.returncode

        store = SQLiteEventStore(self.output / "race.sqlite")
        self.addCleanup(store.close)
        snapshot = {"lease": "CONFLICTED", "radars": {},
                    "live_authorized": False, "execution_enabled": False}
        with (self.output / "progress.jsonl").open("w") as journal, (
            self.output / "worker.log"
        ).open("ab") as worker_log, patch.object(
            soak, "_spawn_worker", return_value=DeadWorker()
        ), patch.object(soak, "_runtime_snapshot", side_effect=[
            {"lease": "NOT_STARTED", "radars": {},
             "live_authorized": False, "execution_enabled": False},
            snapshot, snapshot,
        ]):
            report = soak._monitor(
                self.output, store, journal, worker_log, Event(), 1, 0.1, 0
            )
        self.assertEqual(report["outcome"], "FAILED")
        self.assertEqual(report["failure"], "worker restart limit reached")
        self.assertEqual(report["worker_exit_codes"], [-signal.SIGKILL])
        self.assertEqual(report["worker_restarts"], 0)

    def test_internal_worker_rejects_nonfinite_deadline_before_opening_sqlite(self):
        with self.assertRaisesRegex(ValueError, "invalid offline soak deadline"):
            soak._worker(self.output, os.getppid(), float("nan"), 0.1)
