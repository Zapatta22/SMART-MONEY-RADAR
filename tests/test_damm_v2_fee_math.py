import unittest

from smart_money_radar.data_sources.damm_v2_fee_math import (
    DAMM_FEE_DENOMINATOR,
    U64_MAX,
    amm_fee_excluded_amount,
    amm_fee_included_amount,
    calculate_transfer_fee,
    resolve_damm_fee_mode,
    split_amm_fee,
    transfer_fee_from_gross,
    transfer_fee_gross_for_net,
)


class Token2022TransferFeeMathTests(unittest.TestCase):
    def test_rounds_up_and_caps_fee(self):
        self.assertEqual(calculate_transfer_fee(1, 1, 100), 1)
        self.assertEqual(calculate_transfer_fee(10_001, 1, 100), 2)
        self.assertEqual(calculate_transfer_fee(10_000, 1, 1), 1)
        self.assertEqual(calculate_transfer_fee(1_000_000, 100, 50), 50)

    def test_zero_rate_zero_amount_and_zero_cap(self):
        self.assertEqual(calculate_transfer_fee(123, 0, 99), 0)
        self.assertEqual(calculate_transfer_fee(0, 500, 99), 0)
        self.assertEqual(calculate_transfer_fee(123, 10_000, 0), 0)

    def test_gross_to_net_and_inverse(self):
        actual = transfer_fee_from_gross(10_001, 100, 1_000)
        self.assertEqual((actual.gross_amount, actual.fee_amount, actual.net_amount), (10_001, 101, 9_900))
        inverse = transfer_fee_gross_for_net(9_900, 100, 1_000)
        # The inverse selects the smallest gross: 10_000 also nets 9_900.
        self.assertEqual((inverse.gross_amount, inverse.fee_amount, inverse.net_amount), (10_000, 100, 9_900))
        self.assertNotEqual(inverse, actual)

    def test_inverse_chooses_a_gross_that_reproduces_requested_net(self):
        # At 10%, gross 10 and 11 both produce net 9; Token-2022 chooses 10.
        result = transfer_fee_gross_for_net(9, 1_000, 100)
        self.assertEqual((result.gross_amount, result.fee_amount, result.net_amount), (10, 1, 9))

    def test_maximum_fee_cap_inverse(self):
        result = transfer_fee_gross_for_net(10_000, 100, 7)
        self.assertEqual((result.gross_amount, result.fee_amount, result.net_amount), (10_007, 7, 10_000))

    def test_full_rate_uses_maximum_fee_in_inverse(self):
        result = transfer_fee_gross_for_net(100, 10_000, 25)
        self.assertEqual((result.gross_amount, result.fee_amount, result.net_amount), (125, 25, 100))

    def test_zero_net_is_zero_even_at_full_rate(self):
        self.assertEqual(transfer_fee_gross_for_net(0, 10_000, 25).gross_amount, 0)

    def test_rejects_invalid_and_overflowing_inputs(self):
        with self.assertRaises(ValueError):
            calculate_transfer_fee(1, 10_001, 1)
        with self.assertRaises(ValueError):
            calculate_transfer_fee(True, 1, 1)
        with self.assertRaises(OverflowError):
            transfer_fee_gross_for_net(U64_MAX, 1, U64_MAX)


class AmmFeeMathTests(unittest.TestCase):
    def test_excluded_fee_uses_ceiling(self):
        # 1 raw unit at any positive rate rounds up to 1.
        self.assertEqual(amm_fee_excluded_amount(1, 1), (0, 1))
        self.assertEqual(amm_fee_excluded_amount(1_000_000, 10_000_000), (990_000, 10_000))

    def test_included_fee_uses_ceiling(self):
        included, fee = amm_fee_included_amount(990_000, 10_000_000)
        self.assertEqual((included, fee), (1_000_000, 10_000))

    def test_excluded_and_included_are_not_assumed_to_be_exact_inverses(self):
        included, fee = amm_fee_included_amount(9, DAMM_FEE_DENOMINATOR // 10)
        net, fee_again = amm_fee_excluded_amount(included, DAMM_FEE_DENOMINATOR // 10)
        self.assertGreaterEqual(net, 9)
        self.assertLessEqual(net - 9, 1)
        self.assertEqual(included - fee, 9)
        self.assertEqual(fee_again, included - net)

    def test_zero_amount_and_zero_fee(self):
        self.assertEqual(amm_fee_excluded_amount(0, 0), (0, 0))
        self.assertEqual(amm_fee_included_amount(0, 10), (0, 0))
        self.assertEqual(amm_fee_excluded_amount(123, 0), (123, 0))
        self.assertEqual(amm_fee_included_amount(123, 0), (123, 0))

    def test_excluded_fee_supports_full_rate_but_included_fee_rejects_it(self):
        self.assertEqual(
            amm_fee_excluded_amount(123, DAMM_FEE_DENOMINATOR), (0, 123)
        )
        with self.assertRaises(ValueError):
            amm_fee_excluded_amount(1, DAMM_FEE_DENOMINATOR + 1)
        with self.assertRaises(ValueError):
            amm_fee_included_amount(1, DAMM_FEE_DENOMINATOR)


class AmmFeeSplitAndModeTests(unittest.TestCase):
    def test_fee_split_keeps_referral_separate_from_net_protocol_fee(self):
        result = split_amm_fee(1_001, 20, 25, 2_500, True)
        self.assertEqual(result.protocol_fee, 150)
        self.assertEqual(result.referral_fee, 50)
        self.assertEqual(result.compounding_fee, 200)
        self.assertEqual(result.claiming_fee, 601)
        self.assertEqual(
            result.claiming_fee + result.compounding_fee + result.protocol_fee + result.referral_fee,
            result.total_fee,
        )

    def test_fee_split_without_referral(self):
        result = split_amm_fee(1_001, 20, 25, 2_500, False)
        self.assertEqual(result.protocol_fee, 200)
        self.assertEqual(result.referral_fee, 0)

    def test_fee_split_rounds_protocol_referral_and_compounding_down(self):
        result = split_amm_fee(9, 50, 50, 5_000, True)
        self.assertEqual(result.protocol_fee, 2)
        self.assertEqual(result.referral_fee, 2)
        self.assertEqual(result.compounding_fee, 2)
        self.assertEqual(result.claiming_fee, 3)

    def test_all_six_collect_mode_direction_combinations(self):
        expected = {
            ("BOTH_TOKEN", "A_TO_B"): (False, False),
            ("BOTH_TOKEN", "B_TO_A"): (False, True),
            ("ONLY_B", "A_TO_B"): (False, False),
            ("ONLY_B", "B_TO_A"): (True, False),
            ("COMPOUNDING", "A_TO_B"): (False, False),
            ("COMPOUNDING", "B_TO_A"): (True, False),
        }
        for (collect, direction), (on_input, on_a) in expected.items():
            with self.subTest(collect=collect, direction=direction):
                result = resolve_damm_fee_mode(collect, direction, True)
                self.assertEqual((result.fees_on_input, result.fees_on_token_a), (on_input, on_a))
                self.assertTrue(result.has_referral)

    def test_rejects_unknown_fee_mode_and_non_boolean_referral(self):
        with self.assertRaises(ValueError):
            resolve_damm_fee_mode("UNKNOWN", "A_TO_B", False)
        with self.assertRaises(ValueError):
            resolve_damm_fee_mode("ONLY_B", "A_TO_B", 1)

    def test_inverse_is_minimal_across_small_fee_parameter_grid(self):
        for basis_points in (0, 1, 100, 3_333, 9_999, 10_000):
            for maximum_fee in (0, 1, 3, 20):
                for net_amount in range(0, 20):
                    with self.subTest(
                        basis_points=basis_points,
                        maximum_fee=maximum_fee,
                        net_amount=net_amount,
                    ):
                        result = transfer_fee_gross_for_net(
                            net_amount, basis_points, maximum_fee
                        )
                        self.assertEqual(
                            result.gross_amount - result.fee_amount, net_amount
                        )
                        if result.gross_amount > 0:
                            previous_gross = result.gross_amount - 1
                            previous_net = previous_gross - calculate_transfer_fee(
                                previous_gross, basis_points, maximum_fee
                            )
                            self.assertLess(previous_net, net_amount)


if __name__ == "__main__":
    unittest.main()
