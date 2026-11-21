"""CM74 periodic Android watchdog safety tests."""
import os
import fcntl
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "loop_smr_dashboard_watchdog_android.sh"


@unittest.skipUnless(shutil.which("bash"), "bash required")
class PeriodicDashboardWatchdogTests(unittest.TestCase):
    def run_script(self, env):
        return subprocess.run(
            ["bash", str(SCRIPT)], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=10,
        )

    def test_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_interval_fails_before_state_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            env = os.environ.copy()
            env.update(SMR_DASHBOARD_WATCH_INTERVAL="0", SMR_DASHBOARD_STATE_DIR=str(state))
            result = self.run_script(env)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(state.exists())

    def test_invalid_failure_budget_fails_before_state_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            env = os.environ.copy()
            env.update(SMR_DASHBOARD_WATCH_MAX_FAILURES="0", SMR_DASHBOARD_STATE_DIR=str(state))
            result = self.run_script(env)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(state.exists())

    @unittest.skipUnless(shutil.which("flock"), "flock required")
    def test_second_watchdog_is_rejected_by_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir()
            database = Path(tmp) / "existing.sqlite"
            database.touch()
            with (state / "watchdog.lock").open("w") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                env = os.environ.copy()
                env.update(SMR_DB_PATH=str(database), SMR_DASHBOARD_STATE_DIR=str(state))
                result = self.run_script(env)
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIn("já ativo", result.stderr)

    def test_missing_database_does_not_create_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            env = os.environ.copy()
            env.update(
                SMR_DB_PATH=str(Path(tmp) / "absent.sqlite"),
                SMR_DASHBOARD_STATE_DIR=str(state),
            )
            result = self.run_script(env)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
