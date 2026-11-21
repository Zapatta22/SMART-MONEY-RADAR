import base64
import hashlib
import json
import unittest
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from smart_money_radar.domain.paper_evidence_gate import (
    gate_paper_evidence,
    load_pinned_paper_quote_manifest,
    verify_paper_quote_tick,
)
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

    def _manifest_bytes(self, *, pool="pool-a", quote_id="q0", quote_hash=None):
        return json.dumps({
            "schema": "smr-paper-quote-manifest-v1",
            "pool": pool,
            "quotes": {quote_id: quote_hash or self._record()["raw_capture_sha256"]},
        }).encode()

    def test_pinned_manifest_accepts_matching_bytes_and_quote(self):
        raw = self._manifest_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        manifest = load_pinned_paper_quote_manifest(raw, expected_sha256=digest)
        record = self._record()
        self.assertEqual(manifest.sha256, digest)
        self.assertEqual(verify_paper_quote_tick(self.tick, [record], "pool-a", manifest=manifest),
                         record["raw_capture_sha256"])
        with self.assertRaises(TypeError):
            manifest.quote_digests["q0"] = "a" * 64

    def test_pinned_manifest_rejects_rehashed_quote_and_manifest(self):
        initial = self._manifest_bytes()
        digest = hashlib.sha256(initial).hexdigest()
        manifest = load_pinned_paper_quote_manifest(initial, expected_sha256=digest)
        updated_quote = self._record(changes={"price": "9.1"})
        updated_tick = replace(self.tick, price=Decimal("9.1"))
        self.assertEqual(verify_paper_quote_tick(updated_tick, [updated_quote], "pool-a"),
                         updated_quote["raw_capture_sha256"])
        with self.assertRaisesRegex(ValueError, "diverge do manifesto fixado"):
            verify_paper_quote_tick(updated_tick, [updated_quote], "pool-a", manifest=manifest)
        forged_manifest = self._manifest_bytes(quote_hash=updated_quote["raw_capture_sha256"])
        with self.assertRaisesRegex(ValueError, "diverge do valor fixado"):
            load_pinned_paper_quote_manifest(forged_manifest, expected_sha256=digest)

    def test_pinned_manifest_rejects_wrong_pool_and_missing_quote(self):
        for raw, error in (
            (self._manifest_bytes(pool="pool-b"), "fora do pool"),
            (self._manifest_bytes(quote_id="q1"), "ausente do manifesto"),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                manifest = load_pinned_paper_quote_manifest(raw, expected_sha256=hashlib.sha256(raw).hexdigest())
                verify_paper_quote_tick(self.tick, [self._record()], "pool-a", manifest=manifest)

    def test_pinned_manifest_validates_schema_and_rejects_duplicate_fields(self):
        for raw, error in (
            (b'{"schema":"smr-unknown"}', "schema"),
            (b'{"schema":"smr-paper-quote-manifest-v1","pool":"p","pool":"q"}', "JSON"),
            (self._manifest_bytes(quote_hash="unknown"), "identidades ou hashes"),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                load_pinned_paper_quote_manifest(raw, expected_sha256=hashlib.sha256(raw).hexdigest())

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
