import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.plan_solana_historical_import import build_plan


SIG = "5" * 64
WALLET = "WalletExplicitlySuppliedByOperator"


def make_pair(root: Path, *, signature: str = SIG, slot: int = 9, err=None):
    raw = json.dumps({"result": {
        "slot": slot,
        "transaction": {"signatures": [signature], "message": {"accountKeys": [WALLET], "instructions": []}},
        "meta": {"err": err, "preTokenBalances": [], "postTokenBalances": []},
    }}).encode()
    raw_name = "candidate.raw.json"
    (root / raw_name).write_bytes(raw)
    manifest = {
        "signature": signature, "slot": slot, "commitment": "finalized",
        "encoding": "json", "raw_file": raw_name,
        "sha256": hashlib.sha256(raw).hexdigest(), "anonymized": False,
    }
    path = root / "candidate.manifest.json"
    path.write_text(json.dumps(manifest))
    return path


class HistoricalImportPlannerTests(unittest.TestCase):
    def test_defaults_to_wallet_unassigned_without_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_pair(root)
            report = build_plan(root)
        self.assertEqual(report["status_counts"], {"WALLET_UNASSIGNED": 1})
        self.assertFalse(report["database_access"])
        self.assertFalse(report["network_access"])
        self.assertFalse(report["writes_files"])
        self.assertFalse(report["checkpoint_changes"])
        self.assertFalse(report["execution_authorized"])

    def test_explicit_mapping_only_marks_ready_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_pair(root)
            mapping = root / "wallet-map.json"
            mapping.write_text(json.dumps({SIG: WALLET}))
            report = build_plan(root, mapping)
        self.assertEqual(report["status_counts"], {"READY_FOR_REVIEW": 1})

    def test_detects_manifest_hash_mismatch_without_leaking_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = make_pair(root)
            manifest = json.loads(manifest_path.read_text())
            manifest["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest))
            report = build_plan(root)
        self.assertEqual(report["status_counts"], {"HASH_MISMATCH": 1})
        rendered = json.dumps(report)
        self.assertNotIn(SIG, rendered)
        self.assertNotIn(WALLET, rendered)

    def test_on_chain_failure_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_pair(root, err={"InstructionError": [0, "Custom"]})
            mapping = root / "wallet-map.json"
            mapping.write_text(json.dumps({SIG: WALLET}))
            report = build_plan(root, mapping)
        self.assertEqual(report["status_counts"], {"ON_CHAIN_FAILED": 1})

    def test_rejects_symlinked_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            manifest_path = make_pair(outside)
            link = root / "linked.manifest.json"
            link.symlink_to(manifest_path)
            report = build_plan(root)
        self.assertEqual(report["status_counts"], {"MANIFEST_INVALID": 1})

    def test_empty_wallet_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_pair(root)
            mapping = root / "wallet-map.json"
            mapping.write_text("[]")
            with self.assertRaisesRegex(ValueError, "objeto JSON"):
                build_plan(root, mapping)


if __name__ == "__main__":
    unittest.main()
