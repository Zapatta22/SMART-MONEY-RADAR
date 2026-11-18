import json
import unittest
from urllib.request import Request

from smart_money_radar.data_sources.helius import HeliusDataSource, HeliusRpcError
from smart_money_radar.settings import HeliusSettings


class FakeResponse:
    def __init__(self, value: dict[str, object]) -> None:
        self.body = json.dumps(value).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class HeliusRpcTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = HeliusSettings(api_key="simulated-key")

    def test_get_version_uses_read_only_json_rpc(self) -> None:
        captured: dict[str, object] = {}

        def fake_opener(request: Request, timeout: float) -> FakeResponse:
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse(
                {"jsonrpc": "2.0", "id": 1, "result": {"solana-core": "simulated"}}
            )

        source = HeliusDataSource(self.settings, opener=fake_opener)
        result = source.get_version()

        request = captured["request"]
        self.assertEqual(result["solana-core"], "simulated")
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data)["method"], "getVersion")
        self.assertEqual(captured["timeout"], self.settings.request_timeout_seconds)

    def test_transaction_request_uses_json_parsed_confirmed_mode(self) -> None:
        captured: list[dict[str, object]] = []

        def fake_opener(request: Request, timeout: float) -> FakeResponse:
            captured.append(json.loads(request.data))
            return FakeResponse({"jsonrpc": "2.0", "id": 1, "result": None})

        source = HeliusDataSource(self.settings, opener=fake_opener)

        self.assertIsNone(source.get_transaction("simulated-signature"))
        self.assertEqual(captured[0]["method"], "getTransaction")
        self.assertEqual(
            captured[0]["params"][1],
            {
                "commitment": "confirmed",
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
            },
        )

    def test_rejects_mismatched_json_rpc_response_id(self) -> None:
        source = HeliusDataSource(
            self.settings,
            opener=lambda *_args, **_kwargs: FakeResponse(
                {"jsonrpc": "2.0", "id": 999, "result": {"solana-core": "wrong-request"}}
            ),
        )
        with self.assertRaisesRegex(HeliusRpcError, "ID incompatível"):
            source.get_version()

    def test_rejects_boolean_json_rpc_response_id(self) -> None:
        source = HeliusDataSource(
            self.settings,
            opener=lambda *_args, **_kwargs: FakeResponse(
                {"jsonrpc": "2.0", "id": True, "result": {"solana-core": "invalid-id"}}
            ),
        )
        with self.assertRaisesRegex(HeliusRpcError, "ID incompatível"):
            source.get_version()

    def test_rejects_missing_json_rpc_version(self) -> None:
        source = HeliusDataSource(
            self.settings,
            opener=lambda *_args, **_kwargs: FakeResponse(
                {"id": 1, "result": {"solana-core": "missing-version"}}
            ),
        )
        with self.assertRaisesRegex(HeliusRpcError, "versão JSON-RPC"):
            source.get_version()

    def test_rpc_error_does_not_include_api_key_in_error_text(self) -> None:
        def fake_opener(request: Request, timeout: float) -> FakeResponse:
            return FakeResponse(
                {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "failed"}}
            )

        source = HeliusDataSource(self.settings, opener=fake_opener)
        with self.assertRaises(HeliusRpcError) as error:
            source.get_version()

        self.assertNotIn(self.settings.api_key, str(error.exception))
        self.assertNotIn(self.settings.api_key, repr(self.settings))

    def test_signatures_request_preserves_pagination_parameters(self) -> None:
        captured: list[dict[str, object]] = []

        def fake_opener(request: Request, timeout: float) -> FakeResponse:
            captured.append(json.loads(request.data))
            return FakeResponse({"jsonrpc": "2.0", "id": 1, "result": []})

        source = HeliusDataSource(self.settings, opener=fake_opener)
        result = source.get_signatures_for_address(
            "public-wallet", limit=250, before="older-signature", until="checkpoint-signature"
        )

        self.assertEqual(result, [])
        self.assertEqual(captured[0]["method"], "getSignaturesForAddress")
        self.assertEqual(
            captured[0]["params"][1],
            {
                "limit": 250,
                "commitment": "confirmed",
                "before": "older-signature",
                "until": "checkpoint-signature",
            },
        )

    def test_signatures_request_rejects_item_without_signature(self) -> None:
        source = HeliusDataSource(
            self.settings,
            opener=lambda *_args, **_kwargs: FakeResponse(
                {"jsonrpc": "2.0", "id": 1, "result": [{"err": None}]}
            ),
        )
        with self.assertRaisesRegex(HeliusRpcError, "sem assinatura válida"):
            source.get_signatures_for_address("public-wallet")

    def test_signatures_request_rejects_duplicate_signatures(self) -> None:
        source = HeliusDataSource(
            self.settings,
            opener=lambda *_args, **_kwargs: FakeResponse(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": [
                        {"signature": "duplicate-signature", "err": None},
                        {"signature": "duplicate-signature", "err": None},
                    ],
                }
            ),
        )
        with self.assertRaisesRegex(HeliusRpcError, "assinatura duplicada"):
            source.get_signatures_for_address("public-wallet")

    def test_signatures_request_rejects_invalid_limit(self) -> None:
        source = HeliusDataSource(self.settings, opener=lambda *_args, **_kwargs: None)
        with self.assertRaises(ValueError):
            source.get_signatures_for_address("public-wallet", limit=1001)


if __name__ == "__main__":
    unittest.main()