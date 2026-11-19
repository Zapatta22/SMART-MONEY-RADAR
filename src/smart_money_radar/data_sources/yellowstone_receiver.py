"""Offline receiver for a single Yellowstone SubscribeUpdate transport session."""

from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import replace
import hashlib

from google.protobuf import descriptor_pb2, message_factory
from google.protobuf.message import DecodeError, Message

from smart_money_radar.data_sources.geyser_account_timeline import AccountUpdateTimeline
from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate
from smart_money_radar.data_sources.geyser_bank_lineage import (
    BankKey,
    NormalizedBlockMeta,
    NormalizedEntryUpdateParent,
    NormalizedSlotUpdate,
)
from smart_money_radar.data_sources.geyser_ingestion import NormalizedGeyserEvent
from smart_money_radar.data_sources.geyser_proto_adapter import adapt_subscribe_update
from smart_money_radar.data_sources.geyser_transaction_updates import NormalizedTransactionObservation
from smart_money_radar.data_sources.yellowstone_transaction_evidence import (
    YellowstoneTransactionEvidence,
    project_yellowstone_evidence,
    verify_yellowstone_block_order,
)
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore, WireFrameReceipt


def load_yellowstone_decoder(descriptor_set: bytes) -> Callable[[bytes], Message]:
    """Load the official SubscribeUpdate type from a descriptor set with imports."""
    descriptors = descriptor_pb2.FileDescriptorSet.FromString(descriptor_set)
    messages = message_factory.GetMessages(descriptors.file)
    update = messages.get("geyser.SubscribeUpdate")
    if update is None or "update_oneof" not in update.DESCRIPTOR.oneofs_by_name:
        raise ValueError("descriptor não define geyser.SubscribeUpdate com update_oneof")
    return update.FromString


class YellowstoneFrameReceiver:
    """Journal complete protobuf frames in the connection's sequence domain."""

    def __init__(
        self, store: SQLiteGeyserRawStore, decode: Callable[[bytes], Message], *,
        source_id: str, stream_id: str, ordering_domain_id: str, initial_sequence: int | None = None,
    ) -> None:
        if initial_sequence is None:
            store.require_frame_stream(source_id, stream_id, ordering_domain_id)
        else:
            store.register_frame_stream(source_id, stream_id, ordering_domain_id, initial_sequence)
        self._store = store
        self._decode = decode
        self._source_id = source_id
        self._stream_id = stream_id
        self._ordering_domain_id = ordering_domain_id

    @property
    def database_path(self) -> str:
        return self._store.database_path

    @property
    def scope(self) -> tuple[str, str, str]:
        """Return the journal source, connection and ordering domain."""
        return self._source_id, self._stream_id, self._ordering_domain_id

    def receive(self, payload: bytes, *, stream_sequence: int) -> WireFrameReceipt:
        """Capture a frame at its assigned coordinate, including frames rejected by decoding."""
        if not isinstance(payload, bytes):
            raise TypeError("payload deve ser bytes")
        kind = None
        try:
            message = self._decode(payload)
            selected = message.WhichOneof("update_oneof")
            if selected is not None:
                adapt_subscribe_update(
                    message, source_id=self._source_id, stream_id=self._stream_id,
                    ordering_domain_id=self._ordering_domain_id, stream_sequence=stream_sequence,
                )
                kind = selected
        except (DecodeError, ValueError):
            pass
        return self._store.append_wire_frame(
            source_id=self._source_id, stream_id=self._stream_id,
            ordering_domain_id=self._ordering_domain_id, stream_sequence=stream_sequence,
            payload=payload, frame_kind=kind,
        )

    def replay(
        self,
    ) -> Iterator[tuple[int, NormalizedGeyserEvent | NormalizedTransactionObservation | None]]:
        """Decode a consistent stream snapshot, including coordinates of control frames."""
        for sequence, _, _, event in self._replay_frames():
            yield sequence, event

    def replay_transaction_evidence(self) -> Iterator[YellowstoneTransactionEvidence]:
        """Derive Solana decoder evidence while replay verifies the wire journal."""
        for _, _, frame, event in self._replay_frames():
            if isinstance(event, NormalizedTransactionObservation):
                yield project_yellowstone_evidence(frame, event)

    def _replay_frames(self):
        for sequence, payload in self._store.iter_wire_frames(
            self._source_id, self._stream_id, self._ordering_domain_id,
        ):
            frame = self._decode(payload)
            event = adapt_subscribe_update(
                frame, source_id=self._source_id, stream_id=self._stream_id,
                ordering_domain_id=self._ordering_domain_id, stream_sequence=sequence,
                raw_message_bytes=payload,
            )
            yield sequence, payload, frame, event

    def transaction_evidence_at(
        self, stream_sequence: int, *, block_sequence: int | None = None,
    ) -> YellowstoneTransactionEvidence | None:
        """Resolve a transaction and its finalized account transitions in one wire snapshot."""
        timeline = AccountUpdateTimeline()
        signatures: Counter[str] = Counter()
        evidence = None
        block = None
        block_digest = None
        for sequence, payload, frame, event in self._replay_frames():
            if sequence == block_sequence and frame.WhichOneof("update_oneof") == "block":
                block = frame.block
                block_digest = hashlib.sha256(payload).hexdigest()
            self._apply_timeline_event(timeline, sequence, event)
            if isinstance(event, NormalizedTransactionObservation):
                signatures[event.transaction_signature] += 1
                if sequence == stream_sequence:
                    evidence = project_yellowstone_evidence(frame, event)
        if evidence is None:
            return None
        observation = evidence.observation
        if signatures[observation.transaction_signature] != 1:
            raise ValueError("assinatura Yellowstone ambígua no domínio")
        tracker = timeline.bank_lineage_tracker
        bank_key = BankKey(observation.source_id, observation.slot, observation.bank_id or 0)
        if (not observation.bank_id or not evidence.bundle.structurally_complete
                or tracker.is_bank_finalized(bank_key) is not True):
            if block_sequence is not None:
                raise ValueError("banco sem finalidade para comprovar a ordem no bloco")
            return evidence
        block_order = None
        if block_sequence is not None:
            bank = next(node for node in tracker.banks if node.key == bank_key)
            if block is None or block_digest is None:
                raise ValueError("frame de bloco Yellowstone ausente na sequência informada")
            if not bank.blockhash or bank.blockhash != block.blockhash:
                raise ValueError("hash do bloco diverge dos metadados do banco Yellowstone")
            block_order = verify_yellowstone_block_order(
                block, observation=observation, block_sequence=block_sequence,
                block_wire_sha256=block_digest,
            )
        conflicted_accounts = {item.pubkey for item in timeline.conflicts}
        matching = [
            update for update in timeline.transition_for(observation.transaction_signature)
            if update.evidence_classification == "BANK_PROVIDER_REPORTED_FINALIZED"
            and update.pubkey in evidence.transaction_accounts
            and update.pubkey not in conflicted_accounts
            and update.slot == observation.slot
            and update.post_state.bank_id == observation.bank_id
            and update.pre_state.source == update.post_state.source == observation.source_id
            and update.pre_state.stream_id == update.post_state.stream_id == observation.stream_id
        ]
        counts = Counter(update.pubkey for update in matching)
        return replace(
            evidence,
            provider_reported_finalized=True,
            block_order=block_order,
            account_transitions=tuple(update for update in matching if counts[update.pubkey] == 1),
        )

    def rebuild_account_timeline(self) -> AccountUpdateTimeline:
        """Return a timeline only after every frame in this domain passes replay."""
        timeline = AccountUpdateTimeline()
        for sequence, event in self.replay():
            self._apply_timeline_event(timeline, sequence, event)
        return timeline

    def _apply_timeline_event(
        self, timeline: AccountUpdateTimeline, sequence: int,
        event: NormalizedGeyserEvent | NormalizedTransactionObservation | None,
    ) -> None:
        if isinstance(event, NormalizedAccountUpdate):
            timeline.add(event)
            return
        timeline.advance_transport(self._stream_id, sequence)
        if isinstance(event, NormalizedSlotUpdate):
            timeline.add_slot_update(event)
        elif isinstance(event, NormalizedBlockMeta):
            timeline.add_block_meta(event)
        elif isinstance(event, NormalizedEntryUpdateParent):
            timeline.add_entry_update_parent(event)
