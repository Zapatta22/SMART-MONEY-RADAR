import base64
import json
import unittest

from smart_money_radar.data_sources.helius_historical_account import (
    get_historical_account_info,
    get_historical_account_info_before_transaction,
)


class FakeResponse:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.raw


class HeliusHistoricalAccountTests(unittest.TestCase):
    def setUp(self):
        self.address = "Mint111111111111111111111111111111111111111"
        self.account_data = b"historical-mint-bytes"
        self.payload = {
            "jsonrpc": "2.0",
            "id": "smr-historical-account",
            "result": {
                "context": {"slot": 500000000},
                "value": {
                    "data": [base64.b64encode(self.account_data).decode(), "base64"],
                    "executable": False,
                    "lamports": 123,
                    "owner": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
                    "rentEpoch": 99,
                    "lastUpdatedAt": {"slot": 471107300, "transactionIndex": 12},
                },
            },
        }

    def opener_for(self, payload, captured):
        def opener(request, timeout):
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return FakeResponse(payload)
        return opener

    def test_reads_account_at_exact_slot_and_transaction_index(self):
        captured = {}
        snapshot = get_historical_account_info(
            "https://mainnet.helius-rpc.com/?api-key=test",
            self.address, 471107341, 13,
            opener=self.opener_for(self.payload, captured),
        )
        self.assertEqual(snapshot.data, self.account_data)
        self.assertEqual(snapshot.queried_slot, 471107341)
        self.assertEqual(snapshot.queried_transaction_index, 13)
        self.assertEqual(snapshot.last_updated_slot, 471107300)
        self.assertEqual(snapshot.last_updated_transaction_index, 12)
        self.assertEqual(captured["body"]["method"], "getHistoricalAccountInfo")
        self.assertEqual(captured["body"]["params"][1], {
            "slot": 471107341, "transactionIndex": 13,
        })
        self.assertEqual(captured["body"]["params"][2]["commitment"], "finalized")

    def test_reads_state_before_nonzero_transaction_index(self):
        captured = {}
        snapshot = get_historical_account_info_before_transaction(
            "https://mainnet.helius-rpc.com", self.address, 471107341, 13,
            opener=self.opener_for(self.payload, captured),
        )
        self.assertEqual(snapshot.queried_slot, 471107341)
        self.assertEqual(snapshot.queried_transaction_index, 12)
        self.assertEqual(captured["body"]["params"][1], {
            "slot": 471107341, "transactionIndex": 12,
        })

    def test_reads_previous_slot_before_first_transaction(self):
        captured = {}
        snapshot = get_historical_account_info_before_transaction(
            "https://mainnet.helius-rpc.com", self.address, 471107341, 0,
            opener=self.opener_for(self.payload, captured),
        )
        self.assertEqual(snapshot.queried_slot, 471107340)
        self.assertIsNone(snapshot.queried_transaction_index)
        self.assertEqual(captured["body"]["params"][1], {"slot": 471107340})

    def test_rejects_account_state_written_after_query_position(self):
        payload = json.loads(json.dumps(self.payload))
        payload["result"]["value"]["lastUpdatedAt"] = {
            "slot": 471107342, "transactionIndex": 0,
        }
        with self.assertRaisesRegex(ValueError, "posterior"):
            get_historical_account_info(
                "https://mainnet.helius-rpc.com", self.address, 471107341, 13,
                opener=self.opener_for(payload, {}),
            )

    def test_rejects_missing_account_and_rpc_errors(self):
        payload = {
            "jsonrpc": "2.0", "id": "smr-historical-account",
            "result": {"value": None},
        }
        with self.assertRaisesRegex(ValueError, "ausente"):
            get_historical_account_info(
                "https://mainnet.helius-rpc.com", self.address, 471107341,
                opener=self.opener_for(payload, {}),
            )
        payload = {
            "jsonrpc": "2.0", "id": "smr-historical-account",
            "error": {"code": -32018, "message": "private endpoint detail"},
        }
        with self.assertRaisesRegex(RuntimeError, "code=-32018") as caught:
            get_historical_account_info(
                "https://mainnet.helius-rpc.com", self.address, 471107341,
                opener=self.opener_for(payload, {}),
            )
        self.assertNotIn("private endpoint detail", str(caught.exception))

    def test_rejects_non_https_endpoint_and_invalid_position(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            get_historical_account_info("http://localhost", self.address, 1)
        with self.assertRaisesRegex(ValueError, "transaction_index"):
            get_historical_account_info(
                "https://mainnet.helius-rpc.com", self.address, 1, -1
            )


if __name__ == "__main__":
    unittest.main()
