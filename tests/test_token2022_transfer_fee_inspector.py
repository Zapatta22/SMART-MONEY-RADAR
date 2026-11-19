import sys
import unittest
from pathlib import Path

TOOLS_DIR = str(Path(__file__).resolve().parents[1] / "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from inspect_token_2022_transfer_fee_config import _parse_transfer_fee_config


class Token2022TransferFeeInspectorTests(unittest.TestCase):
    def test_decodes_transfer_fee_config_tlv(self):
        value = bytearray(108)
        value[64:72] = (7).to_bytes(8, "little")
        value[72:80] = (100).to_bytes(8, "little")
        value[80:88] = (1_000).to_bytes(8, "little")
        value[88:90] = (250).to_bytes(2, "little")
        value[90:98] = (200).to_bytes(8, "little")
        value[98:106] = (2_000).to_bytes(8, "little")
        value[106:108] = (300).to_bytes(2, "little")
        data = (
            bytes(166)
            + (1).to_bytes(2, "little")
            + (108).to_bytes(2, "little")
            + bytes(value)
        )

        result = _parse_transfer_fee_config(data)

        self.assertEqual(result["withheld_amount"], 7)
        self.assertEqual(
            result["older_transfer_fee"],
            {"epoch": 100, "maximum_fee": 1_000, "basis_points": 250},
        )
        self.assertEqual(
            result["newer_transfer_fee"],
            {"epoch": 200, "maximum_fee": 2_000, "basis_points": 300},
        )

    def test_returns_none_when_transfer_fee_extension_is_absent(self):
        self.assertIsNone(_parse_transfer_fee_config(bytes(166)))

    def test_rejects_truncated_extension_tlv(self):
        data = (
            bytes(166)
            + (1).to_bytes(2, "little")
            + (108).to_bytes(2, "little")
            + bytes(20)
        )
        with self.assertRaisesRegex(ValueError, "TLV Token-2022 truncado"):
            _parse_transfer_fee_config(data)


if __name__ == "__main__":
    unittest.main()
