"""CM74 safety checks for detached Android dashboard launcher."""

import os
import shutil
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


if __name__ == "__main__":
    unittest.main()
