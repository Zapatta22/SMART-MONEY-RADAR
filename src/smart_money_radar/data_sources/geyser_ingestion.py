"""Offline coordinator from normalized Geyser events into immutable RAW storage.

Receives already-decoded provider-neutral events. Its normalized JSON payload
is deterministic and excludes transport fields; transport identity is stored
separately as a delivery.
"""
from __future__ import annotations

import base64
import json
from typing import Literal

from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate
from smart_money_radar.data_sources.geyser_bank_lineage import (
    NormalizedBlockMeta,
    NormalizedEntryUpdateParent,
    NormalizedSlotUpdate,
)
from smart_money_radar.data_sources.geyser_event_identity import derive_event_identity
from smart_money_radar.storage.geyser_raw_store import (
    RawDeliveryInput,
    RawEventInput,
    RawIngestResult,
    SQLiteGeyserRawStore,
)

NormalizedGeyserEvent = (
    NormalizedAccountUpdate
    | NormalizedSlotUpdate
    | NormalizedBlockMeta
    | NormalizedEntryUpdateParent
)


def _normalized_payload(event: NormalizedGeyserEvent) -> tuple[str, dict]:
    if isinstance(event, NormalizedAccountUpdate):
        return "account", {
            "pubkey": event.pubkey,
            "slot": event.slot,
            "write_version": event.write_version,
            "txn_signature": event.txn_signature,
            "lamports": event.lamports,
            "owner": event.owner,
            "executable": event.executable,
            "rent_epoch": event.rent_epoch,
            "data_base64": base64.b64encode(event.data).decode("ascii"),
            "bank_id": event.bank_id,
            "is_startup": event.is_startup,
        }
    if isinstance(event, NormalizedSlotUpdate):
        return "slot", {
            "slot": event.slot,
            "parent_slot": event.parent_slot,
            "status": event.status,
            "bank_id": event.bank_id,
            "dead_error": event.dead_error,
        }
    if isinstance(event, NormalizedBlockMeta):
        return "block_meta", {
            "slot": event.slot,
            "bank_id": event.bank_id,
            "blockhash": event.blockhash,
            "parent_slot": event.parent_slot,
            "parent_blockhash": event.parent_blockhash,
        }
    if isinstance(event, NormalizedEntryUpdateParent):
        return "entry_update_parent", {
            "slot": event.slot,
            "cleared_bank_id": event.cleared_bank_id,
            "parent_slot": event.parent_slot,
            "parent_block_id_hex": event.parent_block_id.hex(),
        }
    raise TypeError("tipo de evento Geyser normalizado não suportado")


def ingest_normalized_event(
    store: SQLiteGeyserRawStore,
    event: NormalizedGeyserEvent,
    *,
    schema_version: str,
    delivery_kind: Literal["live", "replay", "backfill", "unknown"] = "unknown",
    received_at: str | None = None,
) -> RawIngestResult:
    """Derive stable identity, serialize normalized content, and persist delivery.

    Transport stream_id and stream_sequence are written only to delivery.
    This function does not claim protobuf wire capture: payload_encoding is
    always normalized_json because its input is already decoded/normalized.
    """
    identity = derive_event_identity(event, schema_version=schema_version)
    event_kind, payload = _normalized_payload(event)
    source_id = event.source if isinstance(event, NormalizedAccountUpdate) else event.source_id
    canonical = json.dumps(
        {
            "identity_version": identity.identity_version,
            "schema_version": identity.schema_version,
            "event_kind": event_kind,
            "source_id": source_id,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    raw_event = RawEventInput(
        event_id=identity.event_id,
        source_id=source_id,
        event_kind=event_kind,
        schema_version=schema_version,
        payload_encoding="normalized_json",
        payload_bytes=canonical,
    )
    delivery = RawDeliveryInput(
        stream_id=event.stream_id,
        stream_sequence=event.stream_sequence,
        delivery_kind=delivery_kind,
        received_at=received_at,
    )
    return store.ingest(raw_event, delivery)
