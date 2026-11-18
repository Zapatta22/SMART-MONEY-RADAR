import unittest

from smart_money_radar.domain.program_registry import (
    PROGRAMS, PROGRAMS_BY_ID, get_program_spec, validate_registry,
)


class ProgramRegistryTests(unittest.TestCase):
    def test_registry_has_unique_valid_32_byte_program_ids(self):
        validate_registry()
        self.assertEqual(len(PROGRAMS), len(PROGRAMS_BY_ID))

    def test_jupiter_is_an_aggregator_not_a_venue(self):
        spec = get_program_spec("JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.kind, "aggregator")
        self.assertFalse(spec.venue)

    def test_pump_curve_and_pumpswap_are_distinct_programs(self):
        curve = get_program_spec("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
        amm = get_program_spec("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
        self.assertEqual(curve.kind, "launchpad")
        self.assertEqual(amm.kind, "amm")

    def test_unknown_program_is_not_guessed(self):
        self.assertIsNone(get_program_spec("11111111111111111111111111111112"))


if __name__ == "__main__":
    unittest.main()
