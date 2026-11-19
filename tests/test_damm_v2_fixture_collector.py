import json
import unittest
from pathlib import Path

from tools.collect_damm_v2_fixture import find_damm_v2_signature


class DammV2FixtureCollectorTests(unittest.TestCase):
    def test_catalog_has_exactly_one_meteora_damm_v2_candidate(self):
        root = Path(__file__).resolve().parents[1]
        candidates = json.loads(
            (root / "data/fixtures/candidates/solana_mainnet_candidates.json")
            .read_text(encoding="utf-8")
        )
        signature = find_damm_v2_signature(candidates)
        self.assertEqual(
            signature,
            "1z8EYinixC5GZrwVsapJ4vW9Zfdx7j7EQnGZUVPQUm72WuXz8x5SMbakwunFXHYtftGiikm3JHLgwi2BwEVLLT",
        )

    def test_rejects_missing_or_ambiguous_damm_v2_candidates(self):
        with self.assertRaises(ValueError):
            find_damm_v2_signature([])
        with self.assertRaises(ValueError):
            find_damm_v2_signature([
                {"protocol": "Meteora DAMM v2", "signature": "first"},
                {"protocol": "Meteora DAMM v2", "signature": "second"},
            ])


if __name__ == "__main__":
    unittest.main()
