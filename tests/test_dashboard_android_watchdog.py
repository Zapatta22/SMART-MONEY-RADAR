"""Offline safety tests for the CM74 one-shot Android dashboard watchdog."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "watch_smr_dashboard_android.sh"


@unittest.skipUnless(shutil.which("bash"), "bash required")
class DashboardWatchdogTests(unittest.TestCase):
    def test_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_database_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.sqlite"
            env = os.environ.copy()
            env["SMR_DB_PATH"] = str(missing)
            result = subprocess.run(
                ["bash", str(SCRIPT)], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(missing.exists())

    def test_healthy_local_endpoint_does_not_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "existing.sqlite"
            database.touch()
            fakebin = Path(tmp) / "bin"
            fakebin.mkdir()
            fakecurl = fakebin / "curl"
            fakecurl.write_text("#!/bin/sh" + chr(10) + "exit 0" + chr(10))
            fakecurl.chmod(0o700)
            env = os.environ.copy()
            env.update(SMR_DB_PATH=str(database), PATH=str(fakebin) + os.pathsep + env.get("PATH", ""))
            result = subprocess.run(
                ["bash", str(SCRIPT)], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("nenhuma ação", result.stdout)


if __name__ == "__main__":
    unittest.main()
