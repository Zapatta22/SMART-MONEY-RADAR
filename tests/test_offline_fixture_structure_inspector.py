import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.inspect_solana_fixture_structure import inspect_manifest


class OfflineFixtureStructureInspectorTests(unittest.TestCase):
    def test_reports_structure_without_leaking_addresses_or_signature(self):
        signature = "5" * 64
        address = "SensitiveWalletAddressNeverPrint"
        payload = {
            "jsonrpc": "2.0",
            "result": {
                "slot": 123,
                "version": 0,
                "transaction": {
                    "signatures": [signature],
                    "message": {
                        "accountKeys": [address, "SensitiveMintNeverPrint"],
                        "instructions": [{"programId": "SensitiveProgramNeverPrint"}],
                    },
                },
                "meta": {
                    "err": None,
                    "innerInstructions": [{"instructions": [{"programId": "SecretCPI"}]}],
                    "preTokenBalances": [{"owner": address}],
                    "postTokenBalances": [{"owner": address}],
                },
            },
        }
        raw = json.dumps(payload).encode()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            raw_name = "fixture.raw.json"
            (directory / raw_name).write_bytes(raw)
            manifest = {
                "signature": signature,
                "slot": 123,
                "commitment": "finalized",
                "encoding": "json",
                "raw_file": raw_name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "anonymized": False,
            }
            manifest_path = directory / "fixture.manifest.json"
            manifest_path.write_text(json.dumps(manifest))

            report = inspect_manifest(manifest_path, 1)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                print(json.dumps(report))

        self.assertTrue(report["integrity_valid"])
        self.assertTrue(report["structure_valid"])
        self.assertEqual(report["account_key_count"], 2)
        self.assertEqual(report["top_level_instruction_count"], 1)
        self.assertEqual(report["inner_instruction_count"], 1)
        self.assertEqual(report["pre_balances_with_owner_count"], 1)
        self.assertFalse(report["manifest_declares_wallet_address"])
        for secret in (signature, address, "SensitiveMintNeverPrint", "SensitiveProgramNeverPrint", "SecretCPI"):
            self.assertNotIn(secret, output.getvalue())

    def test_reports_integrity_failure_without_exposing_file_identity(self):
        signature = "5" * 64
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            raw_name = "fixture.raw.json"
            (directory / raw_name).write_text(json.dumps({
                "result": {
                    "slot": 1,
                    "transaction": {"signatures": [signature], "message": {"accountKeys": [], "instructions": []}},
                    "meta": {"err": None},
                }
            }))
            manifest_path = directory / "fixture.manifest.json"
            manifest_path.write_text(json.dumps({
                "signature": signature,
                "slot": 1,
                "commitment": "finalized",
                "encoding": "json",
                "raw_file": raw_name,
                "sha256": "0" * 64,
                "anonymized": False,
            }))
            report = inspect_manifest(manifest_path, 1)

        self.assertFalse(report["integrity_valid"])
        self.assertTrue(report["structure_valid"])
        self.assertIn("SHA-256", report["audit_errors"][0])

    def test_missing_manifest_does_not_echo_sensitive_path(self):
        secret_path = Path("/tmp/WalletSignatureMustNotLeak-5" + "5" * 64 + ".manifest.json")
        report = inspect_manifest(secret_path, 1)
        rendered = json.dumps(report, ensure_ascii=False)
        self.assertFalse(report["integrity_valid"])
        self.assertIn("manifesto ou payload inacessível", rendered)
        self.assertNotIn(str(secret_path), rendered)
        self.assertNotIn("WalletSignatureMustNotLeak", rendered)

    def test_detects_explicit_wallet_field_without_exposing_value(self):
        signature = "5" * 64
        wallet = "SensitiveWalletMustNeverPrint"
        payload = {
            "result": {
                "slot": 7,
                "transaction": {
                    "signatures": [signature],
                    "message": {"accountKeys": [], "instructions": []},
                },
                "meta": {"err": None},
            }
        }
        raw = json.dumps(payload).encode()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "fixture.raw.json").write_bytes(raw)
            manifest_path = directory / "fixture.manifest.json"
            manifest_path.write_text(json.dumps({
                "signature": signature,
                "slot": 7,
                "commitment": "finalized",
                "encoding": "json",
                "raw_file": "fixture.raw.json",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "anonymized": False,
                "wallet_address": wallet,
            }))
            report = inspect_manifest(manifest_path, 1)

        rendered = json.dumps(report, ensure_ascii=False)
        self.assertTrue(report["manifest_declares_wallet_address"])
        self.assertNotIn(wallet, rendered)
        self.assertNotIn(signature, rendered)

    def test_rejects_symlinked_manifest_outside_authorized_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            authorized = root / "authorized"
            outside = root / "outside"
            authorized.mkdir()
            outside.mkdir()
            outside_manifest = outside / "secret.manifest.json"
            outside_manifest.write_text(json.dumps({"signature": "SensitiveSignature"}))
            link = authorized / "linked.manifest.json"
            link.symlink_to(outside_manifest)
            report = inspect_manifest(link, 1, authorized)

        rendered = json.dumps(report)
        self.assertFalse(report["integrity_valid"])
        self.assertFalse(report["structure_valid"])
        self.assertNotIn("SensitiveSignature", rendered)
        self.assertNotIn(str(outside_manifest), rendered)

    def test_rejects_symlinked_raw_payload_outside_authorized_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            authorized = root / "authorized"
            outside = root / "outside"
            authorized.mkdir()
            outside.mkdir()
            signature = "6" * 64
            payload = {
                "result": {
                    "slot": 123,
                    "transaction": {
                        "signatures": [signature],
                        "message": {"accountKeys": [], "instructions": []},
                    },
                    "meta": {"err": None},
                }
            }
            raw = json.dumps(payload).encode()
            outside_raw = outside / "secret.raw.json"
            outside_raw.write_bytes(raw)
            link = authorized / "linked.raw.json"
            link.symlink_to(outside_raw)
            manifest_path = authorized / "linked.manifest.json"
            manifest_path.write_text(json.dumps({
                "signature": signature,
                "slot": 123,
                "commitment": "finalized",
                "encoding": "json",
                "raw_file": "linked.raw.json",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "anonymized": False,
            }))
            report = inspect_manifest(manifest_path, 1, authorized)

        rendered = json.dumps(report)
        self.assertFalse(report["integrity_valid"])
        self.assertFalse(report["structure_valid"])
        self.assertNotIn(signature, rendered)
        self.assertNotIn(str(outside_raw), rendered)


if __name__ == "__main__":
    unittest.main()
