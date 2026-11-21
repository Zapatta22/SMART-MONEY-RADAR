"""CM38J offline economic provenance and lookahead adversarial checks."""
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from smart_money_radar.services.cm38j_metric_provenance import (
    describe_metric, qualify_metric_set, LAUNCH_INDICATORS,
    SMART_MONEY_INDICATORS,
)


class TestCm38JMetricProvenance(unittest.TestCase):
    def setUp(self):
        self.at = datetime.now(timezone.utc) - timedelta(minutes=1)
        self.args = dict(name="liquidity", value=None, start=self.at,
                         end=self.at, available_at=self.at,
                         decision_at=self.at, quality="UNKNOWN",
                         unavailable_reason="source_unavailable")

    def test_missing_value_requires_explicit_reason(self):
        self.args["unavailable_reason"] = None
        with self.assertRaises(ValueError):
            describe_metric(**self.args)

    def test_future_availability_rejected(self):
        self.args["available_at"] = self.at + timedelta(seconds=1)
        with self.assertRaises(ValueError):
            describe_metric(**self.args)

    def test_numeric_value_without_provenance_rejected(self):
        self.args.update(value=Decimal("120"), unavailable_reason=None)
        with self.assertRaises(ValueError):
            describe_metric(**self.args)

    def test_verified_value_is_stably_digestible_but_not_authorization(self):
        self.args.update(value=Decimal("120"), unavailable_reason=None,
                         quality="VERIFIED", source_id="market-rpc",
                         evidence_ids=("a" * 64,))
        first = describe_metric(**self.args)
        self.assertEqual(first, describe_metric(**self.args))
        self.assertFalse(first["operational_authorized"])
        self.assertFalse(first["prospective_paper_authorized"])

    def test_separate_metric_scopes_for_two_radars(self):
        self.assertEqual(len(LAUNCH_INDICATORS), 9)
        self.assertEqual(len(SMART_MONEY_INDICATORS), 9)
        launch = qualify_metric_set(radar="launch", metrics=[
            describe_metric(**self.args)])
        smart = qualify_metric_set(radar="smart_money", metrics=[])
        self.assertFalse(launch["qualified"])
        self.assertFalse(smart["qualified"])
        self.assertIn("realized_pnl", smart["missing"])
        self.assertEqual(launch["strategies"]["immediate"], "BLOCKED")
        self.assertEqual(launch["strategies"]["confirmed"], "BLOCKED")

    def test_cross_radar_indicator_rejected(self):
        with self.assertRaises(ValueError):
            qualify_metric_set(radar="smart_money", metrics=[
                describe_metric(**self.args)])

    def test_invalid_or_future_decision_rejected(self):
        self.args["decision_at"] = datetime.now(timezone.utc) + timedelta(days=1)
        with self.assertRaises(ValueError):
            describe_metric(**self.args)


if __name__ == "__main__":
    unittest.main()
