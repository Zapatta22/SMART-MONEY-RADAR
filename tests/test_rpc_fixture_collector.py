import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from smart_money_radar.data_sources.rpc_fixture_collector import RpcFixtureCollector

SIG = "1" * 64


class FakeResponse:
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.body


def rpc_bytes(signature=SIG):
    return json.dumps({"jsonrpc": "2.0", "id": 1, "result": {
        "slot": 123, "version": 0,
        "transaction": {"signatures": [signature], "message": {"instructions": []}},
        "meta": {"err": None},
    }}).encode()


class RpcFixtureCollectorTests(unittest.TestCase):
    def test_saves_exact_raw_bytes_and_sha256_manifest(self):
        raw = rpc_bytes()
        opener = Mock(return_value=FakeResponse(raw))
        with tempfile.TemporaryDirectory() as directory:
            collector = RpcFixtureCollector("https://rpc.example", directory, opener=opener)
            result = collector.collect(SIG)
            self.assertEqual(result.raw_path.read_bytes(), raw)
            self.assertEqual(result.sha256, hashlib.sha256(raw).hexdigest())
            manifest = json.loads((Path(directory) / f"{SIG}.manifest.json").read_text())
            self.assertFalse(manifest["anonymized"])
            self.assertEqual(manifest["slot"], 123)
            request = opener.call_args.args[0]
            self.assertIn(b'"method":"getTransaction"', request.data)

    def test_does_not_overwrite_existing_raw_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{SIG}.raw.json"
            path.write_text("original")
            collector = RpcFixtureCollector(
                "https://rpc.example", directory,
                opener=Mock(return_value=FakeResponse(rpc_bytes())),
            )
            with self.assertRaises(FileExistsError):
                collector.collect(SIG)
            self.assertEqual(path.read_text(), "original")

    def test_rejects_mismatched_signature(self):
        collector = RpcFixtureCollector(
            "https://rpc.example", tempfile.mkdtemp(),
            opener=Mock(return_value=FakeResponse(rpc_bytes("2" + "1" * 63))),
        )
        with self.assertRaisesRegex(RuntimeError, "não confere"):
            collector.collect(SIG)

    def test_rejects_non_null_rpc_error_even_when_empty_object(self):
        payload = {"jsonrpc": "2.0", "id": 1, "error": {}, "result": None}
        collector = RpcFixtureCollector(
            "https://rpc.example", tempfile.mkdtemp(),
            opener=Mock(return_value=FakeResponse(json.dumps(payload).encode())),
        )
        with self.assertRaisesRegex(RuntimeError, "Erro RPC"):
            collector.collect(SIG)

    def test_rejects_null_result(self):
        collector = RpcFixtureCollector(
            "https://rpc.example", tempfile.mkdtemp(),
            opener=Mock(return_value=FakeResponse(b'{"jsonrpc":"2.0","id":1,"result":null}')),
        )
        with self.assertRaisesRegex(RuntimeError, "não encontrada"):
            collector.collect(SIG)

    def test_rejects_invalid_timeout_values(self):
        cases = (
            ("boolean-true", True), ("boolean-false", False), ("zero", 0),
            ("negative", -1), ("nan", float("nan")), ("infinity", float("inf")),
            ("string", "20"), ("oversized-integer", 10**10000),
        )
        for label, timeout in cases:
            with self.subTest(case=label), self.assertRaises(ValueError):
                RpcFixtureCollector("https://rpc.example", "unused", timeout=timeout)

    def test_rejects_invalid_minimum_interval_values(self):
        cases = (
            ("boolean-true", True), ("boolean-false", False), ("negative", -1),
            ("nan", float("nan")), ("infinity", float("inf")),
            ("string", "0.25"), ("oversized-integer", 10**10000),
        )
        for label, interval in cases:
            with self.subTest(case=label), self.assertRaises(ValueError):
                RpcFixtureCollector(
                    "https://rpc.example", "unused", min_interval_seconds=interval
                )

    def test_requires_https(self):
        with self.assertRaises(ValueError):
            RpcFixtureCollector("http://insecure.example", "unused")

    def test_rejects_non_base58_or_wrong_length_signature_before_network(self):
        opener = Mock()
        collector = RpcFixtureCollector("https://rpc.example", tempfile.mkdtemp(), opener=opener)
        for invalid in ("../" + SIG, "0" * 64, "abc"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                collector.collect(invalid)
        opener.assert_not_called()

    def test_rejects_missing_or_wrong_jsonrpc_version(self):
        for version in (None, "1.0"):
            payload = {"id": 1, "result": {}}
            if version is not None:
                payload["jsonrpc"] = version
            collector = RpcFixtureCollector(
                "https://rpc.example", tempfile.mkdtemp(),
                opener=Mock(return_value=FakeResponse(json.dumps(payload).encode())),
            )
            with self.subTest(version=version), self.assertRaisesRegex(
                RuntimeError, "JSON-RPC 2.0"
            ):
                collector.collect(SIG)

    def test_rejects_mismatched_or_boolean_response_id(self):
        for response_id in (2, True):
            body = json.dumps({
                "jsonrpc": "2.0", "id": response_id,
                "result": {"slot": 123, "transaction": {"signatures": [SIG]}},
            }).encode()
            collector = RpcFixtureCollector(
                "https://rpc.example", tempfile.mkdtemp(),
                opener=Mock(return_value=FakeResponse(body)),
            )
            with self.subTest(response_id=response_id), self.assertRaisesRegex(
                RuntimeError, "ID de resposta divergente"
            ):
                collector.collect(SIG)

    def test_rejects_boolean_or_negative_slot(self):
        for slot in (True, -1, 2**64):
            payload = json.loads(rpc_bytes())
            payload["result"]["slot"] = slot
            collector = RpcFixtureCollector(
                "https://rpc.example", tempfile.mkdtemp(),
                opener=Mock(return_value=FakeResponse(json.dumps(payload).encode())),
            )
            with self.subTest(slot=slot), self.assertRaisesRegex(RuntimeError, "slot inteiro"):
                collector.collect(SIG)

    def test_rejects_invalid_transaction_version(self):
        for version in (None, True, -1, 1, {"unexpected": "object"}):
            payload = json.loads(rpc_bytes())
            payload["result"]["version"] = version
            collector = RpcFixtureCollector(
                "https://rpc.example", tempfile.mkdtemp(),
                opener=Mock(return_value=FakeResponse(json.dumps(payload).encode())),
            )
            with self.subTest(version=version), self.assertRaisesRegex(RuntimeError, "versão"):
                collector.collect(SIG)

    def test_requires_signature_list_with_requested_signature_first_and_unique(self):
        cases = (
            SIG,
            ["another-signature", SIG],
            [SIG, SIG],
            [SIG, 123],
        )
        for signatures in cases:
            payload = json.loads(rpc_bytes())
            payload["result"]["transaction"]["signatures"] = signatures
            collector = RpcFixtureCollector(
                "https://rpc.example", tempfile.mkdtemp(),
                opener=Mock(return_value=FakeResponse(json.dumps(payload).encode())),
            )
            with self.subTest(signatures=signatures), self.assertRaisesRegex(RuntimeError, "primeira posição"):
                collector.collect(SIG)

    def test_rejects_non_object_json_response(self):
        collector = RpcFixtureCollector(
            "https://rpc.example", tempfile.mkdtemp(),
            opener=Mock(return_value=FakeResponse(b'[]')),
        )
        with self.assertRaisesRegex(RuntimeError, "estrutura inválida"):
            collector.collect(SIG)

    def test_manifest_conflict_does_not_leave_raw_or_overwrite_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / f"{SIG}.manifest.json"
            manifest_path.write_text("original-manifest")
            collector = RpcFixtureCollector(
                "https://rpc.example", directory,
                opener=Mock(return_value=FakeResponse(rpc_bytes())),
            )
            with self.assertRaises(FileExistsError):
                collector.collect(SIG)
            self.assertEqual(manifest_path.read_text(), "original-manifest")
            self.assertFalse((Path(directory) / f"{SIG}.raw.json").exists())


if __name__ == "__main__":
    unittest.main()
