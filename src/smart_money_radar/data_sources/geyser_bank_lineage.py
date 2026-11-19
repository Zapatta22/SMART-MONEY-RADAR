"""Provider-neutral Yellowstone bank identity and fork-lineage contracts.

This module models bank identity separately from slot number and transport
sequence. It preserves opaque parent_block_id bytes and never equates them to
blockhash. No network access, persistence, or automatic canonicality inference.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Literal

from smart_money_radar.data_sources.geyser_account_updates import (
    NormalizedAccountUpdate,
    _u64,
    _required_text,
)

SLOT_STATUSES = {
    "SLOT_PROCESSED", "SLOT_CONFIRMED", "SLOT_FINALIZED",
    "SLOT_FIRST_SHRED_RECEIVED", "SLOT_COMPLETED",
    "SLOT_CREATED_BANK", "SLOT_DEAD",
}


def _optional_u64(value, field_name):
    return None if value is None else _u64(value, field_name)


def _event_fingerprint(kind: str, values: dict) -> str:
    encoded = json.dumps(
        {"kind": kind, **values}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class NormalizedSlotUpdate:
    source_id: str
    stream_id: str
    stream_sequence: int
    slot: int
    parent_slot: int | None
    status: str
    bank_id: int | None
    dead_error: str | None

    @property
    def fingerprint(self) -> str:
        return _event_fingerprint("slot", {
            "source_id": self.source_id, "slot": self.slot,
            "parent_slot": self.parent_slot, "status": self.status,
            "bank_id": self.bank_id, "dead_error": self.dead_error,
        })


@dataclass(frozen=True)
class NormalizedBlockMeta:
    source_id: str
    stream_id: str
    stream_sequence: int
    slot: int
    bank_id: int
    blockhash: str
    parent_slot: int
    parent_blockhash: str

    @property
    def fingerprint(self) -> str:
        return _event_fingerprint("block_meta", {
            "source_id": self.source_id, "slot": self.slot,
            "bank_id": self.bank_id, "blockhash": self.blockhash,
            "parent_slot": self.parent_slot,
            "parent_blockhash": self.parent_blockhash,
        })


@dataclass(frozen=True)
class NormalizedEntryUpdateParent:
    source_id: str
    stream_id: str
    stream_sequence: int
    slot: int
    cleared_bank_id: int
    parent_slot: int
    parent_block_id: bytes

    @property
    def fingerprint(self) -> str:
        return _event_fingerprint("entry_update_parent", {
            "source_id": self.source_id, "slot": self.slot,
            "cleared_bank_id": self.cleared_bank_id,
            "parent_slot": self.parent_slot,
            "parent_block_id_hex": self.parent_block_id.hex(),
        })


def _stream_fields(payload: Mapping, source_id: str, stream_id: str, sequence: int):
    if not isinstance(payload, Mapping):
        raise TypeError("payload deve ser um mapeamento")
    return (
        _required_text(source_id, "source_id"),
        _required_text(stream_id, "stream_id"),
        _u64(sequence, "stream_sequence"),
    )


def normalize_slot_update(
    payload: Mapping, *, source_id: str, stream_id: str, stream_sequence: int
) -> NormalizedSlotUpdate:
    source_id, stream_id, sequence = _stream_fields(
        payload, source_id, stream_id, stream_sequence
    )
    slot = _u64(payload.get("slot"), "slot")
    parent_slot = _optional_u64(payload.get("parent"), "parent")
    bank_id = _optional_u64(payload.get("bank_id"), "bank_id")
    status = payload.get("status")
    if not isinstance(status, str) or status not in SLOT_STATUSES:
        raise ValueError("status de slot desconhecido")
    if status == "SLOT_CREATED_BANK" and bank_id is None:
        raise ValueError("SLOT_CREATED_BANK exige bank_id")
    dead_error = payload.get("dead_error")
    if dead_error is not None and not isinstance(dead_error, str):
        raise ValueError("dead_error deve ser texto ou None")
    return NormalizedSlotUpdate(
        source_id, stream_id, sequence, slot, parent_slot, status, bank_id, dead_error
    )


def normalize_block_meta(
    payload: Mapping, *, source_id: str, stream_id: str, stream_sequence: int
) -> NormalizedBlockMeta:
    source_id, stream_id, sequence = _stream_fields(
        payload, source_id, stream_id, stream_sequence
    )
    return NormalizedBlockMeta(
        source_id=source_id, stream_id=stream_id, stream_sequence=sequence,
        slot=_u64(payload.get("slot"), "slot"),
        bank_id=_u64(payload.get("bank_id"), "bank_id"),
        blockhash=_required_text(payload.get("blockhash"), "blockhash"),
        parent_slot=_u64(payload.get("parent_slot"), "parent_slot"),
        parent_blockhash=_required_text(payload.get("parent_blockhash"), "parent_blockhash"),
    )


def normalize_entry_update_parent(
    payload: Mapping, *, source_id: str, stream_id: str, stream_sequence: int
) -> NormalizedEntryUpdateParent:
    source_id, stream_id, sequence = _stream_fields(
        payload, source_id, stream_id, stream_sequence
    )
    parent_block_id = payload.get("parent_block_id")
    if not isinstance(parent_block_id, bytes):
        raise ValueError("parent_block_id deve conter bytes")
    return NormalizedEntryUpdateParent(
        source_id=source_id, stream_id=stream_id, stream_sequence=sequence,
        slot=_u64(payload.get("slot"), "slot"),
        cleared_bank_id=_u64(payload.get("cleared_bank_id"), "cleared_bank_id"),
        parent_slot=_u64(payload.get("parent_slot"), "parent_slot"),
        parent_block_id=parent_block_id,
    )


@dataclass(frozen=True)
class BankKey:
    source_id: str
    slot: int
    bank_id: int


@dataclass
class BankNode:
    key: BankKey
    parent_slot: int | None = None
    blockhash: str | None = None
    parent_blockhash: str | None = None
    parent_key: BankKey | None = None
    statuses: set[str] = field(default_factory=set)
    dead: bool = False
    invalidated: bool = False
    cleared_by_parent_update: bool = False
    parent_block_id: bytes | None = None
    replaces_bank: BankKey | None = None

    @property
    def finalized(self) -> bool:
        return "SLOT_FINALIZED" in self.statuses

    @property
    def usable_for_observation(self) -> bool:
        return not self.dead and not self.invalidated


@dataclass(frozen=True)
class BankLineageConflict:
    key: BankKey | None
    reason: str
    detail: str


@dataclass(frozen=True)
class BankUpdateResult:
    status: Literal["inserted", "duplicate", "conflict"]
    key: BankKey | None = None
    conflict: BankLineageConflict | None = None


class BankLineageTracker:
    """Tracks provider-scoped bank identities and only explicit parent links.

    source_id must remain stable across reconnects to the same provider/node.
    stream_id is a transport connection and is not part of bank identity.
    Slot-only parent signals are retained but do not select a fork. Exact
    parent links are created only from matching (parent_slot, parent_blockhash)
    block metadata. EntryUpdateParent's opaque parent_block_id is never treated
    as a blockhash.
    """

    def __init__(self) -> None:
        self._banks: dict[BankKey, BankNode] = {}
        self._fingerprints: set[str] = set()
        self._dead_slots: set[tuple[str, int]] = set()
        self._pending_replacements: dict[tuple[str, int], list[BankKey]] = {}
        self._conflicts: list[BankLineageConflict] = []

    @property
    def conflicts(self) -> tuple[BankLineageConflict, ...]:
        return tuple(self._conflicts)

    @property
    def banks(self) -> tuple[BankNode, ...]:
        return tuple(self._banks.values())

    def _node(self, key: BankKey) -> BankNode:
        node = self._banks.get(key)
        if node is None:
            node = BankNode(key=key, dead=(key.source_id, key.slot) in self._dead_slots)
            self._banks[key] = node
        return node

    def _conflict(self, key, reason, detail):
        conflict = BankLineageConflict(key, reason, detail)
        self._conflicts.append(conflict)
        return BankUpdateResult("conflict", key, conflict)

    def add_slot_update(self, event: NormalizedSlotUpdate) -> BankUpdateResult:
        if event.fingerprint in self._fingerprints:
            return BankUpdateResult("duplicate")
        key = None if event.bank_id is None else BankKey(
            event.source_id, event.slot, event.bank_id
        )
        if event.status == "SLOT_DEAD":
            if key is None:
                self._dead_slots.add((event.source_id, event.slot))
            targets = (
                [self._node(key)] if key is not None
                else [n for k, n in self._banks.items()
                      if k.source_id == event.source_id and k.slot == event.slot]
            )
            for node in targets:
                node.dead = True
            self._fingerprints.add(event.fingerprint)
            return BankUpdateResult("inserted", key)

        if key is None:
            self._fingerprints.add(event.fingerprint)
            return BankUpdateResult("inserted")

        pending_key = (event.source_id, event.slot)
        pending = self._pending_replacements.get(pending_key, [])
        if event.status == "SLOT_CREATED_BANK" and len(pending) > 1:
            return self._conflict(
                key, "ambiguous_replacement",
                "mais de um bank_id foi invalidado antes do SLOT_CREATED_BANK",
            )

        existing_node = self._banks.get(key)
        if (
            existing_node is not None
            and event.parent_slot is not None
            and existing_node.parent_slot is not None
            and existing_node.parent_slot != event.parent_slot
        ):
            return self._conflict(key, "parent_slot_changed", "bank recebeu parent_slot incompatível")

        node = self._node(key)
        if event.parent_slot is not None:
            node.parent_slot = event.parent_slot
        node.statuses.add(event.status)

        if event.status == "SLOT_CREATED_BANK" and len(pending) == 1:
            old_key = pending.pop(0)
            node.replaces_bank = old_key
            self._node(old_key).invalidated = True
            if not pending:
                self._pending_replacements.pop(pending_key, None)
        self._fingerprints.add(event.fingerprint)
        return BankUpdateResult("inserted", key)

    def add_entry_update_parent(
        self, event: NormalizedEntryUpdateParent
    ) -> BankUpdateResult:
        if event.fingerprint in self._fingerprints:
            return BankUpdateResult("duplicate")
        key = BankKey(event.source_id, event.slot, event.cleared_bank_id)
        existing_node = self._banks.get(key)
        if existing_node is not None and existing_node.parent_slot is not None and existing_node.parent_slot != event.parent_slot:
            return self._conflict(key, "parent_slot_changed", "EntryUpdateParent trouxe parent_slot incompatível")
        node = self._node(key)
        node.invalidated = True
        node.cleared_by_parent_update = True
        node.parent_slot = event.parent_slot
        node.parent_block_id = event.parent_block_id
        self._pending_replacements.setdefault((event.source_id, event.slot), []).append(key)
        self._fingerprints.add(event.fingerprint)
        return BankUpdateResult("inserted", key)

    def add_block_meta(self, event: NormalizedBlockMeta) -> BankUpdateResult:
        if event.fingerprint in self._fingerprints:
            return BankUpdateResult("duplicate")
        key = BankKey(event.source_id, event.slot, event.bank_id)
        existing_node = self._banks.get(key)
        if existing_node is not None and existing_node.blockhash is not None and existing_node.blockhash != event.blockhash:
            return self._conflict(key, "blockhash_changed", "mesmo bank_id recebeu blockhash diferente")
        if existing_node is not None and existing_node.parent_slot is not None and existing_node.parent_slot != event.parent_slot:
            return self._conflict(key, "parent_slot_changed", "slot update e block metadata discordam")
        if existing_node is not None and existing_node.parent_blockhash is not None and (
            existing_node.parent_blockhash != event.parent_blockhash
            or existing_node.parent_slot != event.parent_slot
        ):
            return self._conflict(key, "parent_block_identity_changed", "metadados de pai incompatíveis")
        node = self._node(key)
        node.blockhash = event.blockhash
        node.parent_slot = event.parent_slot
        node.parent_blockhash = event.parent_blockhash
        self._fingerprints.add(event.fingerprint)
        self._rebuild_parent_links(event.source_id)
        return BankUpdateResult("inserted", key)

    def _rebuild_parent_links(self, source_id: str) -> None:
        for node in self._banks.values():
            if node.key.source_id != source_id or node.parent_blockhash is None:
                continue
            matches = [
                candidate.key for candidate in self._banks.values()
                if candidate.key.source_id == source_id
                and candidate.key.slot == node.parent_slot
                and candidate.blockhash == node.parent_blockhash
            ]
            node.parent_key = matches[0] if len(matches) == 1 else None

    def account_bank_status(self, update: NormalizedAccountUpdate) -> str:
        if update.is_startup:
            return "startup_unassigned"
        if update.bank_id is None:
            return "bank_id_missing"
        key = BankKey(update.source, update.slot, update.bank_id)
        node = self._banks.get(key)
        if node is None:
            return "bank_not_observed"
        if node.dead:
            return "bank_dead"
        if node.invalidated:
            return "bank_invalidated"
        return "bank_observed_finalized" if node.finalized else "bank_observed_unfinalized"

    def is_bank_usable(self, key: BankKey) -> bool | None:
        """Return whether a known bank and every known ancestor are not invalidated.

        An unresolved parent does not make two writes in the exact same bank
        incomparable, but any known dead/cleared ancestor makes that bank unusable.
        """
        current = self._banks.get(key)
        if current is None:
            return None
        visited: set[BankKey] = set()
        while current is not None:
            if not current.usable_for_observation:
                return False
            if current.key in visited:
                return False
            visited.add(current.key)
            if current.parent_key is None:
                return True
            current = self._banks.get(current.parent_key)
        return None

    def is_ancestor(self, ancestor: BankKey, descendant: BankKey) -> bool | None:
        """True only for a verified parent chain; None for incomplete/invalid lineage."""
        if ancestor.source_id != descendant.source_id:
            return None
        if ancestor == descendant:
            return self.is_bank_usable(ancestor)
        current = self._banks.get(descendant)
        if current is None:
            return None
        visited: set[BankKey] = set()
        while current is not None:
            if not current.usable_for_observation or current.key in visited:
                return None
            visited.add(current.key)
            parent_key = current.parent_key
            if parent_key is None:
                if (
                    current.key.slot == 0
                    and current.parent_slot is None
                    and current.parent_blockhash is None
                ):
                    return False
                return None
            parent = self._banks.get(parent_key)
            if parent is None:
                return None
            if not parent.usable_for_observation:
                return None
            if parent_key == ancestor:
                return True
            current = parent
        return None
