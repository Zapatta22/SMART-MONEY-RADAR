"""CM30 - read-only bridge for actual archived Launch and Smart Money producers.

The source remains the existing SQLite journal; fixtures, historical data and
simulated test frames are NEVER represented as live captures. Input bytes and
their recorded availability are checked; an archived hash does not attest a
third-party provider or full history coverage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Literal

from smart_money_radar.data_sources.raydium_cpmm_launch import (
    detect_cpmm_pool_initializations,
)
from smart_money_radar.services.radar_integration_status import (
    RadarObservation, compose_radar_snapshot,
)
from smart_money_radar.storage.event_store import SQLiteEventStore

OriginKind = Literal["ARCHIVED_RPC", "ARCHIVED_DERIVED", "FIXTURE_OFFLINE", "SIMULATED_TEST"]


@dataclass(frozen=True)
class IntegratedRadarEvent:
    id: str
    radar: Literal["launch", "smart_money"]
    event_type: str
    origin: OriginKind
    source_id: str
    provider: str | None
    signature: str | None
    slot: int | None
    pool: str
    observed_at: str | None
    available_at: str | None
    raw_sha256: str | None
    raw_identity: str | None
    coverage: str
    evidence_quality: str
    verdict: str
    direction: str | None
    reasons: tuple[str, ...]
    source_reference: str
    operational_authorized: bool = False


def _date(value: str | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if result.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return result


def _event(
    *, radar: Literal["launch", "smart_money"], source_id: str,
    event_id: str, event_type: str, origin: OriginKind,
    signature: str | None, slot: int | None, pool: str,
    available_at: datetime | None, observed_at: datetime | None,
    raw: bytes | None, expected_hash: str | None,
    source_reference: str, direction: str | None = None,
    extra_reasons: tuple[str, ...] = (),
) -> IntegratedRadarEvent:
    snapshot = compose_radar_snapshot(RadarObservation(
        radar=radar, source_id=source_id, pool=pool, signature=signature,
        slot=slot, available_at=available_at,
        raw_payload=raw, raw_sha256=expected_hash,
        coverage="UNKNOWN", source_authenticated=False,
    ))
    reasons = set(snapshot.reasons) | set(extra_reasons)
    if observed_at is None:
        reasons.add("observation_time_unknown")
    elif available_at is not None and observed_at > available_at:
        reasons.add("observation_after_publication")
    if origin != "ARCHIVED_RPC":
        reasons.add("derived_or_offline_origin")
    if raw is None:
        reasons.add("raw_not_persisted")
    if raw is not None and expected_hash is not None and sha256(raw).hexdigest() != expected_hash:
        reasons.add("raw_sha256_conflict")
    quality = "CONFLICTED" if (
        snapshot.evidence_status == "CONFLICTED" or
        "raw_sha256_conflict" in reasons or
        "observation_after_publication" in reasons or
        "source_identity_conflict" in reasons or
        "slot_regression" in reasons
    ) else "UNKNOWN" if snapshot.evidence_status == "UNKNOWN" else "LOCALLY_CONSISTENT"
    return IntegratedRadarEvent(
        id=event_id, radar=radar, event_type=event_type, origin=origin,
        source_id=source_id, provider=None,
        signature=signature, slot=slot, pool=pool,
        observed_at=observed_at.isoformat() if observed_at is not None else None,
        available_at=available_at.isoformat() if available_at is not None else None,
        raw_sha256=expected_hash,
        raw_identity=expected_hash if raw is not None else None,
        coverage="UNKNOWN", evidence_quality=quality,
        verdict="UNKNOWN", direction=direction,
        reasons=tuple(sorted(reasons)),
        source_reference=source_reference,
    )


def launch_events_from_archive(
    rows: list[dict[str, Any]], *,
    origin: OriginKind = "ARCHIVED_RPC",
    source_id: str = "launch-sqlite-archive",
) -> tuple[IntegratedRadarEvent, ...]:
    """Validate archive records against the unchanged original Launch decoder."""
    if origin not in ("ARCHIVED_RPC", "FIXTURE_OFFLINE", "SIMULATED_TEST"):
        raise ValueError("launch origin not supported")
    events: dict[str, IntegratedRadarEvent] = {}
    conflicts: set[str] = set()
    last_by_source: dict[str, int] = {}
    for row in rows:
        raw = row.get("raw_bytes")
        digest = row.get("raw_sha256")
        raw = bytes(raw) if isinstance(raw, (bytes, bytearray, memoryview)) else None
        try:
            identity = json.loads(row["identity_json"])
            decoded = json.loads(raw) if raw is not None else None
            candidates = (detect_cpmm_pool_initializations(decoded)
                          if isinstance(decoded, dict) else ())
        except (ValueError, TypeError, KeyError, UnicodeDecodeError):
            identity, candidates = None, ()
        if not isinstance(identity, dict) or not isinstance(row.get("pool"), str):
            continue
        pool = row["pool"]
        source_ref = f"cpmm_launch_evidence:{pool}:{digest or 'UNKNOWN'}"
        matching = [x for x in candidates if x.pool == pool
                    and asdict(x) == identity]
        match = matching[0] if len(matching) == 1 else None
        sig = identity.get("signature") if match is not None else None
        slot = identity.get("slot") if match is not None else None
        captured = _date(row.get("archived_at"))
        reasons: list[str] = []
        if match is None:
            reasons.append("source_identity_conflict")
        # Archived_at is a local ingest time, never a source timestamp.
        if source_ref in events:
            if events[source_ref].raw_sha256 != digest:
                conflicts.add(source_ref)
            continue
        item = _event(
            radar="launch", source_id=source_id,
            event_id=f"launch:{pool}:{sig or 'UNKNOWN'}:{identity.get('instruction_index', 'UNKNOWN')}",
            event_type="CPMM_POOL_INITIALIZED",
            origin=origin, signature=sig, slot=slot, pool=pool,
            available_at=captured, observed_at=None,
            raw=raw, expected_hash=digest,
            source_reference=source_ref, extra_reasons=tuple(reasons),
        )
        if slot is not None:
            previous = last_by_source.get(source_id)
            if previous is not None and slot < previous:
                item = _event(
                    radar="launch", source_id=source_id, event_id=item.id,
                    event_type=item.event_type, origin=origin,
                    signature=sig, slot=slot, pool=pool,
                    available_at=captured, observed_at=None, raw=raw,
                    expected_hash=digest, source_reference=source_ref,
                    extra_reasons=tuple(reasons) + ("slot_regression",),
                )
            last_by_source[source_id] = slot
        events[source_ref] = item
    for key in conflicts:
        original = events[key]
        events[key] = IntegratedRadarEvent(**{
            **asdict(original),
            "evidence_quality": "CONFLICTED",
            "reasons": tuple(sorted(set(original.reasons) | {"duplicate_identity_conflict"})),
        })
    return tuple(events.values())


def smart_money_events_from_archive(
    rows: list[dict[str, Any]], *,
    origin: OriginKind = "ARCHIVED_DERIVED",
    source_id: str = "smart-money-sqlite-archive",
) -> tuple[IntegratedRadarEvent, ...]:
    """Project stored swap receipts; no wallet ownership or BUY/SELL authority."""
    if origin not in ("ARCHIVED_DERIVED", "FIXTURE_OFFLINE", "SIMULATED_TEST"):
        raise ValueError("Smart Money origin not supported")
    events: dict[str, IntegratedRadarEvent] = {}
    for row in rows:
        op = row.get("operation_id")
        pool = row.get("pool")
        if not isinstance(op, str) or not op or not isinstance(pool, str) or not pool:
            continue
        raw = row.get("raw_bytes")
        if not isinstance(raw, (bytes, bytearray)):
            raw = None
        sig = row.get("signature")
        if not isinstance(sig, str) or not sig:
            sig = None
        slot = row.get("slot")
        if type(slot) is not int or slot < 0:
            slot = None
        reasons: list[str] = []
        if row.get("chain") not in (None, "solana"):
            reasons.append("source_identity_conflict")
        if raw is not None:
            try:
                obj = json.loads(raw)
                payload = obj.get("result", obj) if isinstance(obj, dict) else None
                if not isinstance(payload, dict):
                    raise ValueError("RAW transaction must be a JSON object")
                chain_slot = payload.get("slot")
                transaction = payload.get("transaction")
                chain_signatures = (
                    transaction.get("signatures") if isinstance(transaction, dict) else None
                )
                chain_sig = chain_signatures[0] if isinstance(chain_signatures, list) and chain_signatures else None
                if chain_sig is not None and chain_sig != sig:
                    reasons.append("source_identity_conflict")
                    sig = None
                if type(chain_slot) is int and slot is not None and chain_slot != slot:
                    reasons.append("source_identity_conflict")
                    slot = None
            except (ValueError, TypeError, KeyError, IndexError):
                reasons.append("raw_unparseable")
        side = row.get("side")
        if side not in ("BUY", "SELL"):
            side = None
            reasons.append("direction_unverified")
        digest = sha256(raw).hexdigest() if raw is not None else None
        captured = _date(row.get("observed_at"))
        published = _date(row.get("available_at"))
        item = _event(
            radar="smart_money", source_id=source_id,
            event_id=f"smart_money:{op}", event_type="SWAP_CLASSIFIED",
            origin=origin, signature=sig, slot=slot, pool=pool,
            available_at=published, observed_at=captured, raw=raw,
            expected_hash=digest, source_reference=f"swap_replay_archive:{op}",
            direction=side, extra_reasons=tuple(reasons),
        )
        existing = events.get(item.id)
        if existing is not None and existing != item:
            item = IntegratedRadarEvent(**{
                **asdict(existing),
                "evidence_quality": "CONFLICTED",
                "reasons": tuple(sorted(set(existing.reasons) | {"duplicate_identity_conflict"})),
            })
        events[item.id] = item
    return tuple(events.values())


def read_archived_radar_events(
    store: SQLiteEventStore, *, limit: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    """Read existing SQLite producers without modifying schemas or opening RPC."""
    launch = launch_events_from_archive(
        store.list_cpmm_launch_archived_event_inputs(limit=limit),
    )
    smart = smart_money_events_from_archive(
        store.list_smr_archived_event_inputs(limit=limit),
    )
    return {
        "launch": [asdict(x) for x in launch],
        "smart_money": [asdict(x) for x in smart],
    }
