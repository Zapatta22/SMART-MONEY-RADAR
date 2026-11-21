"""CM74 authenticated health probe: fail closed without a private token."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "check_smr_dashboard_health.py"


class AuthenticatedHealthProbeTests(unittest.TestCase):
    def run_probe(self, state):
        env = os.environ.copy()
        env["SMR_DASHBOARD_STATE_DIR"] = str(state)
        return subprocess.run([sys.executable, str(PROBE)], env=env, capture_output=True, text=True, timeout=10)

    def test_missing_token_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_probe(Path(tmp)).returncode, 1)

    def test_world_readable_token_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "health.token"
            token.write_text("a" * 64)
            token.chmod(0o644)
            self.assertEqual(self.run_probe(Path(tmp)).returncode, 1)

    def test_world_readable_state_directory_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "health.token"
            token.write_text("a" * 64)
            token.chmod(0o600)
            Path(tmp).chmod(0o755)
            self.assertEqual(self.run_probe(Path(tmp)).returncode, 1)

    def test_symlink_token_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "secret"
            target.write_text("a" * 64)
            target.chmod(0o600)
            (Path(tmp) / "health.token").symlink_to(target)
            self.assertEqual(self.run_probe(Path(tmp)).returncode, 1)


if __name__ == "__main__":
    unittest.main()
