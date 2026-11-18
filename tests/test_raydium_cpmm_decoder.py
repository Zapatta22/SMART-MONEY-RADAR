import unittest

from smart_money_radar.data_sources.raydium_cpmm_decoder import (
    RAYDIUM_CPMM_PROGRAM_ID,
    SWAP_BASE_INPUT_DISCRIMINATOR,
    SWAP_BASE_OUTPUT_DISCRIMINATOR,
    RaydiumCpmmSwapBaseInput,
    RaydiumCpmmSwapBaseOutput,
    decode_raydium_cpmm_instruction,
)


def _encode(discriminator, first, second):
    return (
        discriminator
        + first.to_bytes(8, "little")
        + second.to_bytes(8, "little")
    )


class TestRaydiumCpmmDecoder(unittest.TestCase):
    def test_decodes_exact_input(self):
        result = decode_raydium_cpmm_instruction(
            RAYDIUM_CPMM_PROGRAM_ID,
            _encode(SWAP_BASE_INPUT_DISCRIMINATOR, 123, 456),
        )
        self.assertEqual(result, RaydiumCpmmSwapBaseInput(123, 456))

    def test_decodes_exact_output(self):
        result = decode_raydium_cpmm_instruction(
            RAYDIUM_CPMM_PROGRAM_ID,
            _encode(SWAP_BASE_OUTPUT_DISCRIMINATOR, 789, 321),
        )
        self.assertEqual(result, RaydiumCpmmSwapBaseOutput(789, 321))

    def test_returns_none_for_other_program(self):
        result = decode_raydium_cpmm_instruction(
            "11111111111111111111111111111111",
            _encode(SWAP_BASE_OUTPUT_DISCRIMINATOR, 1, 2),
        )
        self.assertIsNone(result)

    def test_returns_none_for_unknown_instruction(self):
        result = decode_raydium_cpmm_instruction(
            RAYDIUM_CPMM_PROGRAM_ID,
            b"\x00" * 24,
        )
        self.assertIsNone(result)

    def test_rejects_non_bytes(self):
        with self.assertRaises(TypeError):
            decode_raydium_cpmm_instruction(RAYDIUM_CPMM_PROGRAM_ID, "data")

    def test_rejects_empty_data(self):
        with self.assertRaises(ValueError):
            decode_raydium_cpmm_instruction(RAYDIUM_CPMM_PROGRAM_ID, b"")

    def test_rejects_truncated_exact_output(self):
        with self.assertRaisesRegex(ValueError, "exige 24 bytes"):
            decode_raydium_cpmm_instruction(
                RAYDIUM_CPMM_PROGRAM_ID,
                SWAP_BASE_OUTPUT_DISCRIMINATOR + b"\x01",
            )


if __name__ == "__main__":
    unittest.main()
