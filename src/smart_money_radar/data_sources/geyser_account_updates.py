"""Provider-neutral contracts and strict normalization for Solana account updates.

This module deliberately does not import Yellowstone protobufs or connect to a
provider. A provider adapter must translate its message into the canonical
mapping accepted below and assign a monotonically increasing stream sequence.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any


U64_MAX = (1 << 64) - 1


def _u64(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= U64_MAX:
        raise ValueError(f"{field} deve ser u64")
    return value


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve ser texto não vazio")
    return value


@dataclass(frozen=True)
class NormalizedAccountUpdate:
    """Immutable account write with its source ordering and transaction evidence.

    `stream_sequence` is assigned by the consuming adapter, not read from
    Yellowstone. It is monotonic within `stream_id` and allows the timeline to
    detect transport gaps without confusing provider write_version with
    delivery order.
    """

    pubkey: str
    slot: int
    write_version: int
    txn_signature: str | None
    lamports: int
    owner: str
    executable: bool
    rent_epoch: int
    data: bytes
    stream_id: str
    stream_sequence: int
    source: str
    bank_id: int | None = None
    is_startup: bool = False

    @property
    def ordering_key(self) -> tuple[int, int, int]:
        """Deterministic order: ledger slot, account write, then stream delivery."""
        return (self.slot, self.write_version, self.stream_sequence)

    @property
    def state_hash(self) -> str:
        """SHA-256 of account state, excluding transport and transaction metadata."""
        metadata = json.dumps(
            {
                "pubkey": self.pubkey,
                "lamports": self.lamports,
                "owner": self.owner,
                "executable": self.executable,
                "rent_epoch": self.rent_epoch,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256()
        digest.update(len(metadata).to_bytes(8, "big"))
        digest.update(metadata)
        digest.update(len(self.data).to_bytes(8, "big"))
        digest.update(self.data)
        return digest.hexdigest()

    @property
    def event_fingerprint(self) -> str:
        """Fingerprint including transaction identity and ledger ordering."""
        payload = {
            "pubkey": self.pubkey,
            "slot": self.slot,
            "write_version": self.write_version,
            "txn_signature": self.txn_signature,
            "bank_id": self.bank_id,
            "is_startup": self.is_startup,
            "state_hash": self.state_hash,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def normalize_account_update(
    payload: Mapping[str, Any],
    *,
    stream_id: str,
    stream_sequence: int,
    source: str = "yellowstone",
) -> NormalizedAccountUpdate:
    """Validate a canonical account-update envelope and preserve raw account bytes.

    Canonical envelope:
      {
        "slot": int, "bank_id": int | None, "is_startup": bool,
        "account": {
          "pubkey": str, "lamports": int, "owner": str,
          "executable": bool, "rent_epoch": int, "data": bytes,
          "write_version": int, "txn_signature": str | None
        }
      }

    No base64 coercion, current-RPC lookup, epoch inference, or commitment
    promotion is performed here. Missing txn_signature is preserved as None;
    callers must not use such an update as transaction-specific post-state.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("payload deve ser um mapeamento")
    account = payload.get("account")
    if not isinstance(account, Mapping):
        raise ValueError("account ausente ou inválida")

    pubkey = _required_text(account.get("pubkey"), "account.pubkey")
    owner = _required_text(account.get("owner"), "account.owner")
    slot = _u64(payload.get("slot"), "slot")
    raw_bank_id = payload.get("bank_id")
    bank_id = None if raw_bank_id is None else _u64(raw_bank_id, "bank_id")
    is_startup = payload.get("is_startup", False)
    if not isinstance(is_startup, bool):
        raise ValueError("is_startup deve ser booleano")
    if is_startup and bank_id is not None:
        raise ValueError("is_startup não pode carregar bank_id")
    write_version = _u64(account.get("write_version"), "account.write_version")
    lamports = _u64(account.get("lamports"), "account.lamports")
    rent_epoch = _u64(account.get("rent_epoch"), "account.rent_epoch")

    executable = account.get("executable")
    if not isinstance(executable, bool):
        raise ValueError("account.executable deve ser booleano")

    data = account.get("data")
    if not isinstance(data, bytes):
        raise ValueError("account.data deve conter bytes; conversão de encoding pertence ao adapter")

    txn_signature = account.get("txn_signature")
    if txn_signature is not None:
        txn_signature = _required_text(txn_signature, "account.txn_signature")

    stream_id = _required_text(stream_id, "stream_id")
    source = _required_text(source, "source")
    stream_sequence = _u64(stream_sequence, "stream_sequence")

    return NormalizedAccountUpdate(
        pubkey=pubkey,
        slot=slot,
        write_version=write_version,
        txn_signature=txn_signature,
        lamports=lamports,
        owner=owner,
        executable=executable,
        rent_epoch=rent_epoch,
        data=data,
        stream_id=stream_id,
        stream_sequence=stream_sequence,
        source=source,
        bank_id=bank_id,
        is_startup=is_startup,
    )
