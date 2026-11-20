"""Offline tests for the conservative CPMM reserve estimator."""
import unittest
from decimal import Decimal
from smart_money_radar.domain.cpmm_reserve_estimator import estimate_exact_input


class CPMMReserveEstimatorTests(unittest.TestCase):
    def quote(self, **overrides):
        args = dict(pool="pool-a", slot=123, reserve_in="1000",
                    reserve_out="2000", amount_in="10", fee_bps="30")
        args.update(overrides)
        return estimate_exact_input(**args)

    def test_estimate_is_not_observed_quote(self):
        quote = self.quote()
        self.assertFalse(quote.is_observed_quote)
        self.assertEqual(quote.source, "MODEL_ESTIMATE_NOT_OBSERVED")
        self.assertEqual(quote.slot, 123)
        self.assertEqual(quote.pool, "pool-a")
        self.assertGreater(quote.estimated_output, Decimal("0"))
        self.assertLess(quote.estimated_output, Decimal("20"))
        self.assertGreater(quote.price_impact_fraction, 0)

    def test_zero_fee_constant_product(self):
        quote = self.quote(fee_bps=0, amount_in="100")
        self.assertLess(abs(quote.estimated_output - Decimal(2000) * 100 / 1100), Decimal("1e-20"))

    def test_larger_input_has_worse_average_price(self):
        self.assertLess(self.quote(amount_in="100").average_execution_price,
                        self.quote(amount_in="1").average_execution_price)

    def test_rejects_bad_reserves_and_amounts(self):
        for key, value in (("reserve_in", 0), ("reserve_out", "-1"),
                           ("amount_in", "NaN"), ("reserve_in", "Infinity"),
                           ("amount_in", True)):
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    self.quote(**{key: value})

    def test_rejects_bad_fee_slot_and_pool(self):
        for changes in (dict(fee_bps=10000), dict(fee_bps=-1),
                        dict(fee_bps="NaN"), dict(fee_bps=True),
                        dict(slot=-1), dict(slot=True), dict(pool="")):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.quote(**changes)


if __name__ == "__main__":
    unittest.main()
