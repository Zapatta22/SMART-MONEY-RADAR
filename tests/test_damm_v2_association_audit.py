import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_damm_v2_associations import build_report
from smart_money_radar.data_sources.damm_v2_decoder import (
    EVENT_CPI_TAG,
    EVT_SWAP2_DISCRIMINATOR,
    METEORA_DAMM_V2_PROGRAM_ID,
    SWAP_DISCRIMINATOR,
)

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(data):
    zeros = len(data) - len(data.lstrip(b"\\x00"))
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = ALPHABET[remainder] + encoded
    return "1" * zeros + (encoded or ("" if zeros else "1"))


def u64(value):
    return value.to_bytes(8, "little")


def event_data():
    body = (
        bytes(32) + bytes((0, 0, 0))
        + u64(100) + u64(90) + bytes((0,))
        + u64(100) + u64(0) + u64(0) + u64(90) + bytes(16)
        + u64(0) + u64(0) + u64(0) + u64(0)
        + u64(0) + u64(0) + u64(0)
        + u64(1) + u64(2) + u64(3)
    )
    data = EVENT_CPI_TAG + EVT_SWAP2_DISCRIMINATOR + body
    assert len(data) == 196
    return data


class DammV2AssociationAuditTests(unittest.TestCase):
    def _fixture(self, root):
        raw_name = "private.raw.json"
        signature = "private-signature"
        swap = SWAP_DISCRIMINATOR + u64(100) + u64(90)
        payload = {
            "result": {
                "slot": 7,
                "transaction": {
                    "signatures": [signature],
                    "message": {
                        "accountKeys": ["private-wallet"],
                        "instructions": [{
                            "programId": "aggregator",
                            "accounts": [],
                            "data": b58encode(b"route"),
                        }],
                    },
                },
                "meta": {
                    "err": None,
                    "innerInstructions": [{
                        "index": 0,
                        "instructions": [
                            {"programId": METEORA_DAMM_V2_PROGRAM_ID,
                             "accounts": [0], "data": b58encode(swap),
                             "stackHeight": 2},
                            {"programId": METEORA_DAMM_V2_PROGRAM_ID,
                             "accounts": [0], "data": b58encode(event_data()),
                             "stackHeight": 3},
                        ],
                    }],
                },
            }
        }
        raw_bytes = json.dumps(payload).encode()
        (root / raw_name).write_bytes(raw_bytes)
        manifest = {
            "signature": signature,
            "slot": 7,
            "commitment": "finalized",
            "encoding": "json",
            "raw_file": raw_name,
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "anonymized": False,
        }
        (root / "private.manifest.json").write_text(json.dumps(manifest))

    def test_reports_matched_swap_and_event_without_fixture_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            report = build_report(root)
            rendered = json.dumps(report)
            self.assertEqual(report["manifest_count"], 1)
            self.assertEqual(report["audited_count"], 1)
            item = report["reports"][0]
            self.assertEqual(item["swap_operation_count"], 1)
            self.assertEqual(item["swap_status_counts"], {"MATCHED": 1})
            self.assertEqual(item["event_count"], 1)
            self.assertEqual(item["event_status_counts"], {"MATCHED": 1})
            for secret in ("private-signature", "private-wallet", "private.raw.json"):
                self.assertNotIn(secret, rendered)
            self.assertFalse(report["network_access"])
            self.assertFalse(report["database_access"])
            self.assertFalse(report["writes_files"])
            self.assertFalse(report["checkpoint_changes"])
            self.assertFalse(report["execution_authorized"])

    def test_rejects_symlinked_raw_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / (root.name + "-outside.json")
            outside.write_text("{}")
            try:
                manifest = {
                    "signature": "sig", "slot": 1, "commitment": "finalized",
                    "encoding": "json", "raw_file": "linked.raw.json",
                    "sha256": "0" * 64, "anonymized": False,
                }
                (root / "linked.raw.json").symlink_to(outside)
                (root / "linked.manifest.json").write_text(json.dumps(manifest))
                report = build_report(root)
                self.assertEqual(report["reports"][0]["status"], "FIXTURE_INVALID")
            finally:
                outside.unlink(missing_ok=True)

    def test_empty_directory_is_reported_without_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            report = build_report(Path(directory))
            self.assertEqual(report["manifest_count"], 0)
            self.assertEqual(report["audited_count"], 0)
            self.assertFalse(report["network_access"])
            self.assertFalse(report["database_access"])
            self.assertFalse(report["writes_files"])


if __name__ == "__main__":
    unittest.main()
