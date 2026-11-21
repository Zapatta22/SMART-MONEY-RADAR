import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from smart_money_radar.cli import main
from smart_money_radar.services.rpc_evidence_attestation import verify_archived_rpc_attestation
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.storage.event_store import SQLiteEventStore


SIGNATURE = "1" * 64
OBSERVED = datetime(2026, 1, 1, tzinfo=timezone.utc)
RECEIVED = OBSERVED + timedelta(minutes=2)
# Public Ed25519 test key and private test seed from RFC 8032, section 7.1.
PUBLIC_KEY = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
PRIVATE_KEY_DER = bytes.fromhex(
    "302e020100300506032b657004220420"
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
)


class RpcAttestationTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        self.store = SQLiteEventStore(self.path / "smr.sqlite")
        self.addCleanup(self.store.close)
        self.raw = json.dumps({
            "jsonrpc": "2.0", "result": {
                "slot": 42, "meta": {"err": None},
                "transaction": {"signatures": [SIGNATURE]},
            },
        }).encode()
        self.identifier = RpcObservationJournal(self.store).append(
            radar="launch", signature=SIGNATURE, source_id="provider",
            endpoint_host="rpc.example", raw_payload=self.raw, observed_at=OBSERVED,
            available_at=OBSERVED, expected_slot=42,
        )
        self.scope = dict(radar="launch", network="solana-mainnet",
                          source_id="provider", endpoint_host="rpc.example")
        self.claim = {
            **self.scope, "evidence_id": self.identifier, "signature": SIGNATURE, "slot": 42,
            "raw_sha256": sha256(self.raw).hexdigest(), "observed_at": OBSERVED.isoformat(),
            "issued_at": (OBSERVED + timedelta(minutes=1)).isoformat(),
            "commitment_requested": "finalized",
        }
        self.trust = {"keys": {"test-key": {
            **self.scope, "public_key_hex": PUBLIC_KEY,
            "valid_from": OBSERVED.isoformat(), "valid_until": RECEIVED.isoformat(),
        }}}
        self.envelope = {
            "key_id": "test-key", "claim": self.claim,
            "signature": base64.b64encode(bytes(64)).decode(),
        }

    def sign(self):
        message = b"SMR:solana-rpc-observation:ed25519:v1\x00" + json.dumps(
            {"key_id": "test-key", "claim": self.claim}, sort_keys=True, separators=(",", ":"),
        ).encode("ascii")
        (self.path / "key.der").write_bytes(PRIVATE_KEY_DER)
        (self.path / "msg").write_bytes(message)
        process = subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-inkey", "key.der", "-keyform", "DER",
             "-rawin", "-in", "msg"],
            cwd=self.path, capture_output=True, check=True, timeout=5,
        )
        self.envelope["signature"] = base64.b64encode(process.stdout).decode()

    def verify(self, **overrides):
        args = dict(evidence_id=self.identifier, radar="launch", network="solana-mainnet",
                    envelope_raw=json.dumps(self.envelope).encode(),
                    trust_raw=json.dumps(self.trust).encode(),
                    attestation_available_at=RECEIVED, cutoff=RECEIVED)
        return verify_archived_rpc_attestation(self.store, **(args | overrides))

    @unittest.skipUnless(shutil.which("openssl"), "requires OpenSSL Ed25519 verification")
    def test_real_signature_verifies_from_read_only_cli_and_rejects_tampering(self):
        self.sign()
        result = self.verify()
        self.assertEqual(result["status"], "SIGNED_RPC_OBSERVATION_VERIFIED")
        self.assertTrue(result["signer_authenticated"])
        self.assertFalse(result["independently_finalized"])
        self.assertFalse(result["operational_authorized"])

        envelope_path, trust_path = self.path / "envelope.json", self.path / "trust.json"
        envelope_path.write_text(json.dumps(self.envelope))
        trust_path.write_text(json.dumps(self.trust))
        with redirect_stdout(io.StringIO()) as output:
            main(["verify-rpc-attestation", str(self.path / "smr.sqlite"), self.identifier,
                  str(envelope_path), "--trust", str(trust_path), "--network", "solana-mainnet",
                  "--radar", "launch"])
        self.assertTrue(json.loads(output.getvalue())["signer_authenticated"])

        self.claim["issued_at"] = (OBSERVED + timedelta(seconds=30)).isoformat()
        self.assertEqual(self.verify()["reason"], "attestation_signature_invalid")
        self.claim["slot"] = 43
        self.assertEqual(self.verify()["reason"], "attestation_archive_conflict")

    @unittest.skipUnless(shutil.which("openssl"), "requires OpenSSL Ed25519 verification")
    def test_confirmed_smart_money_observation_authenticates_only_signer(self):
        self.identifier = RpcObservationJournal(self.store).append(
            radar="smart_money", signature=SIGNATURE, source_id="provider",
            endpoint_host="rpc.example", raw_payload=self.raw, observed_at=OBSERVED,
            available_at=OBSERVED, expected_slot=42, commitment_requested="confirmed",
        )
        self.claim.update(evidence_id=self.identifier, radar="smart_money",
                          commitment_requested="confirmed")
        self.trust["keys"]["test-key"]["radar"] = "smart_money"
        self.sign()
        result = self.verify(radar="smart_money")
        self.assertTrue(result["signer_authenticated"])
        self.assertFalse(result["independently_finalized"])
        self.claim["commitment_requested"] = "finalized"
        self.assertEqual(self.verify(radar="smart_money")["reason"], "attestation_archive_conflict")

    def test_rejects_future_receipt_cross_radar_and_expired_key(self):
        self.assertEqual(self.verify(cutoff=OBSERVED)["reason"], "attestation_unavailable_at_cutoff")
        self.assertEqual(self.verify(radar="smart_money")["reason"], "attestation_scope_conflict")
        self.trust["keys"]["test-key"]["valid_until"] = self.claim["issued_at"]
        self.assertEqual(self.verify()["reason"], "attestation_key_outside_validity")

    def test_verifier_unavailable_stays_unknown_and_duplicate_json_fails_closed(self):
        with patch("smart_money_radar.services.rpc_evidence_attestation.subprocess.run",
                   side_effect=FileNotFoundError):
            result = self.verify()
        self.assertEqual(result["reason"], "ed25519_verifier_unavailable")
        self.assertFalse(result["signer_authenticated"])
        result = self.verify(trust_raw=b'{"keys": {}, "keys": {}}')
        self.assertEqual(result["reason"], "invalid_attestation_input")
