import hashlib
import unittest
from smart_money_radar.domain.cpmm_reserve_snapshot import (
    validate_snapshot, estimate_from_snapshot, estimate_from_raw_units,
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
            "input_decimals": 9, "output_decimals": 6,
        }

    def test_valid_snapshot_yields_non_observed_estimate(self):
        snapshot = validate_snapshot(self.record(), self.RAW)
        result = estimate_from_snapshot(snapshot, "10")
        self.assertFalse(result.is_observed_quote)
        self.assertEqual(result.slot, 123)

    def test_raw_integer_reserves_match_declared_decimals(self):
        snapshot = validate_snapshot(self.record(), self.RAW)
        quote = estimate_from_raw_units(
            snapshot, amount_in_raw=10_000_000_000,
            reserve_in_raw=1_000_000_000_000,
            reserve_out_raw=2_000_000_000,
        )
        self.assertEqual(quote.estimated_output,
                         estimate_from_snapshot(snapshot, "10").estimated_output)

    def test_raw_integer_reserve_mismatch_fails_closed(self):
        snapshot = validate_snapshot(self.record(), self.RAW)
        with self.assertRaisesRegex(ValueError, "reservas RAW divergentes"):
            estimate_from_raw_units(
                snapshot, amount_in_raw=10_000_000_000,
                reserve_in_raw=1_000_000_000_001,
                reserve_out_raw=2_000_000_000,
            )
        with self.assertRaises(ValueError):
            estimate_from_raw_units(
                snapshot, amount_in_raw=True,
                reserve_in_raw=1_000_000_000_000,
                reserve_out_raw=2_000_000_000,
            )

    def test_rejects_tampered_raw(self):
        with self.assertRaisesRegex(ValueError, "hash RAW"):
            validate_snapshot(self.record(), b"tampered")

    def test_rejects_incomplete_or_unfinalized(self):
        for changes in ({"commitment": "processed"}, {"slot": True},
                        {"reserve_in": "NaN"}, {"fee_bps": 10000},
                        {"available_at": "2026-11-19T19:59:00-04:00"},
                        {"input_mint": "USDC"}, {"input_decimals": True},
                        {"output_decimals": -1}, {"input_decimals": 19}):
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
