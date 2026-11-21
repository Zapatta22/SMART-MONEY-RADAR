"""Static CM27 safety review against workflow and one-shot capture script."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class LiveGateStaticReview(unittest.TestCase):
    def test_manual_only_read_scope_and_opt_in(self):
        yaml=(ROOT/".github/workflows/smr-cm27-live-gate.yml").read_text()
        self.assertIn("workflow_dispatch:",yaml)
        self.assertIn("contents: read",yaml)
        self.assertIn("READ_ONLY_BOUNDED_CM27",yaml)
        self.assertIn("timeout-minutes: 3",yaml)
        self.assertNotIn("pull_request:",yaml)
        self.assertNotIn("push:",yaml)
        self.assertNotIn("secrets.",yaml)
    def test_bounded_script_scoped_accounts_and_upload(self):
        script=(ROOT/"tools/capture_live_cpmm_ws_baseline.py").read_text()
        yaml=(ROOT/".github/workflows/smr-cm27-live-gate.yml").read_text()
        self.assertIn("MAX_SECONDS=75",script)
        self.assertIn("MAX_FRAMES=80",script)
        self.assertIn("SMR_LIVE_CAPTURE_OPT_IN",script)
        self.assertIn("len(matches)!=1",script)
        self.assertIn("if: always()",yaml)
        self.assertIn("upload-artifact@v4",yaml)
    def test_insecure_assumptions_not_silently_accepted(self):
        yaml=(ROOT/".github/workflows/smr-cm27-live-gate.yml").read_text()
        self.assertNotIn("permissions: write-all",yaml)
        self.assertNotIn("persist-credentials: true",yaml)
        self.assertIn("actions/checkout@v4",yaml)
        self.assertNotIn("ref: main",yaml)
