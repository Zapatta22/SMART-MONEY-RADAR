"""Provider-neutral transaction observations from Yellowstone Geyser updates.

The adapter preserves transaction/meta protobuf payloads and a transport-order
coordinate supplied by the receiver. It does not assign sequence numbers,
decode economic meaning, classify BUY/SELL, or authorize execution.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

U64_MAX = (1 << 64) - 1
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def _u64(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= U64_MAX:
        raise ValueError(f"{field} deve ser u64")
    return value

def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve ser texto não vazio")
    return value

def _base58_encode(value: bytes, *, field: str, expected_length: int) -> str:
    if not isinstance(value, bytes) or len(value) != expected_length:
        raise ValueError(f"{field} deve conter exatamente {expected_length} bytes")
    zeroes = len(value) - len(value.lstrip(b"\x00"))
    number = int.from_bytes(value, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = _BASE58_ALPHABET[remainder] + encoded
    return "1" * zeroes + encoded

def _serialize(message: Any, field: str) -> bytes:
    serialize = getattr(message, "SerializeToString", None)
    if not callable(serialize):
        raise TypeError(f"{field} deve ser uma mensagem protobuf serializável")
    try:
        value = serialize(deterministic=True)
    except TypeError:
        value = serialize()
    if not isinstance(value, bytes):
        raise ValueError(f"{field} não produziu bytes protobuf")
    return value

def _has_field(message: Any, name: str) -> bool:
    has_field = getattr(message, "HasField", None)
    if callable(has_field):
        try:
            return bool(has_field(name))
        except (ValueError, TypeError):
            pass
    return getattr(message, name, None) is not None

@dataclass(frozen=True)
class NormalizedTransactionObservation:
    """Immutable transaction update tied to one source stream ordering domain.

    stream_sequence must be assigned to every SubscribeUpdate in arrival order,
    not by separate per-message-type counters. WIRE payloads are exact received
    protobuf frames. Reserialized protobuf bytes are explicitly not original RAW.
    """
    transaction_signature: str
    slot: int
    source_id: str
    stream_id: str
    ordering_domain_id: str
    stream_sequence: int
    transaction_index: int | None
    is_vote: bool
    transaction_payload: bytes
    meta_payload: bytes | None
    raw_payload: bytes
    raw_payload_provenance: str
    payload_sha256: str

    @property
    def ordering_key(self) -> tuple[str, str, int]:
        return (self.source_id, self.ordering_domain_id, self.stream_sequence)

    @property
    def evidence_complete(self) -> bool:
        return self.meta_payload is not None

def normalize_transaction_update(message: Any, *, source_id: str, stream_id: str,
                                 ordering_domain_id: str, stream_sequence: int,
                                 raw_message_bytes: bytes | None = None) -> NormalizedTransactionObservation:
    """Normalize SubscribeUpdateTransaction without inventing missing evidence."""
    info = getattr(message, "transaction", None)
    if info is None:
        raise ValueError("transaction ausente em SubscribeUpdateTransaction")
    transaction = getattr(info, "transaction", None)
    if transaction is None:
        raise ValueError("transaction ausente em SubscribeUpdateTransactionInfo")
    signature_bytes = getattr(info, "signature", None)
    signature = _base58_encode(signature_bytes, field="transaction.signature", expected_length=64)
    signatures = getattr(transaction, "signatures", None)
    if not signatures or not isinstance(signatures[0], bytes):
        raise ValueError("transaction.signatures[0] ausente ou inválida")
    nested_signature = _base58_encode(signatures[0], field="transaction.signatures[0]", expected_length=64)
    if nested_signature != signature:
        raise ValueError("signature diverge de transaction.signatures[0]")
    slot = _u64(getattr(message, "slot", None), "slot")
    source_id = _text(source_id, "source_id")
    stream_id = _text(stream_id, "stream_id")
    ordering_domain_id = _text(ordering_domain_id, "ordering_domain_id")
    stream_sequence = _u64(stream_sequence, "stream_sequence")
    raw_index = getattr(info, "index", None)
    transaction_index = None if raw_index is None else _u64(raw_index, "transaction.index")
    is_vote = getattr(info, "is_vote", False)
    if not isinstance(is_vote, bool):
        raise ValueError("transaction.is_vote deve ser booleano")
    transaction_payload = _serialize(transaction, "transaction")
    meta = getattr(info, "meta", None) if _has_field(info, "meta") else None
    meta_payload = None if meta is None else _serialize(meta, "transaction.meta")
    if raw_message_bytes is not None:
        if not isinstance(raw_message_bytes, bytes) or not raw_message_bytes:
            raise ValueError("raw_message_bytes deve conter bytes protobuf não vazios")
        raw_payload, provenance = raw_message_bytes, "WIRE"
    else:
        raw_payload = _serialize(message, "SubscribeUpdateTransaction")
        provenance = "PROTOBUF_DETERMINISTIC_RESERIALIZATION"
    return NormalizedTransactionObservation(
        transaction_signature=signature, slot=slot, source_id=source_id, stream_id=stream_id,
        ordering_domain_id=ordering_domain_id, stream_sequence=stream_sequence, transaction_index=transaction_index, is_vote=is_vote,
        transaction_payload=transaction_payload, meta_payload=meta_payload, raw_payload=raw_payload,
        raw_payload_provenance=provenance, payload_sha256=hashlib.sha256(raw_payload).hexdigest(),
    )
