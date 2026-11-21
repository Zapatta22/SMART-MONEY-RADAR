import unittest
from dataclasses import astuple
from fractions import Fraction
from math import ceil, floor

from smart_money_radar.domain.cpmm_integer_estimator import (
    CPMMFeeRates,
    estimate_exact_input,
    estimate_exact_output,
)


class CPMMIntegerEstimatorTests(unittest.TestCase):
    # Raydium cp-swap 3d69122790e97cd6aff24e8ba95940793773f58c,
    # curve/calculator.rs, curve/constant_product.rs and curve/fees.rs.
    def test_exact_input_vectors(self):
        for side, expected in (
            (True, (12345, 97413, 32, 15, 4, 5, True, 1246865, 9779130)),
            (False, (12345, 97417, 31, 122, 4, 5, False, 1246881, 9779004)),
        ):
            with self.subTest(creator_fee_on_input=side):
                result = estimate_exact_input(
                    reserve_in=1234567, reserve_out=9876543, amount_in=12345,
                    fees=CPMMFeeRates(2500, 1250, 130000, 170000, side),
                )
                self.assertEqual(astuple(result), expected)

    def test_exact_output_vectors(self):
        for side, expected in (
            (True, (12332, 97311, 32, 15, 4, 5, True, 1246852, 9779232)),
            (False, (12332, 97311, 31, 122, 4, 5, False, 1246868, 9779110)),
        ):
            with self.subTest(creator_fee_on_input=side):
                result = estimate_exact_output(
                    reserve_in=1234567, reserve_out=9876543, amount_out=97311,
                    fees=CPMMFeeRates(2500, 1250, 130000, 170000, side),
                )
                self.assertEqual(astuple(result), expected)

    def test_parity_with_fraction_reference_in_both_directions(self):
        for x, y in ((997, 211), (211, 997)):
            for trade_rate, creator_rate in ((0, 0), (0, 3333), (12345, 0), (125001, 35007)):
                for side in (True, False):
                    if side and trade_rate + creator_rate == 0:
                        continue
                    fees = CPMMFeeRates(trade_rate, creator_rate, 299999, 121337, side)
                    trade = Fraction(trade_rate, 1_000_000)
                    creator = Fraction(creator_rate, 1_000_000)
                    input_rate = trade + creator if side else trade
                    for amount in (1, 2, 17, 100):
                        with self.subTest(x=x, y=y, fees=fees, amount=amount):
                            input_fee = ceil(amount * input_rate)
                            net = amount - input_fee
                            gross = floor(Fraction(net * y, x + net))
                            self.assert_swap(
                                estimate_exact_input(reserve_in=x, reserve_out=y, amount_in=amount, fees=fees),
                                x, y, amount, gross if side else gross - ceil(gross * creator),
                                net, gross, input_fee, input_rate, creator, side,
                            )

                            gross = amount if side else ceil(amount / (1 - creator))
                            net = ceil(Fraction(x * gross, y - gross))
                            required = ceil(net / (1 - input_rate))
                            self.assert_swap(
                                estimate_exact_output(reserve_in=x, reserve_out=y, amount_out=amount, fees=fees),
                                x, y, required, amount, net, gross, required - net,
                                input_rate, creator, side,
                            )

    def assert_swap(self, result, x, y, amount_in, amount_out, net, gross, input_fee,
                    input_rate, creator, side):
        creator_fee = floor(input_fee * creator / input_rate) if side else gross - amount_out
        trade_fee = input_fee - creator_fee if side else input_fee
        self.assertEqual(
            astuple(result),
            (amount_in, amount_out, trade_fee, creator_fee,
             floor(trade_fee * Fraction(299999, 1_000_000)),
             floor(trade_fee * Fraction(121337, 1_000_000)),
             side, x + net, y - gross),
        )

    def test_rejects_gross_output_at_reserve_and_input_outside_u64(self):
        fees = CPMMFeeRates(0, 100_000, 0, 0, False)
        with self.assertRaisesRegex(ValueError, "gross output"):
            estimate_exact_output(reserve_in=100, reserve_out=10, amount_out=9, fees=fees)
        with self.assertRaisesRegex(ValueError, "positive u64"):
            estimate_exact_output(reserve_in=2**64 - 1, reserve_out=10, amount_out=8, fees=fees)
        with self.assertRaisesRegex(ValueError, "positive u64"):
            estimate_exact_input(reserve_in=100, reserve_out=10, amount_in=True, fees=fees)

    def test_rejects_undefined_fee_arithmetic(self):
        with self.assertRaisesRegex(ValueError, "zero total rate"):
            CPMMFeeRates(0, 0, 0, 0, True)
        with self.assertRaisesRegex(ValueError, "below 100%"):
            CPMMFeeRates(500_000, 500_000, 0, 0, True)
        with self.assertRaisesRegex(ValueError, "shares exceed"):
            CPMMFeeRates(2500, 0, 600_000, 600_000, False)
