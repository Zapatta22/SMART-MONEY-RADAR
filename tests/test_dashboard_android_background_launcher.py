"""CM74 safety checks for detached Android dashboard launcher."""

import os
import fcntl
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "start_smr_dashboard_background_android.sh"


@unittest.skipUnless(shutil.which("bash"), "bash required")
class BackgroundDashboardLauncherTests(unittest.TestCase):
    def test_bash_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_background_child_closes_startup_lock_descriptor(self):
        source = SCRIPT.read_text()
        self.assertIn('exec 9>"$STATE/startup.lock"', source)
        self.assertIn('</dev/null 9>&- &', source)

    def test_missing_database_is_rejected_without_creating_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "absent.sqlite"
            state = Path(tmp) / "state"
            env = os.environ.copy()
            env.update(SMR_DB_PATH=str(missing), SMR_DASHBOARD_STATE_DIR=str(state))
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("SMR_DB_PATH", result.stderr)
            self.assertFalse(missing.exists())
            self.assertFalse(state.exists())

    def test_missing_environment_database_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.pop("SMR_DB_PATH", None)
            env["SMR_DASHBOARD_STATE_DIR"] = str(Path(tmp) / "state")
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("SMR_DB_PATH", result.stderr)
            self.assertFalse(Path(tmp, "state").exists())


    def test_incomplete_database_does_not_start_dashboard_or_migrate(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "incomplete.sqlite"
            state = Path(tmp) / "state"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE unrelated (id INTEGER)")
            env = os.environ.copy()
            env.update(SMR_DB_PATH=str(database), SMR_DASHBOARD_STATE_DIR=str(state))
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ERRO", (state / "dashboard.log").read_text())
            self.assertNotIn("TOKEN TEMPORÁRIO", result.stdout)
            with sqlite3.connect(database) as connection:
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
            self.assertEqual(tables, {"unrelated"})


    def test_active_pid_without_http_does_not_spawn_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "existing.sqlite"
            database.touch()
            state = Path(tmp) / "state"
            state.mkdir()
            (state / "dashboard.pid").write_text(str(os.getpid()) + chr(10))
            fakebin = Path(tmp) / "bin"
            fakebin.mkdir()
            fakecurl = fakebin / "curl"
            fakecurl.write_text("#!/bin/sh" + chr(10) + "exit 7" + chr(10))
            fakecurl.chmod(0o700)
            env = os.environ.copy()
            env.update(
                SMR_DB_PATH=str(database),
                SMR_DASHBOARD_STATE_DIR=str(state),
                PATH=str(fakebin) + os.pathsep + env.get("PATH", ""),
            )
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn("ainda ativo", result.stderr)
            self.assertFalse((state / "dashboard.log").exists())


    def test_stale_pid_is_removed_before_launch_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "existing.sqlite"
            database.touch()
            state = Path(tmp) / "state"
            state.mkdir()
            pidfile = state / "dashboard.pid"
            pidfile.write_text("999999999" + chr(10))
            fakebin = Path(tmp) / "bin"
            fakebin.mkdir()
            fakecurl = fakebin / "curl"
            fakecurl.write_text("#!/bin/sh" + chr(10) + "exit 7" + chr(10))
            fakecurl.chmod(0o700)
            env = os.environ.copy()
            env.update(
                SMR_DB_PATH=str(database),
                SMR_DASHBOARD_STATE_DIR=str(state),
                PATH=str(fakebin) + os.pathsep + env.get("PATH", ""),
            )
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertNotEqual(result.returncode, 3, result.stderr)
            self.assertNotEqual(pidfile.read_text().strip(), "999999999")


    @unittest.skipUnless(shutil.which("flock"), "flock required")
    def test_concurrent_startup_lock_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "existing.sqlite"
            database.touch()
            state = Path(tmp) / "state"
            state.mkdir()
            lock = state / "startup.lock"
            with lock.open("w") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                env = os.environ.copy()
                env.update(SMR_DB_PATH=str(database), SMR_DASHBOARD_STATE_DIR=str(state))
                result = subprocess.run(
                    ["bash", str(SCRIPT)],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIn("outra inicialização", result.stderr)
                self.assertFalse((state / "dashboard.pid").exists())


if __name__ == "__main__":
    unittest.main()
