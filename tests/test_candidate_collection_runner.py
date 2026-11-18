import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from smart_money_radar.data_sources.rpc_fixture_collector import FixtureResult
from tools.collect_solana_candidates import run

SIG = "1" * 64


class RunnerTests(unittest.TestCase):
    def _candidate_file(self, directory):
        path = Path(directory) / "candidates.json"
        path.write_text(json.dumps([{"signature": SIG}, {"signature": SIG}]))
        return path

    def test_collects_and_audits_once_after_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collector = Mock()
            collector.collect.side_effect = lambda signature: self._write_fixture(root, signature)
            collected, skipped = run(self._candidate_file(root), root / "out", collector=collector)
            self.assertEqual((collected, skipped), (1, 0))
            collector.collect.assert_called_once_with(SIG)

    def _write_fixture(self, root, signature):
        out = root / "out"
        out.mkdir(exist_ok=True)
        payload = {"result": {"slot": 77, "transaction": {"signatures": [signature]}}}
        raw = json.dumps(payload).encode()
        import hashlib
        raw_path = out / f"{signature}.raw.json"
        manifest_path = out / f"{signature}.manifest.json"
        raw_path.write_bytes(raw)
        manifest_path.write_text(json.dumps({"signature": signature, "slot": 77,
            "commitment": "finalized", "encoding": "json", "raw_file": raw_path.name,
            "sha256": hashlib.sha256(raw).hexdigest(), "anonymized": False}))
        return FixtureResult(signature, raw_path, hashlib.sha256(raw).hexdigest(), 77, 0)

    def test_skips_existing_valid_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collector = Mock()
            collector.collect.side_effect = lambda signature: self._write_fixture(root, signature)
            run(self._candidate_file(root), root / "out", collector=collector)
            collector.reset_mock()
            collected, skipped = run(self._candidate_file(root), root / "out", collector=collector)
            self.assertEqual((collected, skipped), (0, 1))
            collector.collect.assert_not_called()

    def test_partial_pair_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "out"
            out.mkdir()
            raw = out / f"{SIG}.raw.json"
            raw.write_text("preserve")
            collector = Mock()
            with self.assertRaisesRegex(RuntimeError, "Evidência parcial"):
                run(self._candidate_file(root), out, collector=collector)
            self.assertEqual(raw.read_text(), "preserve")
            collector.collect.assert_not_called()

    def test_invalid_existing_pair_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_fixture(root, SIG)
            manifest = root / "out" / f"{SIG}.manifest.json"
            manifest.write_text("{}")
            collector = Mock()
            with self.assertRaises(Exception):
                run(self._candidate_file(root), root / "out", collector=collector)
            collector.collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
