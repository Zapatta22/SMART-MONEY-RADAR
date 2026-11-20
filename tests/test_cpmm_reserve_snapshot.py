import hashlib
import unittest
from smart_money_radar.domain.cpmm_reserve_snapshot import (
    validate_snapshot, estimate_from_snapshot,
)


class SnapshotTests(unittest.TestCase):
    RAW = b'{"rpc":"example","slot":123}'

    def record(self):
        return {
            "pool": "pool-a", "slot": 123, "commitment": "finalized",
            "captured_at": "2026-11-19T20:00:00-04:00",
            "available_at": "2026-11-19T20:00:01-04:00",
            "raw_sha256": hashlib.sha256(self.RAW).hexdigest(),
            "reserve_in": "1000", "reserve_out": "2000", "fee_bps": "30",
            "input_mint": "SOL", "output_mint": "USDC",
        }

    def test_valid_snapshot_yields_non_observed_estimate(self):
        snapshot = validate_snapshot(self.record(), self.RAW)
        result = estimate_from_snapshot(snapshot, "10")
        self.assertFalse(result.is_observed_quote)
        self.assertEqual(result.slot, 123)

    def test_rejects_tampered_raw(self):
        with self.assertRaisesRegex(ValueError, "hash RAW"):
            validate_snapshot(self.record(), b"tampered")

    def test_rejects_incomplete_or_unfinalized(self):
        for changes in ({"commitment": "processed"}, {"slot": True},
                        {"reserve_in": "NaN"}, {"fee_bps": 10000},
                        {"available_at": "2026-11-19T19:59:00-04:00"},
                        {"input_mint": "USDC"}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    validate_snapshot({**self.record(), **changes}, self.RAW)

    def test_rejects_missing_field(self):
        data = self.record()
        del data["raw_sha256"]
        with self.assertRaises(ValueError):
            validate_snapshot(data, self.RAW)


if __name__ == "__main__":
    unittest.main()
