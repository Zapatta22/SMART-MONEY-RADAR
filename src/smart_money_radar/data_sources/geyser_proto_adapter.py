"""Boundary adapter for pinned Yellowstone Geyser protobuf messages.

Accepts decoded protobuf objects from an official Yellowstone client. No gRPC
client, network access, persistence, or provider SDK is created here. Binary
Solana keys/signatures are converted to Base58 at this boundary; account data
and opaque parent IDs remain bytes.
"""
from __future__ import annotations

from typing import Any

from smart_money_radar.data_sources.geyser_transaction_updates import (
    NormalizedTransactionObservation,
    bind_transaction_wire,
    normalize_transaction_update,
)
from smart_money_radar.data_sources.geyser_account_updates import (
    NormalizedAccountUpdate,
    normalize_account_update,
)
from smart_money_radar.data_sources.geyser_bank_lineage import (
    NormalizedBlockMeta,
    NormalizedEntryUpdateParent,
    NormalizedSlotUpdate,
    normalize_block_meta,
    normalize_entry_update_parent,
    normalize_slot_update,
)

_SLOT_STATUS_BY_NUMBER = {
    0: "SLOT_PROCESSED",
    1: "SLOT_CONFIRMED",
    2: "SLOT_FINALIZED",
    3: "SLOT_FIRST_SHRED_RECEIVED",
    4: "SLOT_COMPLETED",
    5: "SLOT_CREATED_BANK",
    6: "SLOT_DEAD",
}
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58_encode(value: bytes, *, field: str, expected_length: int | None = None) -> str:
    if not isinstance(value, bytes):
        raise ValueError(f"{field} deve conter bytes")
    if expected_length is not None and len(value) != expected_length:
        raise ValueError(f"{field} deve conter exatamente {expected_length} bytes")
    leading_zeroes = len(value) - len(value.lstrip(b"\x00"))
    number = int.from_bytes(value, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = _BASE58_ALPHABET[remainder] + encoded
    return "1" * leading_zeroes + encoded


def _has_field(message: Any, name: str) -> bool:
    """Read protobuf presence for optional fields without mistaking defaults for presence."""
    has_field = getattr(message, "HasField", None)
    if callable(has_field):
        try:
            return bool(has_field(name))
        except (ValueError, TypeError):
            pass
    return getattr(message, name, None) is not None


def _required_message(message: Any, name: str) -> Any:
    if message is None or not hasattr(message, name):
        raise ValueError(f"mensagem Yellowstone sem campo {name}")
    value = getattr(message, name)
    if value is None:
        raise ValueError(f"mensagem Yellowstone com campo {name} ausente")
    return value


def adapt_account_update(
    message: Any, *, source_id: str, stream_id: str, stream_sequence: int
) -> NormalizedAccountUpdate:
    """Convert SubscribeUpdateAccount into the provider-neutral account contract."""
    account = _required_message(message, "account")
    envelope = {
        "slot": getattr(message, "slot", None),
        "is_startup": getattr(message, "is_startup", False),
        "account": {
            "pubkey": _base58_encode(
                getattr(account, "pubkey", None), field="account.pubkey", expected_length=32
            ),
            "lamports": getattr(account, "lamports", None),
            "owner": _base58_encode(
                getattr(account, "owner", None), field="account.owner", expected_length=32
            ),
            "executable": getattr(account, "executable", None),
            "rent_epoch": getattr(account, "rent_epoch", None),
            "data": getattr(account, "data", None),
            "write_version": getattr(account, "write_version", None),
            "txn_signature": (
                _base58_encode(
                    getattr(account, "txn_signature", None),
                    field="account.txn_signature",
                    expected_length=64,
                )
                if _has_field(account, "txn_signature")
                else None
            ),
        },
    }
    if _has_field(message, "bank_id"):
        envelope["bank_id"] = getattr(message, "bank_id")
    return normalize_account_update(
        envelope, stream_id=stream_id, stream_sequence=stream_sequence, source=source_id
    )


def adapt_slot_update(
    message: Any, *, source_id: str, stream_id: str, stream_sequence: int
) -> NormalizedSlotUpdate:
    """Convert SubscribeUpdateSlot, preserving absent optional parent/bank fields."""
    raw_status = getattr(message, "status", None)
    status = raw_status if isinstance(raw_status, str) else _SLOT_STATUS_BY_NUMBER.get(raw_status)
    if status is None:
        raise ValueError(f"SlotStatus Yellowstone desconhecido: {raw_status!r}")
    payload = {
        "slot": getattr(message, "slot", None),
        "status": status,
        "parent": getattr(message, "parent") if _has_field(message, "parent") else None,
        "dead_error": getattr(message, "dead_error") if _has_field(message, "dead_error") else None,
        "bank_id": getattr(message, "bank_id") if _has_field(message, "bank_id") else None,
    }
    return normalize_slot_update(
        payload, source_id=source_id, stream_id=stream_id, stream_sequence=stream_sequence
    )


def adapt_block_meta(
    message: Any, *, source_id: str, stream_id: str, stream_sequence: int
) -> NormalizedBlockMeta:
    """Convert SubscribeUpdateBlockMeta without deriving missing parent identity."""
    payload = {
        "slot": getattr(message, "slot", None),
        "bank_id": getattr(message, "bank_id", None),
        "blockhash": getattr(message, "blockhash", None),
        "parent_slot": getattr(message, "parent_slot", None),
        "parent_blockhash": getattr(message, "parent_blockhash", None),
    }
    return normalize_block_meta(
        payload, source_id=source_id, stream_id=stream_id, stream_sequence=stream_sequence
    )


def adapt_entry_update_parent(
    message: Any, *, source_id: str, stream_id: str, stream_sequence: int
) -> NormalizedEntryUpdateParent:
    """Convert EntryUpdateParent; parent_block_id remains opaque bytes."""
    payload = {
        "slot": getattr(message, "slot", None),
        "cleared_bank_id": getattr(message, "cleared_bank_id", None),
        "parent_slot": getattr(message, "parent_slot", None),
        "parent_block_id": getattr(message, "parent_block_id", None),
    }
    return normalize_entry_update_parent(
        payload, source_id=source_id, stream_id=stream_id, stream_sequence=stream_sequence
    )


def adapt_transaction_update(
    message: Any, *, source_id: str, stream_id: str, ordering_domain_id: str,
    stream_sequence: int, raw_message_bytes: bytes | None = None,
) -> NormalizedTransactionObservation:
    """Convert SubscribeUpdateTransaction and preserve transport provenance."""
    return normalize_transaction_update(
        message, source_id=source_id, stream_id=stream_id,
        ordering_domain_id=ordering_domain_id, stream_sequence=stream_sequence,
        raw_message_bytes=raw_message_bytes,
    )


def adapt_subscribe_update(
    message: Any, *, source_id: str, stream_id: str, stream_sequence: int,
    raw_message_bytes: bytes | None = None, ordering_domain_id: str | None = None
) -> (
    NormalizedAccountUpdate
    | NormalizedSlotUpdate
    | NormalizedBlockMeta
    | NormalizedEntryUpdateParent
    | NormalizedTransactionObservation
    | None
):
    """Dispatch supported SubscribeUpdate oneof members.

    Ping/pong, blocks, and ordinary entries are ignored here;
    their contracts belong to separate adapters.
    """
    which_oneof = getattr(message, "WhichOneof", None)
    if not callable(which_oneof):
        raise TypeError("mensagem deve ser SubscribeUpdate protobuf com WhichOneof")
    kind = which_oneof("update_oneof")
    if kind == "transaction":
        if ordering_domain_id is None:
            raise ValueError("ordering_domain_id deve ser fornecido para transações")
        observation = adapt_transaction_update(
            message.transaction, source_id=source_id, stream_id=stream_id,
            stream_sequence=stream_sequence, ordering_domain_id=ordering_domain_id,
        )
        if raw_message_bytes is not None:
            return bind_transaction_wire(observation, message, raw_message_bytes)
        return observation
    adapters = {
        "account": adapt_account_update,
        "slot": adapt_slot_update,
        "block_meta": adapt_block_meta,
        "entry_update_parent": adapt_entry_update_parent,
    }
    adapter = adapters.get(kind)
    if adapter is None:
        return None
    return adapter(
        getattr(message, kind),
        source_id=source_id,
        stream_id=stream_id,
        stream_sequence=stream_sequence,
    )
