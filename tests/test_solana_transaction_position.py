import json
import unittest

from smart_money_radar.data_sources.solana_transaction_position import get_transaction_index


class FakeResponse:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.raw


class SolanaTransactionPositionTests(unittest.TestCase):
    def payload(self, transactions):
        return {
            "jsonrpc": "2.0",
            "id": "smr-transaction-position",
            "result": {"blockHeight": 1, "transactions": transactions},
        }

    def opener_for(self, payload, captured):
        def opener(request, timeout):
            captured["body"] = json.loads(request.data)
            return FakeResponse(payload)
        return opener

    def test_returns_zero_based_position_of_primary_signature(self):
        captured = {}
        txs = [
            {"transaction": {"signatures": ["sig-a"]}},
            {"transaction": {"signatures": ["sig-b", "secondary"]}},
            {"transaction": {"signatures": ["sig-c"]}},
        ]
        result = get_transaction_index(
            "https://api.mainnet-beta.solana.com", 471107341, "sig-b",
            opener=self.opener_for(self.payload(txs), captured),
        )
        self.assertEqual(result, 1)
        request = captured["body"]
        self.assertEqual(request["method"], "getBlock")
        self.assertEqual(request["params"][0], 471107341)
        self.assertEqual(request["params"][1]["transactionDetails"], "full")
        self.assertEqual(request["params"][1]["maxSupportedTransactionVersion"], 1)

    def test_rejects_missing_signature_and_duplicate_primary_signature(self):
        with self.assertRaisesRegex(ValueError, "não encontrada"):
            get_transaction_index(
                "https://rpc.example", 10, "missing",
                opener=self.opener_for(self.payload([
                    {"transaction": {"signatures": ["sig-a"]}},
                ]), {}),
            )
        with self.assertRaisesRegex(ValueError, "duplicada"):
            get_transaction_index(
                "https://rpc.example", 10, "sig-a",
                opener=self.opener_for(self.payload([
                    {"transaction": {"signatures": ["sig-a"]}},
                    {"transaction": {"signatures": ["sig-a"]}},
                ]), {}),
            )

    def test_rejects_malformed_block_and_rpc_error(self):
        with self.assertRaisesRegex(RuntimeError, "sem lista"):
            get_transaction_index(
                "https://rpc.example", 10, "sig-a",
                opener=self.opener_for({
                    "jsonrpc": "2.0", "id": "smr-transaction-position",
                    "result": {},
                }, {}),
            )
        with self.assertRaisesRegex(RuntimeError, "code=-32004"):
            get_transaction_index(
                "https://rpc.example", 10, "sig-a",
                opener=self.opener_for({
                    "jsonrpc": "2.0", "id": "smr-transaction-position",
                    "error": {"code": -32004, "message": "internal"},
                }, {}),
            )

    def test_rejects_invalid_slot_signature_and_http(self):
        for args in (
            ("http://localhost", 1, "sig"),
            ("https://rpc.example", -1, "sig"),
            ("https://rpc.example", 1, ""),
        ):
            with self.assertRaises(ValueError):
                get_transaction_index(*args)


if __name__ == "__main__":
    unittest.main()
