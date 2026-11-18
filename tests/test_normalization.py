import unittest
from datetime import datetime, timezone
from decimal import Decimal

from smart_money_radar.domain.normalization import normalize_transaction


class TransactionNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.wallet = "wallet-a"
        self.raw = {
            "slot": 123,
            "blockTime": 1_730_000_000,
            "meta": {
                "err": None,
                "preTokenBalances": [{"owner": self.wallet, "mint": "mint-a",
                                      "uiTokenAmount": {"amount": "100", "decimals": 2}}],
                "postTokenBalances": [{"owner": self.wallet, "mint": "mint-a",
                                       "uiTokenAmount": {"amount": "300", "decimals": 2}}],
                "innerInstructions": [],
            },
            "transaction": {"message": {"instructions": []}},
        }

    def test_normalizes_envelope_and_preserves_legacy_events(self):
        observed = datetime(2026, 11, 16, tzinfo=timezone.utc)
        result = normalize_transaction(self.raw, self.wallet, "sig-a", observed_at=observed)
        self.assertEqual(result.transaction.parse_status, "parsed")
        self.assertEqual(result.transaction.slot, 123)
        self.assertEqual(result.transaction.observed_at, observed)
        self.assertEqual(len(result.activity_events), 1)
        self.assertEqual(len(result.token_deltas), 1)
        self.assertEqual(result.token_deltas[0].amount, Decimal("2"))
        self.assertEqual(result.token_deltas[0].token_mint, "mint-a")
        self.assertEqual(result.token_deltas[0].decimals, 2)

    def test_marks_unknown_parser_result_as_no_events_and_keeps_raw_payload(self):
        raw = {"meta": {"err": None}, "transaction": {"message": {"instructions": []}}}
        result = normalize_transaction(raw, self.wallet, "sig-b")
        self.assertEqual(result.transaction.parse_status, "no_events")
        self.assertEqual(result.transaction.raw_transaction, raw)
        self.assertEqual(result.token_deltas, ())

    def test_marks_on_chain_failure(self):
        raw = {"meta": {"err": {"InstructionError": [0, "Custom"]}}}
        result = normalize_transaction(raw, self.wallet, "sig-c")
        self.assertEqual(result.transaction.parse_status, "failed_on_chain")
        self.assertEqual(result.activity_events, ())

    def test_rejects_non_object_payload(self):
        with self.assertRaises(TypeError):
            normalize_transaction([], self.wallet, "sig-d")

    def test_rejects_missing_identifiers(self):
        with self.assertRaises(ValueError):
            normalize_transaction(self.raw, "", "sig-e")
