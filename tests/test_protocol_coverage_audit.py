import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID
from smart_money_radar.data_sources.solana_token_transfer_decoder import SPL_TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID
from tools.audit_solana_protocol_coverage import build_report

SIGNATURE = "5" * 64


def fixture(root: Path):
    keys = ["wallet-placeholder", RAYDIUM_CPMM_PROGRAM_ID, SPL_TOKEN_PROGRAM_ID,
            TOKEN_2022_PROGRAM_ID, "unknown-program-placeholder"]
    payload = {"result": {
        "slot": 123,
        "transaction": {"signatures": [SIGNATURE], "message": {
            "accountKeys": keys,
            "instructions": [{"programIdIndex": 1, "data": b58encode(bytes.fromhex("0102030405060708") + bytes(16)), "accounts": list(range(13))}, {"programIdIndex": 4}],
        }},
        "meta": {"err": None, "innerInstructions": [
            {"index": 0, "instructions": [{"programIdIndex": 2}, {"programIdIndex": 3}]}
        ], "preTokenBalances": [], "postTokenBalances": []},
    }}
    raw = json.dumps(payload).encode()
    (root / "one.raw.json").write_bytes(raw)
    manifest = {"signature": SIGNATURE, "slot": 123, "commitment": "finalized",
                "encoding": "json", "raw_file": "one.raw.json",
                "sha256": hashlib.sha256(raw).hexdigest(), "anonymized": False}
    (root / "one.manifest.json").write_text(json.dumps(manifest))


class ProtocolCoverageTests(unittest.TestCase):
    def test_counts_registered_programs_and_narrow_decoder_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            report = build_report(root)
        self.assertEqual(report["audited_count"], 1)
        item = report["reports"][0]
        self.assertEqual(item["status"], "AUDITED")
        self.assertEqual(item["instruction_count"], 4)
        self.assertEqual(item["registered_program_counts"], {
            "Raydium CPMM": 1, "SPL Token": 1, "Token-2022": 1
        })
        self.assertEqual(item["decoder_scope_counts"], {
            "Raydium CPMM": 1, "SPL Token": 1, "Token-2022": 1
        })
        self.assertEqual(item["venue_instruction_profiles"], [{
            "program": "Raydium CPMM",
            "location": "top_level",
            "data_prefix_hex": "0102030405060708",
            "data_length": 24,
            "account_count": 13,
            "stack_height": None,
            "count": 1,
        }])
        self.assertEqual(item["unregistered_program_instruction_count"], 1)
        self.assertEqual(item["unresolved_program_instruction_count"], 0)

    def test_report_never_exposes_program_ids_or_fixture_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            report = build_report(root)
        rendered = json.dumps(report)
        for secret in (SIGNATURE, RAYDIUM_CPMM_PROGRAM_ID, SPL_TOKEN_PROGRAM_ID,
                       TOKEN_2022_PROGRAM_ID, "wallet-placeholder", "unknown-program-placeholder"):
            self.assertNotIn(secret, rendered)
        self.assertFalse(report["network_access"])
        self.assertFalse(report["database_access"])
        self.assertFalse(report["writes_files"])
        self.assertFalse(report["checkpoint_changes"])
        self.assertIn("venue_instruction_profiles", report["reports"][0])

    def test_rejects_symlinked_raw_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            fixture(outside)
            # Copy the manifest into the authorized root, but link its raw payload outside.
            manifest = json.loads((outside / "one.manifest.json").read_text())
            (root / "one.manifest.json").write_text(json.dumps(manifest))
            (root / "one.raw.json").symlink_to(outside / "one.raw.json")
            report = build_report(root)
        self.assertEqual(report["status_counts"], {"FIXTURE_INVALID": 1})


if __name__ == "__main__":
    unittest.main()
