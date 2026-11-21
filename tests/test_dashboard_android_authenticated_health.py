"""CM74 authenticated health probe: fail closed without a private token."""
import os
import subprocess
import sys
import tempfile
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "check_smr_dashboard_health.py"


class AuthenticatedHealthProbeTests(unittest.TestCase):
    def run_probe(self, state):
        env = os.environ.copy()
        env["SMR_DASHBOARD_STATE_DIR"] = str(state)
        return subprocess.run([sys.executable, str(PROBE)], env=env, capture_output=True, text=True, timeout=10)

    def test_authenticated_local_http_health_end_to_end(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/health" or self.headers.get("Authorization") != "Bearer " + "a" * 64:
                    self.send_response(401)
                    self.end_headers()
                    return
                payload = json.dumps({"status": "ok", "mode": "read_only"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir(mode=0o700)
            token = state / "health.token"
            token.write_text("a" * 64 + "\n")
            token.chmod(0o600)
            try:
                server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
            except OSError as exc:
                self.skipTest(f"port 8765 unavailable: {exc}")
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = self.run_probe(state)
                self.assertEqual(result.returncode, 0, result.stderr)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

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
