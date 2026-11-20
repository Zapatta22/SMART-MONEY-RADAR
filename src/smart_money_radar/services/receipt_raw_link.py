"""Read-only, fail-closed binding of archived swap receipts to stored transaction RAW.

The SQLite payload is normalized/re-serialized JSON and may be overwritten by
legacy ingestion. Its digest is local integrity only, NEVER external provider
authentication or finalized attestation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json

from smart_money_radar.storage.event_store import SQLiteEventStore


@dataclass(frozen=True)
class ReceiptRawLink:
    operation_id: str
    signature: str
    wallet: str
    pool: str
    source_id: str | None
    slot: int | None
    observed_at: datetime | None
    available_at: datetime
    local_payload_sha256: str | None
    status: str
    reasons: tuple[str, ...]
    provider_authenticated: bool = False
    finalized_attested: bool = False


def _clock(value: str | None, label: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} inválido")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} inválido") from exc
    if stamp.utcoffset() is None:
        # SQLite CURRENT_TIMESTAMP defaults to naive UTC, not an attested
        # provider timestamp. Interpret only for local ordering.
        if label != "sqlite_observed_at":
            raise ValueError(f"{label} sem fuso")
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def inspect_receipt_raw(
    store: SQLiteEventStore, *, wallet: str, row: dict, pool: str,
    source_id: str | None, as_of: datetime, expected_slot: int | None = None,
    expected_raw_sha256: str | None = None,
) -> ReceiptRawLink:
    """Check local joins; no claim that a caller hash proves network provenance."""
    if not isinstance(store, SQLiteEventStore) or not isinstance(row, dict):
        raise TypeError("recibo SQLite inválido")
    if any(not isinstance(x, str) or not x.strip() for x in (wallet, pool)):
        raise ValueError("wallet/pool obrigatórios")
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("cutoff sem fuso")
    if expected_slot is not None and (type(expected_slot) is not int or expected_slot < 0):
        raise ValueError("slot esperado inválido")
    operation_id, signature = row.get("operation_id"), row.get("signature")
    if not all(isinstance(v, str) and v.strip() for v in (operation_id, signature)):
        raise ValueError("operação e assinatura obrigatórias")
    available = _clock(row.get("available_at"), "available_at")
    if available is None:
        raise ValueError("disponibilidade ausente")
    if available > as_of.astimezone(timezone.utc):
        raise ValueError("RAW futuro não pode ser usado no replay")
    if store.integrity_check() != ["ok"]:
        raise RuntimeError("SQLite corrupto")
    reasons = []
    bundle = store.get_swap_bundle(operation_id)
    if bundle is None:
        reasons.append("swap_bundle_missing")
    else:
        obs = bundle["observation"]
        ev = bundle["evidence"]
        if obs.signature != signature or obs.wallet_address != wallet:
            reasons.append("swap_receipt_identity_conflict")
        if ev is None:
            reasons.append("swap_evidence_missing")
        else:
            if source_id is not None and ev.program_id != source_id:
                reasons.append("source_identity_conflict")
            if not any(x == f"pool_state:{pool}" for x in ev.evidence):
                reasons.append("pool_identity_unproven")
    meta = store.get_observation_metadata(wallet, signature)
    payload = store.get_raw_transaction(wallet, signature)
    local_hash = None
    slot = None
    observed = None
    if meta is None or payload is None:
        reasons.append("transaction_raw_missing")
    else:
        observed = _clock(meta.get("observed_at"), "sqlite_observed_at")
        slot = meta.get("slot")
        if slot is not None and (type(slot) is not int or slot < 0):
            reasons.append("invalid_stored_slot")
            slot = None
        pslot = payload.get("slot")
        if pslot is not None and (type(pslot) is not int or pslot < 0):
            reasons.append("invalid_payload_slot")
        if slot is not None and pslot is not None and slot != pslot:
            reasons.append("slot_mismatch")
        if expected_slot is not None and slot != expected_slot:
            reasons.append("expected_slot_mismatch")
        embedded = payload.get("transaction")
        signatures = embedded.get("signatures") if isinstance(embedded, dict) else None
        if not isinstance(signatures, list) or signature not in signatures:
            reasons.append("transaction_signature_unbound")
        if meta.get("parse_status") == "parse_error":
            reasons.append("parser_error")
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        local_hash = sha256(canonical).hexdigest()
        if expected_raw_sha256 is not None and local_hash != expected_raw_sha256:
            reasons.append("local_sha256_mismatch")
        if observed is not None and observed > as_of.astimezone(timezone.utc):
            reasons.append("raw_observed_after_cutoff")
        if observed is not None and available < observed:
            reasons.append("receipt_before_transaction_observed")
    if source_id is None:
        reasons.append("provider_identity_unknown")
    # Local storage does NOT establish finalized commitment, even if the
    # decoded RPC claims it. Preserve that as UNKNOWN.
    reasons.append("provider_authentication_unavailable")
    reasons.append("finalization_not_attested")
    blocking = tuple(sorted(set(reasons)))
    return ReceiptRawLink(
        operation_id=operation_id, signature=signature, wallet=wallet,
        pool=pool, source_id=source_id, slot=slot, observed_at=observed,
        available_at=available, local_payload_sha256=local_hash,
        status="UNKNOWN" if blocking else "LOCALLY_CONSISTENT",
        reasons=blocking,
    )
