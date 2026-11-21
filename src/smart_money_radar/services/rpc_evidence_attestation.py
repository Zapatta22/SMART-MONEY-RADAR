"""Audit external Ed25519 signatures over exact archived RPC observations."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from smart_money_radar.services.rpc_observation_journal import (
    RADARS, RpcObservationJournal, _canonical, _strict_json,
)

_DOMAIN = b"SMR:solana-rpc-observation:ed25519:v1\x00"
_ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")
_HEX_32 = re.compile(r"[0-9a-f]{64}")
ATTESTATION_MAX_BYTES = 16_384
_SCOPE_FIELDS = ("network", "radar", "source_id", "endpoint_host")
_CLAIM_FIELDS = frozenset((*_SCOPE_FIELDS, "evidence_id", "signature", "slot",
                           "raw_sha256", "observed_at", "issued_at", "commitment_requested"))
_UNATTESTED_REASONS = {
    "provider_independent_attestation_missing",
    "finalization_independent_attestation_missing",
    "finalized_not_requested",
}


def _utc(stamp):
    if not isinstance(stamp, datetime) or stamp.utcoffset() is None:
        raise ValueError("timezone required for attestation timestamps")
    return stamp.astimezone(timezone.utc)


def _parse_time(text):
    if not isinstance(text, str):
        raise ValueError("invalid attestation timestamp")
    return _utc(datetime.fromisoformat(text))


def _verify_ed25519(key, message, signature):
    """Use the installed OpenSSL verifier, without network or signing keys."""
    try:
        with TemporaryDirectory(prefix="smr-attestation-") as directory:
            path = Path(directory)
            (path / "key").write_bytes(_ED25519_SPKI_PREFIX + key)
            (path / "message").write_bytes(message)
            (path / "signature").write_bytes(signature)
            result = subprocess.run(
                ["openssl", "pkeyutl", "-verify", "-pubin", "-keyform", "DER",
                 "-inkey", "key", "-rawin", "-in", "message", "-sigfile", "signature"],
                cwd=path, stdin=subprocess.DEVNULL, capture_output=True, timeout=5, check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode == 0:
        return True
    if result.returncode == 1 and result.stdout.strip() == b"Signature Verification Failure":
        return False
    return None


def verify_archived_rpc_attestation(
    store, *, evidence_id, radar, network, envelope_raw, trust_raw,
    attestation_available_at, cutoff,
):
    """Return a scope-bound signer receipt. Trust pins must come from local policy.

    Receiving time is supplied by the verifier. A timestamp claimed by the signer
    cannot establish that the signature was available to an earlier decision.
    """
    if radar not in RADARS or not isinstance(network, str) or not network.strip():
        raise ValueError("explicit radar and network required")
    if not isinstance(evidence_id, str) or not _HEX_32.fullmatch(evidence_id):
        raise ValueError("invalid RPC evidence ID")
    point, received = _utc(cutoff), _utc(attestation_available_at)
    result = {
        "evidence_id": evidence_id, "radar": radar, "network": network,
        "status": "UNKNOWN", "cutoff": point.isoformat(),
        "attestation_available_at": received.isoformat(),
        "signer_authenticated": False, "independently_finalized": False,
        "operational_authorized": False,
    }
    if received > point or point > datetime.now(timezone.utc):
        return {**result, "reason": "attestation_unavailable_at_cutoff"}
    if any(not isinstance(raw, bytes) or not 0 < len(raw) <= ATTESTATION_MAX_BYTES
           for raw in (envelope_raw, trust_raw)):
        return {**result, "reason": "invalid_attestation_input"}
    try:
        envelope, trust = _strict_json(envelope_raw), _strict_json(trust_raw)
        if not isinstance(envelope, dict) or set(envelope) != {"key_id", "claim", "signature"}:
            raise ValueError("invalid attestation envelope")
        if not isinstance(trust, dict) or set(trust) != {"keys"} or not isinstance(trust["keys"], dict):
            raise ValueError("invalid attestation trust policy")
        claim, key_id = envelope["claim"], envelope["key_id"]
        if not isinstance(claim, dict) or set(claim) != _CLAIM_FIELDS:
            raise ValueError("invalid attestation claim")
        if not isinstance(key_id, str) or not key_id or len(key_id) > 128:
            raise ValueError("invalid attestation key ID")
        signature = base64.b64decode(envelope["signature"], validate=True)
        if len(signature) != 64 or base64.b64encode(signature).decode("ascii") != envelope["signature"]:
            raise ValueError("invalid attestation signature encoding")
        issued, observed = _parse_time(claim["issued_at"]), _parse_time(claim["observed_at"])
        if type(claim["slot"]) is not int or claim["slot"] < 0 or not observed <= issued <= received:
            raise ValueError("invalid observation or attestation order")
        if any(not isinstance(claim[name], str) or not claim[name].strip()
               for name in _CLAIM_FIELDS - {"slot"}):
            raise ValueError("invalid attestation claim field")
        pin = trust["keys"].get(key_id)
        if pin is None:
            return {**result, "reason": "attestation_key_not_pinned"}
        if not isinstance(pin, dict) or set(pin) != {
            *_SCOPE_FIELDS, "public_key_hex", "valid_from", "valid_until",
        }:
            raise ValueError("invalid trust pin")
        if not isinstance(pin["public_key_hex"], str) or not _HEX_32.fullmatch(pin["public_key_hex"]):
            raise ValueError("invalid pinned public key")
        valid_from, valid_until = _parse_time(pin["valid_from"]), _parse_time(pin["valid_until"])
        if valid_from >= valid_until:
            raise ValueError("invalid key validity window")
        if not valid_from <= issued < valid_until:
            return {**result, "reason": "attestation_key_outside_validity"}
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return {**result, "reason": "invalid_attestation_input"}

    if (claim["evidence_id"] != evidence_id or claim["radar"] != radar
            or claim["network"] != network
            or any(claim[field] != pin[field] for field in _SCOPE_FIELDS)):
        return {**result, "status": "CONFLICTED", "reason": "attestation_scope_conflict"}

    with store._connection_scope() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cm38_rpc_observations'"
        ).fetchone()
        row = conn.execute(
            "SELECT radar,signature,available_at,metadata,metadata_sha,raw "
            "FROM cm38_rpc_observations WHERE evidence_id=?", (evidence_id,),
        ).fetchone() if exists else None
    if row is None:
        return {**result, "reason": "rpc_evidence_not_archived"}
    try:
        item = RpcObservationJournal._read(evidence_id, row[3:])
        metadata, evidence = item["metadata"], item["evidence"]
        if (row[:3] != (metadata["radar"], metadata["signature"], metadata["available_at"])
                or evidence.status == "CONFLICTED"
                or set(evidence.reasons) - _UNATTESTED_REASONS
                or observed != evidence.observed_at
                or any(claim[k] != metadata[k] for k in (
                    "radar", "signature", "slot", "source_id", "endpoint_host", "raw_sha256",
                    "commitment_requested",
                ))):
            raise ValueError("archived scope mismatch")
        if evidence.available_at > point:
            return {**result, "reason": "rpc_evidence_unavailable_at_cutoff"}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        return {**result, "status": "CONFLICTED", "reason": "attestation_archive_conflict"}

    message = _DOMAIN + _canonical({"key_id": key_id, "claim": claim}).encode("ascii")
    verified = _verify_ed25519(bytes.fromhex(pin["public_key_hex"]), message, signature)
    if verified is None:
        return {**result, "reason": "ed25519_verifier_unavailable"}
    if not verified:
        return {**result, "status": "CONFLICTED", "reason": "attestation_signature_invalid"}
    return {
        **result, "status": "SIGNED_RPC_OBSERVATION_VERIFIED", "signer_authenticated": True,
        "key_id": key_id, "source_id": evidence.source_id, "signature": evidence.signature,
        "slot": evidence.slot, "raw_sha256": evidence.raw_sha256,
        "attestation_sha256": sha256(envelope_raw).hexdigest(),
    }
