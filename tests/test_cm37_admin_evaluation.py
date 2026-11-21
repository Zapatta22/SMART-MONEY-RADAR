"""CM37D security/control integration restricted to a fresh evaluation DB."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from smart_money_radar.services.admin_evaluation import IsolatedAdminEvaluation
from smart_money_radar.services.admin_security import AdminSecurity

class AdminEvaluationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"new-eval";self.now=1000.
        self.e=IsolatedAdminEvaluation(self.path,password="fixture-long-password",clock=lambda:self.now)
        self.addCleanup(self.e.close)
        self.s=self.e.login("fixture-long-password")
        self.i=0
    def execute(self,action,radar=None,request_id=None):
        self.i+=1
        tok=self.s["session"];csrf=self.s["csrf"]
        nonce=self.e.confirm(tok,csrf,action=action,radar=radar)
        return self.e.execute(tok,csrf,request_id=request_id or "request-eval-%04d"%self.i,
            action=action,radar=radar,confirmation=nonce)
    def test_independent_controls_and_sticky_halt(self):
        a=self.execute("START","launch")
        self.assertTrue(a["executed"])
        self.assertEqual(a["state"]["radars"],{"launch":"RUNNING","smart_money":"PAUSED"})
        b=self.execute("START","smart_money")
        self.assertTrue(b["executed"])
        c=self.execute("PAUSE","launch")
        self.assertEqual(c["state"]["radars"],{"launch":"PAUSED","smart_money":"RUNNING"})
        h=self.execute("EMERGENCY_HALT")
        self.assertTrue(h["state"]["emergency_halt"])
        self.assertFalse(h["state"]["live_authorized"])
        self.assertFalse(self.execute("START","launch")["executed"])
        self.assertEqual(self.e.outcome(h["request_id"])["status"],"APPLIED")
    def test_duplicate_receipt_does_not_execute_again(self):
        rid="request-duplicate-0001"
        self.execute("START","launch",rid)
        with self.assertRaises(PermissionError):self.execute("START","launch",rid)
        self.assertEqual(self.e.outcome(rid)["status"],"APPLIED")
        self.assertEqual(len(self.e.outcome(rid)["state"]["alerts"]),1)
    def test_corrupt_audit_blocks_login_and_commands(self):
        with sqlite3.connect(self.e.security.path) as conn:
            conn.execute("UPDATE audit SET payload='tampered' WHERE seq=1")
        with self.assertRaises(PermissionError):self.e.login("fixture-long-password")
        with self.assertRaises(PermissionError):self.execute("START","launch")
        self.assertEqual(self.e.outcome("request-eval-0001")["status"],"NO_COMMITTED_TRANSITION")
    def test_existing_directory_cannot_be_reprovisioned(self):
        with self.assertRaises(FileExistsError):
            IsolatedAdminEvaluation(self.path,password="fixture-long-password",clock=lambda:self.now)
