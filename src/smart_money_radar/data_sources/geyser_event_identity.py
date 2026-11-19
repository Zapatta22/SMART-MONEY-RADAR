"""Versioned deterministic identities for normalized Yellowstone events.

These identities describe the logical ledger event, not a transport delivery
or a byte-for-byte protobuf wire representation. Stream IDs and stream
sequences are intentionally excluded. RAW payload integrity remains enforced
separately by SQLiteGeyserRawStore.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate
from smart_money_radar.data_sources.geyser_bank_lineage import (
    NormalizedBlockMeta,
    NormalizedEntryUpdateParent,
    NormalizedSlotUpdate,
)

IDENTITY_VERSION = "geyser-event-id:v1"
_SUPPORTED_EVENTS = (
    NormalizedAccountUpdate,
    NormalizedSlotUpdate,
    NormalizedBlockMeta,
    NormalizedEntryUpdateParent,
)


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve ser texto não vazio")
    return value


@dataclass(frozen=True)
class EventIdentity:
    """Deterministic logical identity plus the versioned identity contract."""

    event_id: str
    identity_version: str
    schema_version: str
    event_kind: str
    identity_fields: tuple[tuple[str, str | int | bool], ...]


def _identity_parts(event):
    if isinstance(event, NormalizedAccountUpdate):
        return "account", {
            "source_id": event.source,
            "slot": event.slot,
            "write_version": event.write_version,
            "pubkey": event.pubkey,
            "bank_id": event.bank_id,
            "is_startup": event.is_startup,
        }
    if isinstance(event, NormalizedSlotUpdate):
        return "slot", {
            "source_id": event.source_id,
            "slot": event.slot,
            "status": event.status,
            "bank_id": event.bank_id,
        }
    if isinstance(event, NormalizedBlockMeta):
        return "block_meta", {
            "source_id": event.source_id,
            "slot": event.slot,
            "bank_id": event.bank_id,
        }
    if isinstance(event, NormalizedEntryUpdateParent):
        return "entry_update_parent", {
            "source_id": event.source_id,
            "slot": event.slot,
            "cleared_bank_id": event.cleared_bank_id,
        }
    raise TypeError("tipo de evento Geyser normalizado não suportado")


def derive_event_identity(event, *, schema_version: str) -> EventIdentity:
    """Derive an ID from stable ledger identity fields and explicit versions.

    Content fields such as account bytes, parent hash, status metadata, and
    dead_error are deliberately not all part of the key: if those change while
    the logical identity remains the same, RAW storage must detect a conflict
    instead of silently creating a second event. Callers persist the payload
    and its SHA-256 separately.

    For account updates the key is source + slot + write_version + pubkey,
    with bank/startup context included to avoid merging distinct bank-scoped
    observations. Slot events use source + slot + status + bank. Block metadata
    uses source + slot + bank. EntryUpdateParent uses source + slot + cleared
    bank. Transport stream_id/stream_sequence never participate.
    """
    schema_version = _required_text(schema_version, "schema_version")
    if not isinstance(event, _SUPPORTED_EVENTS):
        raise TypeError("tipo de evento Geyser normalizado não suportado")
    event_kind, fields = _identity_parts(event)
    canonical = json.dumps(
        {
            "identity_version": IDENTITY_VERSION,
            "schema_version": schema_version,
            "event_kind": event_kind,
            "identity": fields,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    ordered_fields = tuple(sorted(fields.items()))
    return EventIdentity(
        event_id=f"ge1_{digest}",
        identity_version=IDENTITY_VERSION,
        schema_version=schema_version,
        event_kind=event_kind,
        identity_fields=ordered_fields,
    )
