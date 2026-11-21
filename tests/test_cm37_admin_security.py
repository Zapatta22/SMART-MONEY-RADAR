"""CM37C security primitives only; no HTTP mutation or trading."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from smart_money_radar.services.admin_security import AdminSecurity


class AdminSecurityTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"admin.sqlite"
        self.now=1000.
        self.security=AdminSecurity.provision(self.path,"fixture-password-strong",
            clock=lambda:self.now,session_seconds=60)
    def login(self):
        return self.security.login("fixture-password-strong")
    def test_password_is_not_persisted_and_setup_cannot_overwrite(self):
        with sqlite3.connect(self.path) as conn:
            salt,verifier=conn.execute("SELECT salt,verifier FROM credentials").fetchone()
            self.assertEqual(len(salt),32)
            self.assertNotIn("fixture-password",verifier)
        with self.assertRaises(FileExistsError):
            AdminSecurity.provision(self.path,"other-strong-password")
    def test_session_expiry_and_revocation(self):
        s=self.login();self.now+=60
        with self.assertRaises(PermissionError):
            self.security.confirm(s["session"],s["csrf"],action="START",radar="launch")
        s=self.login();self.security.revoke(s["session"],s["csrf"])
        with self.assertRaises(PermissionError):
            self.security.confirm(s["session"],s["csrf"],action="START",radar="launch")
    def test_csrf_confirmation_and_replay(self):
        s=self.login();token=s["session"];csrf=s["csrf"]
        with self.assertRaises(PermissionError):
            self.security.confirm(token,"wrong"*8,action="START",radar="launch")
        with self.assertRaises(PermissionError):
            self.security.authorize(token,csrf,request_id="request-00000001",action="START",radar="launch")
        nonce=self.security.confirm(token,csrf,action="START",radar="launch")
        with self.assertRaises(PermissionError):
            self.security.authorize(token,csrf,request_id="request-00000002",action="START",radar="smart_money",confirmation=nonce)
        receipt=self.security.authorize(token,csrf,request_id="request-00000003",action="START",radar="launch",confirmation=nonce)
        self.assertFalse(receipt["executed"])
        self.assertFalse(receipt["remote_writes_enabled"])
        for request in ("request-00000003","request-00000004"):
            with self.assertRaises(PermissionError):
                self.security.authorize(token,csrf,request_id=request,action="START",radar="launch",confirmation=nonce)
        self.assertGreater(self.security.verify_audit(),0)
    def test_persistent_login_rate_limit(self):
        for _ in range(5):
            with self.assertRaises(PermissionError): self.security.login("incorrect-password")
        with self.assertRaises(PermissionError): self.login()
        self.now+=60
        self.assertIn("session",self.login())
    def test_reject_unsupported_financial_action(self):
        s=self.login()
        with self.assertRaises(ValueError):
            self.security.confirm(s["session"],s["csrf"],action="BUY",radar="launch")
    def test_audit_corruption_detected(self):
        self.login()
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE audit SET payload='tampered' WHERE seq=1")
        with self.assertRaises(ValueError): self.security.verify_audit()
