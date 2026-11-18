import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from smart_money_radar.data_sources.fixture_audit import audit_fixture

SIG = "5" * 64


def make_pair(directory: Path):
    raw = json.dumps({"jsonrpc": "2.0", "result": {
        "slot": 42, "transaction": {"signatures": [SIG]}, "meta": {"err": None}
    }}).encode()
    raw_name = f"{SIG}.raw.json"
    (directory / raw_name).write_bytes(raw)
    manifest = {
        "signature": SIG, "slot": 42, "commitment": "finalized", "encoding": "json",
        "raw_file": raw_name, "sha256": hashlib.sha256(raw).hexdigest(), "anonymized": False,
    }
    path = directory / f"{SIG}.manifest.json"
    path.write_text(json.dumps(manifest))
    return path


class FixtureAuditTests(unittest.TestCase):
    def test_accepts_intact_raw_and_manifest_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = audit_fixture(make_pair(Path(tmp)))
            self.assertTrue(result.valid)
            self.assertEqual(result.slot, 42)
            self.assertEqual(result.errors, ())

    def test_detects_raw_payload_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_pair(Path(tmp))
            raw = Path(tmp) / f"{SIG}.raw.json"
            raw.write_bytes(raw.read_bytes() + b" ")
            result = audit_fixture(path)
            self.assertFalse(result.valid)
            self.assertIn("SHA-256 do arquivo bruto não confere", result.errors)

    def test_detects_manifest_signature_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_pair(Path(tmp))
            manifest = json.loads(path.read_text())
            manifest["signature"] = "4" * 64
            path.write_text(json.dumps(manifest))
            result = audit_fixture(path)
            self.assertFalse(result.valid)
            self.assertIn("assinatura do payload difere do manifesto", result.errors)

    def test_rejects_path_traversal_in_raw_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_pair(Path(tmp))
            manifest = json.loads(path.read_text())
            manifest["raw_file"] = "../outside.json"
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "nome de arquivo local"):
                audit_fixture(path)

    def test_detects_non_finalized_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_pair(Path(tmp))
            manifest = json.loads(path.read_text())
            manifest["commitment"] = "confirmed"
            path.write_text(json.dumps(manifest))
            result = audit_fixture(path)
            self.assertFalse(result.valid)
            self.assertIn("commitment não é finalized", result.errors)


if __name__ == "__main__":
    unittest.main()
