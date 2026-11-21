"""Offline-only CM27 termination and immutable-ref security tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json,sqlite3,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from cm27_finalize_manifest import finalize

ROOT=Path(__file__).resolve().parents[1]
class Cm27GateOffline(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory();self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.out=self.root/"evidence";self.out.mkdir()
        self.lock=ROOT/"requirements/cm27-live-linux-py312.lock"
        self.script=self.root/"capture.py";self.script.write_text("# fixture")
    def do(self):return finalize(self.out,"4"*40,self.lock,self.script)
    def test_interruption_without_any_artifacts_creates_incomplete_manifest(self):
        r=self.do()
        self.assertEqual(r["status"],"FAILED_OR_INCOMPLETE")
        self.assertEqual(r["capture_exit_code"],"MISSING")
        self.assertFalse(r["manifest_completed"])
        self.assertEqual(json.loads((self.out/"manifest.json").read_text())["coverage"],"UNKNOWN")
        self.assertTrue((self.out/"termination.json").exists())
    def test_timeout_with_partial_sqlite_never_promotes_success(self):
        sqlite3.connect(self.out/"geyser-raw.sqlite").close()
        (self.out/"capture_exit_code.txt").write_text("124")
        (self.out/"manifest.json").write_text(json.dumps({"runtime":"real_solana_public_rpc_websocket","coverage":"UNKNOWN","financial_execution_authorized":False}))
        r=self.do()
        self.assertEqual(r["status"],"FAILED_OR_INCOMPLETE")
        self.assertTrue((self.out/"partial-manifest.json").exists())
    def test_success_requires_complete_manifest_and_integrity(self):
        sqlite3.connect(self.out/"geyser-raw.sqlite").close()
        (self.out/"capture_exit_code.txt").write_text("0")
        (self.out/"manifest.json").write_text(json.dumps({"runtime":"real_solana_public_rpc_websocket","coverage":"UNKNOWN","financial_execution_authorized":False}))
        r=self.do()
        self.assertEqual(r["status"],"COMPLETED_CAPTURE_WITH_UNPROVEN_COVERAGE")
        self.assertFalse(r["live_homologation"])
        self.assertEqual(json.loads((self.out/"manifest.json").read_text())["runtime"],"real_solana_public_rpc_websocket")
    def test_corrupted_db_does_not_claim_capture_complete(self):
        (self.out/"geyser-raw.sqlite").write_bytes(b"not sqlite")
        (self.out/"capture_exit_code.txt").write_text("0")
        (self.out/"manifest.json").write_text(json.dumps({"runtime":"real_solana_public_rpc_websocket","coverage":"UNKNOWN","financial_execution_authorized":False}))
        self.assertEqual(self.do()["status"],"FAILED_OR_INCOMPLETE")
    def test_workflow_is_manual_pinned_and_without_secrets(self):
        wf=(ROOT/".github/workflows/smr-cm27-live-gate.yml").read_text()
        self.assertIn("workflow_dispatch:",wf)
        self.assertIn("permissions:\n  contents: read",wf)
        self.assertNotIn("  push:",wf)
        self.assertNotIn("  pull_request:",wf)
        self.assertIn("READ_ONLY_BOUNDED_CM27",wf)
        self.assertIn("persist-credentials: false",wf)
        self.assertIn("49bb5e7763926d28e540ca13d9557056b9d87833",wf)
        self.assertIn("timeout --signal=TERM --kill-after=5s 90s",wf)
        self.assertIn("if: always()",wf)
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",wf)
        self.assertIn("CM27_AUDIT_STATUS", (ROOT/"tools/cm27_finalize_manifest.py").read_text())
    def test_wheels_are_frozen_by_sha256(self):
        text=self.lock.read_text()
        lines=[x for x in text.splitlines() if x and not x.startswith("#")]
        self.assertEqual(len(lines),3)
        import re
        for line in lines:
            self.assertRegex(line,r"^[a-z-]+==[0-9.]+ --hash=sha256:[a-f0-9]{64}$")

if __name__=="__main__":unittest.main()
