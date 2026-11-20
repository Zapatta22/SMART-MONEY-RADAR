import base64
import hashlib
import json
import unittest
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from smart_money_radar.domain.paper_evidence_gate import gate_paper_evidence, verify_paper_quote_tick
from smart_money_radar.domain.paper_replay import ReplayTick


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


class PaperRawQuoteTests(unittest.TestCase):
    def setUp(self):
        self.raw_quote = {
            "quote_id": "q0",
            "pool": "pool-a",
            "observed_at": "2026-11-19T12:00:00Z",
            "available_at": "2026-11-19T12:00:02Z",
            "price": "10.1",
            "volume": "25",
            "bid": "10.0",
            "ask": "10.2",
            "bid_size": "100",
            "ask_size": "125",
        }
        self.tick = ReplayTick(
            at=datetime.fromisoformat(self.raw_quote["available_at"]),
            market_at=datetime.fromisoformat(self.raw_quote["observed_at"]),
            price=Decimal("10.1"),
            volume=Decimal("25"),
            bid=Decimal("10"),
            ask=Decimal("10.2"),
            bid_size=Decimal("100"),
            ask_size=Decimal("125"),
            quote_id="q0",
        )

    def _record(self, *, raw=None, changes=None):
        if raw is None:
            raw = json.dumps({**self.raw_quote, **(changes or {})}).encode()
        return {
            "evidence_id": "receipt-q0", "pool": "pool-a",
            "observed_at": self.raw_quote["observed_at"],
            "available_at": self.raw_quote["available_at"],
            "source": "OBSERVED_MARKET_QUOTE", "is_observed_quote": True,
            "raw_capture_base64": base64.b64encode(raw).decode(),
            "raw_capture_sha256": hashlib.sha256(raw).hexdigest(),
        }

    def test_raw_bytes_bind_quote_and_tick(self):
        record = self._record()
        self.assertEqual(verify_paper_quote_tick(self.tick, [record], "pool-a"),
                         record["raw_capture_sha256"])

    def test_rejects_mutated_prices_depth_and_availability(self):
        for field, value in (
            ("price", "10.3"), ("bid", "9"), ("ask", "20"),
            ("volume", "30"), ("bid_size", "101"), ("ask_size", "124"),
            ("available_at", "2026-11-19T12:00:01Z"),
            ("observed_at", "2026-11-19T11:59:59Z"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "diverg"):
                verify_paper_quote_tick(self.tick, [self._record(changes={field: value})], "pool-a")
        late_tick = replace(self.tick, at=datetime.fromisoformat("2026-11-19T12:00:03Z"))
        with self.assertRaisesRegex(ValueError, "horários divergentes"):
            verify_paper_quote_tick(late_tick, [self._record()], "pool-a")

    def test_digest_and_raw_pool_are_both_checked(self):
        record = self._record()
        record["raw_capture_base64"] = self._record(changes={"price": "9"})["raw_capture_base64"]
        with self.assertRaisesRegex(ValueError, "SHA-256 divergente"):
            verify_paper_quote_tick(self.tick, [record], "pool-a")
        for field, value in (("pool", "pool-b"), ("quote_id", "q1")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "identidade ou pool"):
                verify_paper_quote_tick(self.tick, [self._record(changes={field: value})], "pool-a")

    def test_rejects_legacy_declarations_ambiguous_raw_and_boolean_numbers(self):
        record = self._record()
        record.pop("raw_capture_base64")
        with self.assertRaisesRegex(ValueError, "são obrigatórios"):
            verify_paper_quote_tick(self.tick, [record], "pool-a")
        raw = json.dumps(self.raw_quote).encode()[:-1] + b', "price": "10.1"}'
        with self.assertRaisesRegex(ValueError, "JSON RAW"):
            verify_paper_quote_tick(self.tick, [self._record(raw=raw)], "pool-a")
        with self.assertRaisesRegex(ValueError, "valor numérico"):
            verify_paper_quote_tick(self.tick, [self._record(changes={"volume": True})], "pool-a")


if __name__ == "__main__":
    unittest.main()
