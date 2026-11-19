"""In-memory, provider-neutral account update timeline for Solana Geyser data.

The timeline separates ledger ordering (slot/write_version) from transport
ordering (stream_id/stream_sequence). It does not assign commitment, blockhash,
or fork identity: a provider adapter must supply authoritative rollback signals.
No persistence or network access is performed here.
"""
from dataclasses import dataclass
from typing import Literal

from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate


@dataclass(frozen=True)
class AccountTimelineGap:
    stream_id: str
    expected_sequence: int | None
    received_sequence: int | None
    reason: str
    continuity_epoch: int


@dataclass(frozen=True)
class AccountTimelineConflict:
    pubkey: str
    slot: int
    write_version: int
    existing_fingerprint: str
    incoming_fingerprint: str
    reason: str


@dataclass(frozen=True)
class AccountStateTransition:
    """A transaction-linked post-state and its immediately preceding observed state."""

    pubkey: str
    txn_signature: str
    slot: int
    write_version: int
    pre_state: NormalizedAccountUpdate
    post_state: NormalizedAccountUpdate


@dataclass(frozen=True)
class TimelineInsertResult:
    status: Literal["inserted", "duplicate", "conflict"]
    gap: AccountTimelineGap | None = None
    conflict: AccountTimelineConflict | None = None


@dataclass(frozen=True)
class _TimelineEntry:
    update: NormalizedAccountUpdate
    continuity_epoch: int
    baseline: bool = False


class AccountUpdateTimeline:
    """Tracks observed account states without treating delivery order as ledger order.

    One logical stream is expected at a time. Changing stream_id is treated as a
    reconnect boundary. A sequence gap invalidates the predecessor relationship
    for the first subsequent update of every known account; that update becomes
    a new baseline, and later contiguous writes can be paired again.

    The first observed write for an account is always a baseline: its earlier
    state is unknown. A baseline is never emitted as a transaction transition.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[_TimelineEntry]] = {}
        self._orphaned: list[NormalizedAccountUpdate] = []
        self._fingerprints: set[str] = set()
        self._write_identity: dict[tuple[str, str, int, int | None, int, bool], str] = {}
        self._stream_last: dict[str, int] = {}
        self._stream_sequences: dict[tuple[str, int], str] = {}
        self._active_stream_id: str | None = None
        self._continuity_epoch = 0
        self._needs_baseline: set[str] = set()
        self._gaps: list[AccountTimelineGap] = []
        self._conflicts: list[AccountTimelineConflict] = []

    @property
    def gaps(self) -> tuple[AccountTimelineGap, ...]:
        return tuple(self._gaps)

    @property
    def conflicts(self) -> tuple[AccountTimelineConflict, ...]:
        return tuple(self._conflicts)

    @property
    def orphaned_updates(self) -> tuple[NormalizedAccountUpdate, ...]:
        return tuple(self._orphaned)

    def _mark_gap(
        self,
        *,
        stream_id: str,
        expected_sequence: int | None,
        received_sequence: int | None,
        reason: str,
    ) -> AccountTimelineGap:
        self._continuity_epoch += 1
        self._needs_baseline.update(self._events)
        gap = AccountTimelineGap(
            stream_id=stream_id,
            expected_sequence=expected_sequence,
            received_sequence=received_sequence,
            reason=reason,
            continuity_epoch=self._continuity_epoch,
        )
        self._gaps.append(gap)
        return gap

    def add(self, update: NormalizedAccountUpdate) -> TimelineInsertResult:
        """Insert an update idempotently, detecting stream gaps and write conflicts."""
        if not isinstance(update, NormalizedAccountUpdate):
            raise TypeError("update deve ser NormalizedAccountUpdate")

        gap = None
        if self._active_stream_id is None:
            self._active_stream_id = update.stream_id
        elif update.stream_id != self._active_stream_id:
            gap = self._mark_gap(
                stream_id=update.stream_id,
                expected_sequence=None,
                received_sequence=update.stream_sequence,
                reason="stream_changed_or_reconnected",
            )
            self._active_stream_id = update.stream_id
            self._stream_last.setdefault(update.stream_id, update.stream_sequence - 1)

        sequence_key = (update.stream_id, update.stream_sequence)
        prior_sequence_fingerprint = self._stream_sequences.get(sequence_key)
        if prior_sequence_fingerprint is not None:
            if prior_sequence_fingerprint == update.event_fingerprint:
                return TimelineInsertResult("duplicate", gap=gap)
            conflict = AccountTimelineConflict(
                pubkey=update.pubkey,
                slot=update.slot,
                write_version=update.write_version,
                existing_fingerprint=prior_sequence_fingerprint,
                incoming_fingerprint=update.event_fingerprint,
                reason="stream_sequence_reused_for_different_event",
            )
            self._conflicts.append(conflict)
            return TimelineInsertResult("conflict", gap=gap, conflict=conflict)

        last_sequence = self._stream_last.get(update.stream_id)
        if last_sequence is not None:
            if update.stream_sequence > last_sequence + 1:
                gap = self._mark_gap(
                    stream_id=update.stream_id,
                    expected_sequence=last_sequence + 1,
                    received_sequence=update.stream_sequence,
                    reason="stream_sequence_gap",
                )
            elif update.stream_sequence <= last_sequence:
                conflict = AccountTimelineConflict(
                    pubkey=update.pubkey,
                    slot=update.slot,
                    write_version=update.write_version,
                    existing_fingerprint="",
                    incoming_fingerprint=update.event_fingerprint,
                    reason="unrecognized_out_of_order_stream_sequence",
                )
                self._conflicts.append(conflict)
                return TimelineInsertResult("conflict", gap=gap, conflict=conflict)

        self._stream_sequences[sequence_key] = update.event_fingerprint
        self._stream_last[update.stream_id] = max(
            update.stream_sequence, self._stream_last.get(update.stream_id, update.stream_sequence)
        )

        identity = (update.source, update.pubkey, update.slot, update.bank_id, update.write_version, update.is_startup)
        existing_identity = self._write_identity.get(identity)
        if existing_identity is not None:
            if existing_identity == update.event_fingerprint:
                return TimelineInsertResult("duplicate", gap=gap)
            conflict = AccountTimelineConflict(
                pubkey=update.pubkey,
                slot=update.slot,
                write_version=update.write_version,
                existing_fingerprint=existing_identity,
                incoming_fingerprint=update.event_fingerprint,
                reason="ledger_write_identity_collision",
            )
            self._conflicts.append(conflict)
            return TimelineInsertResult("conflict", gap=gap, conflict=conflict)

        if update.event_fingerprint in self._fingerprints:
            return TimelineInsertResult("duplicate", gap=gap)

        baseline = update.pubkey not in self._events or update.pubkey in self._needs_baseline
        if baseline:
            self._needs_baseline.discard(update.pubkey)
        entry = _TimelineEntry(update, self._continuity_epoch, baseline)
        entries = self._events.setdefault(update.pubkey, [])
        entries.append(entry)
        entries.sort(key=lambda item: item.update.ordering_key)
        self._write_identity[identity] = update.event_fingerprint
        self._fingerprints.add(update.event_fingerprint)
        return TimelineInsertResult("inserted", gap=gap)

    def events_for(self, pubkey: str) -> tuple[NormalizedAccountUpdate, ...]:
        """Return active writes for one account in ledger order."""
        return tuple(entry.update for entry in self._events.get(pubkey, ()))

    def current_state(self, pubkey: str) -> NormalizedAccountUpdate | None:
        """Return the latest observed active state, not necessarily finalized."""
        entries = self._events.get(pubkey, ())
        if not entries:
            return None
        # Without a BankLineageTracker this linear view cannot choose a fork.
        if any(entry.update.bank_id is not None for entry in entries):
            return None
        return entries[-1].update

    def transition_for(
        self, txn_signature: str, *, pubkey: str | None = None
    ) -> tuple[AccountStateTransition, ...]:
        """Return only transitions with an observed predecessor in the same epoch.

        Missing txn_signature, first-seen baselines, and writes immediately after
        a gap/reconnect/rollback are deliberately not promoted to pre/post pairs.
        """
        if not isinstance(txn_signature, str) or not txn_signature.strip():
            raise ValueError("txn_signature deve ser texto não vazio")
        transitions: list[AccountStateTransition] = []
        accounts = (pubkey,) if pubkey is not None else tuple(self._events)
        for account in accounts:
            entries = self._events.get(account, ())
            for index, entry in enumerate(entries):
                update = entry.update
                if update.txn_signature != txn_signature or entry.baseline or index == 0:
                    continue
                previous = entries[index - 1]
                # Fork-scoped updates require a verified bank-parent chain. This
                # linear timeline has no tracker dependency, so fail closed.
                if update.is_startup or previous.update.is_startup:
                    continue
                if update.bank_id is not None or previous.update.bank_id is not None:
                    continue
                if previous.continuity_epoch != entry.continuity_epoch:
                    continue
                transitions.append(
                    AccountStateTransition(
                        pubkey=account,
                        txn_signature=txn_signature,
                        slot=update.slot,
                        write_version=update.write_version,
                        pre_state=previous.update,
                        post_state=update,
                    )
                )
        return tuple(transitions)

    def rollback_from_slot(self, first_orphaned_slot: int) -> tuple[NormalizedAccountUpdate, ...]:
        """Mark all active updates at/after a provider-confirmed fork boundary orphaned.

        This is an explicit input from a provider/fork tracker, not fork detection.
        Removed writes remain available through orphaned_updates for audit.
        """
        if isinstance(first_orphaned_slot, bool) or not isinstance(first_orphaned_slot, int) or first_orphaned_slot < 0:
            raise ValueError("first_orphaned_slot deve ser inteiro não negativo")
        removed: list[NormalizedAccountUpdate] = []
        for pubkey, entries in tuple(self._events.items()):
            kept = []
            for entry in entries:
                if entry.update.slot >= first_orphaned_slot:
                    removed.append(entry.update)
                    self._orphaned.append(entry.update)
                    self._fingerprints.discard(entry.update.event_fingerprint)
                    self._write_identity.pop(
                        (entry.update.source, entry.update.pubkey, entry.update.slot, entry.update.bank_id, entry.update.write_version, entry.update.is_startup), None
                    )
                else:
                    kept.append(entry)
            if kept:
                self._events[pubkey] = kept
            else:
                self._events.pop(pubkey, None)
        if removed:
            self._mark_gap(
                stream_id=self._active_stream_id or "unknown",
                expected_sequence=None,
                received_sequence=None,
                reason="explicit_fork_rollback",
            )
        return tuple(sorted(removed, key=lambda item: (item.slot, item.write_version, item.pubkey)))
