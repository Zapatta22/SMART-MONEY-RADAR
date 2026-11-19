"""Offline receiver for a single Yellowstone SubscribeUpdate transport session."""

from collections.abc import Callable, Iterator

from google.protobuf import descriptor_pb2, message_factory
from google.protobuf.message import DecodeError, Message

from smart_money_radar.data_sources.geyser_account_timeline import AccountUpdateTimeline
from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate
from smart_money_radar.data_sources.geyser_bank_lineage import (
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
        source_id: str, stream_id: str, ordering_domain_id: str, initial_sequence: int,
    ) -> None:
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
        for sequence, _, event in self._replay_frames():
            yield sequence, event

    def replay_transaction_evidence(self) -> Iterator[YellowstoneTransactionEvidence]:
        """Derive Solana decoder evidence while replay verifies the wire journal."""
        for _, frame, event in self._replay_frames():
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
            yield sequence, frame, event

    def rebuild_account_timeline(self) -> AccountUpdateTimeline:
        """Return a timeline only after every frame in this domain passes replay."""
        timeline = AccountUpdateTimeline()
        for sequence, event in self.replay():
            if isinstance(event, NormalizedAccountUpdate):
                timeline.add(event)
                continue
            timeline.advance_transport(self._stream_id, sequence)
            if isinstance(event, NormalizedSlotUpdate):
                timeline.add_slot_update(event)
            elif isinstance(event, NormalizedBlockMeta):
                timeline.add_block_meta(event)
            elif isinstance(event, NormalizedEntryUpdateParent):
                timeline.add_entry_update_parent(event)
        return timeline
