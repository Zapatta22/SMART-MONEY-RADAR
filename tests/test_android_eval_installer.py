"""Offline tests of the Android evaluation path, including original immutability."""
import hashlib
import runpy
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from smart_money_radar.storage.event_store import SQLiteEventStore

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"tools"/"install_smr_android_eval.sh"
prepare=runpy.run_path(str(ROOT/"tools"/"prepare_smr_eval_db.py"))["prepare"]

class AndroidEvalInstaller(unittest.TestCase):
    @unittest.skipUnless(shutil.which("bash"),"bash required")
    def test_shell_syntax_and_fixed_loopback(self):
        subprocess.run(["bash","-n",str(SCRIPT)],check=True)
        code=SCRIPT.read_text()
        self.assertIn("mktemp -d",code)
        self.assertIn("--host 127.0.0.1 --port 8765",code)
        self.assertIn("rev-parse HEAD",code)
        self.assertNotIn("--host 0.0.0.0",code)
        # Ensure the embedded helper and the tested helper are identical.
        helper=(ROOT/"tools"/"prepare_smr_eval_db.py").read_text().strip()
        self.assertIn(helper,code)

    def test_new_database_is_isolated_and_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/"new.sqlite"
            prepare(dest)
            db=SQLiteEventStore(dest,read_only=True)
            try:self.assertEqual(db.integrity_check(),["ok"])
            finally:db.close()
            with self.assertRaises(ValueError):prepare(dest)

    def test_readonly_copy_preserves_original(self):
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"original.sqlite"
            db=SQLiteEventStore(src);db.close()
            before=hashlib.sha256(src.read_bytes()).digest()
            dst=Path(temp)/"copy.sqlite"
            prepare(dst,src)
            self.assertEqual(hashlib.sha256(src.read_bytes()).digest(),before)
            self.assertNotEqual(src,dst)
            with sqlite3.connect(dst) as conn:
                conn.execute("CREATE TABLE evaluation_only (id INTEGER)")
            self.assertEqual(hashlib.sha256(src.read_bytes()).digest(),before)
    def test_preexisting_destination_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/"existing"
            dest.write_bytes(b"keep")
            with self.assertRaises(ValueError):prepare(dest)
            self.assertEqual(dest.read_bytes(),b"keep")
