import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from smart_money_radar.data_sources.fixture_anonymizer import anonymize_fixture

SIG = "5" * 64
WALLET = "11111111111111111111111111111112"
TOKEN_ACCOUNT = "11111111111111111111111111111113"
OWNER = "11111111111111111111111111111114"
PROGRAM = "11111111111111111111111111111111"
MINT = "So11111111111111111111111111111111111111112"
POOL = "11111111111111111111111111111115"


def raw_payload():
    return {"jsonrpc": "2.0", "result": {
        "slot": 987, "blockTime": 123456,
        "transaction": {"signatures": [SIG], "message": {
            "header": {"numRequiredSignatures": 1, "numReadonlySignedAccounts": 0, "numReadonlyUnsignedAccounts": 1},
            "accountKeys": [WALLET, TOKEN_ACCOUNT, PROGRAM, POOL],
            "instructions": [{"programIdIndex": 2, "accounts": [0, 1, 3], "data": "abc"}],
            "recentBlockhash": "11111111111111111111111111111111"
        }},
        "meta": {"err": None, "fee": 5000,
            "preTokenBalances": [{"accountIndex": 1, "mint": MINT, "owner": OWNER, "uiTokenAmount": {"amount": "10", "decimals": 6}}],
            "postTokenBalances": [{"accountIndex": 1, "mint": MINT, "owner": OWNER, "uiTokenAmount": {"amount": "8", "decimals": 6}}],
            "logMessages": [f"Program log: owner={OWNER} signer={WALLET}"]}
    }}


class FixtureAnonymizerTests(unittest.TestCase):
    def run_anon(self, directory: Path, *, protected=()):
        raw = directory / "original.raw.json"
        raw_bytes = (json.dumps(raw_payload(), separators=(",", ":")) + "\n").encode()
        raw.write_bytes(raw_bytes)
        mapping = directory.parent / (directory.name + "-private") / "map.json"
        result = anonymize_fixture(raw, directory / "fixture.json", mapping,
            key="unit-test-secret-key-which-is-long", protected_addresses=protected)
        return raw, mapping, result, raw_bytes

    def test_anonymizes_fee_payer_token_account_owner_and_token_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / "fixtures"; out.mkdir()
            raw, mapping, result, raw_bytes = self.run_anon(out)
            projected = json.loads(result.projection_path.read_text())
            keys = projected["result"]["transaction"]["message"]["accountKeys"]
            self.assertNotIn(WALLET, keys)
            self.assertNotIn(TOKEN_ACCOUNT, keys)
            self.assertEqual(keys[2], PROGRAM)
            self.assertEqual(keys[3], POOL)
            balances = projected["result"]["meta"]["preTokenBalances"]
            self.assertNotEqual(balances[0]["owner"], OWNER)
            self.assertEqual(balances[0]["mint"], MINT)
            self.assertNotIn(WALLET, projected["result"]["meta"]["logMessages"][0])
            self.assertNotIn(OWNER, projected["result"]["meta"]["logMessages"][0])
            self.assertEqual(raw.read_bytes(), raw_bytes)
            self.assertEqual(result.raw_sha256, hashlib.sha256(raw_bytes).hexdigest())
            self.assertEqual(result.replaced_addresses, 3)
            self.assertTrue(result.mapping_path.exists())
            self.assertEqual(os.stat(mapping).st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(mapping.read_text())["aliases"][WALLET], keys[0])

    def test_protected_wallet_like_address_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / "fixtures"; out.mkdir()
            _, _, result, _ = self.run_anon(out, protected=[WALLET])
            projected = json.loads(result.projection_path.read_text())
            keys = projected["result"]["transaction"]["message"]["accountKeys"]
            self.assertEqual(keys[0], WALLET)

    def test_aliases_are_stable_for_same_key_and_address(self):
        aliases = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); out = root / "fixtures"; out.mkdir()
                _, mapping, _, _ = self.run_anon(out)
                aliases.append(json.loads(mapping.read_text())["aliases"][WALLET])
        self.assertEqual(aliases[0], aliases[1])

    def test_refuses_mapping_inside_fixture_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); raw = root / "raw.json"
            raw.write_text(json.dumps(raw_payload()))
            with self.assertRaisesRegex(ValueError, "fora do diretório"):
                anonymize_fixture(raw, root / "fixture.json", root / "map.json", key="x" * 20)

    def test_refuses_short_key_and_existing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / "fixtures"; out.mkdir()
            raw = out / "raw.json"; raw.write_text(json.dumps(raw_payload()))
            with self.assertRaisesRegex(ValueError, "pelo menos 16"):
                anonymize_fixture(raw, out / "fixture.json", root / "map.json", key="short")
            projection = out / "fixture.json"; projection.write_text("keep")
            with self.assertRaises(FileExistsError):
                anonymize_fixture(raw, projection, root / "map.json", key="x" * 20)
            self.assertEqual(projection.read_text(), "keep")

    def test_validates_source_manifest_hash_and_raw_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / "fixtures"; out.mkdir()
            raw = out / "raw.json"; raw_bytes = json.dumps(raw_payload()).encode(); raw.write_bytes(raw_bytes)
            manifest = out / "raw.manifest.json"
            manifest.write_text(json.dumps({"sha256": "0" * 64, "anonymized": False, "signature": SIG,
                "slot": 987, "commitment": "finalized", "encoding": "json", "raw_file": raw.name}))
            with self.assertRaisesRegex(ValueError, "não corresponde"):
                anonymize_fixture(raw, out / "fixture.json", root / "map.json", key="x" * 20, source_manifest_path=manifest)

    def test_preserves_program_ids_from_inner_compiled_instructions_and_loaded_addresses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / "fixtures"; out.mkdir()
            payload = raw_payload()
            result = payload["result"]
            result["meta"]["loadedAddresses"] = {"writable": ["11111111111111111111111111111116"],
                "readonly": ["11111111111111111111111111111117"]}
            result["meta"]["innerInstructions"] = [{"index": 0, "instructions": [
                {"programIdIndex": 5, "accounts": [0, 1], "data": "xyz"}]}]
            raw = out / "raw.json"; raw.write_text(json.dumps(payload))
            mapping = root / "private" / "map.json"
            result_obj = anonymize_fixture(raw, out / "projection.json", mapping,
                key="inner-test-secret-key-at-least-16")
            projected = json.loads(result_obj.projection_path.read_text())["result"]
            self.assertEqual(projected["meta"]["loadedAddresses"]["readonly"][0],
                "11111111111111111111111111111117")
            self.assertEqual(projected["meta"]["innerInstructions"][0]["instructions"][0]["programIdIndex"], 5)

    def test_accepts_and_checks_valid_source_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / "fixtures"; out.mkdir()
            raw = out / "raw.json"
            raw_bytes = json.dumps(raw_payload()).encode(); raw.write_bytes(raw_bytes)
            manifest = out / "raw.manifest.json"
            manifest.write_text(json.dumps({"signature": SIG, "slot": 987, "commitment": "finalized",
                "encoding": "json", "raw_file": raw.name,
                "sha256": hashlib.sha256(raw_bytes).hexdigest(), "anonymized": False}))
            result = anonymize_fixture(raw, out / "projection.json", root / "private" / "map.json",
                key="manifest-test-secret-key-long", source_manifest_path=manifest)
            self.assertTrue(result.manifest_path.exists())

    def test_anonymizes_explicit_personal_address_but_protection_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / "fixtures"; out.mkdir()
            raw = out / "raw.json"; raw.write_text(json.dumps(raw_payload()))
            result = anonymize_fixture(raw, out / "projection.json", root / "private" / "map.json",
                key="explicit-address-test-key-long", sensitive_addresses=[POOL],
                protected_addresses=[PROGRAM])
            mapping = json.loads(result.mapping_path.read_text())["aliases"]
            self.assertIn(POOL, mapping)
            self.assertNotIn(PROGRAM, mapping)

    def test_rejects_invalid_explicit_sensitive_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / "fixtures"; out.mkdir()
            raw = out / "raw.json"; raw.write_text(json.dumps(raw_payload()))
            with self.assertRaisesRegex(ValueError, "Base58 válida"):
                anonymize_fixture(raw, out / "projection.json", root / "private" / "map.json",
                    key="explicit-address-test-key-long", sensitive_addresses=["not-an-address"])


if __name__ == "__main__":
    unittest.main()
