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

    def test_rejects_null_result(self):
        collector = RpcFixtureCollector(
            "https://rpc.example", tempfile.mkdtemp(),
            opener=Mock(return_value=FakeResponse(b'{"result":null}')),
        )
        with self.assertRaisesRegex(RuntimeError, "não encontrada"):
            collector.collect(SIG)

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
