import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import collect_solana_fixtures


class CandidateBatchCliTests(unittest.TestCase):
    def test_candidate_file_contains_five_unique_documented_signatures(self):
        path = Path("data/fixtures/candidates/solana_mainnet_candidates.json")
        candidates = json.loads(path.read_text())
        signatures = [item["signature"] for item in candidates]
        self.assertEqual(len(signatures), 5)
        self.assertEqual(len(set(signatures)), 5)
        self.assertTrue(all(item["source"].startswith("https://solscan.io/tx/") for item in candidates))

    def test_cli_loads_candidate_file_and_deduplicates(self):
        class FakeResult:
            signature = "sig"
            slot = 1
            sha256 = "hash"
        class FakeCollector:
            def __init__(self, endpoint, output):
                self.signatures = []
            def collect(self, signature):
                self.signatures.append(signature)
                return FakeResult()
        with tempfile.TemporaryDirectory() as tmp:
            candidate_file = Path(tmp) / "candidates.json"
            candidate_file.write_text(json.dumps([{"signature":"sig"},{"signature":"sig"}]))
            with patch("sys.argv", ["collect", "--candidate-file", str(candidate_file)]), \
                 patch.object(collect_solana_fixtures, "endpoint_from_environment", return_value="https://rpc.example"), \
                 patch.object(collect_solana_fixtures, "RpcFixtureCollector", FakeCollector):
                self.assertEqual(collect_solana_fixtures.main(), 0)


if __name__ == "__main__":
    unittest.main()
