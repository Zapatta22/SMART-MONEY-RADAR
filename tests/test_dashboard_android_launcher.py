"""Safety checks for the Android dashboard launcher."""

import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "run_smr_dashboard_android.sh"


@unittest.skipUnless(shutil.which("bash"), "bash is required for launcher tests")
class DashboardAndroidLauncherTests(unittest.TestCase):
    def test_launcher_has_valid_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.sqlite3"
            env = os.environ.copy()
            env["SMR_DB_PATH"] = str(missing)
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("não encontrado", result.stderr)
            self.assertFalse(missing.exists())

    def test_incomplete_database_is_not_migrated(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "old.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE unrelated (id INTEGER)")
            env = os.environ.copy()
            env["SMR_DB_PATH"] = str(database)
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Tabelas ausentes", result.stderr)
            with sqlite3.connect(database) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            self.assertEqual(tables, {"unrelated"})


if __name__ == "__main__":
    unittest.main()
