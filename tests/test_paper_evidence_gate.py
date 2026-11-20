import unittest
from smart_money_radar.domain.paper_evidence_gate import gate_paper_evidence


class PaperEvidenceGateTests(unittest.TestCase):
    def item(self):
        return dict(evidence_id="a", pool="pool-a",
                    observed_at="2026-11-19T12:00:00Z",
                    available_at="2026-11-19T12:00:02Z",
                    source="MODEL_ESTIMATE_NOT_OBSERVED",
                    is_observed_quote=False)

    def check(self, items=None, **kwargs):
        args = dict(signal_at="2026-11-19T12:00:00Z",
                    decision_at="2026-11-19T12:00:03Z",
                    evidence=[self.item()] if items is None else items,
                    expected_pool="pool-a")
        args.update(kwargs)
        return gate_paper_evidence(**args)

    def test_allows_model_for_non_executable_paper_analysis(self):
        self.assertEqual(len(self.check()), 1)

    def test_blocks_model_as_observed_quote(self):
        with self.assertRaisesRegex(ValueError, "não é cotação"):
            self.check(require_observed_quote=True)

    def test_blocks_future_evidence_and_future_availability(self):
        for field, timestamp in (
            ("available_at", "2026-11-19T12:00:04Z"),
            ("observed_at", "2026-11-19T12:00:04Z"),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check([{**self.item(), field: timestamp}])

    def test_rejects_pool_mismatch_duplicates_and_false_observed_flag(self):
        with self.assertRaises(ValueError):
            self.check([{**self.item(), "pool": "another"}])
        with self.assertRaises(ValueError):
            self.check([self.item(), self.item()])
        with self.assertRaises(ValueError):
            self.check([{**self.item(), "is_observed_quote": True}])

    def test_accepts_observed_quote_only_when_explicit(self):
        item = {**self.item(), "source": "OBSERVED_MARKET_QUOTE",
                "is_observed_quote": True}
        self.assertEqual(len(self.check([item], require_observed_quote=True)), 1)

    def test_rejects_naive_times_and_early_decision(self):
        with self.assertRaises(ValueError):
            self.check(decision_at="2026-11-19T12:00:03")
        with self.assertRaises(ValueError):
            self.check(decision_at="2026-11-19T11:59:59Z")


if __name__ == "__main__":
    unittest.main()
