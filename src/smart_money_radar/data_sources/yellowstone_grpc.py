"""Bounded, read-only transport capture for Yellowstone gRPC."""

from dataclasses import dataclass
from queue import Queue
from time import monotonic, sleep
from uuid import uuid4

from google.protobuf import descriptor_pb2, message_factory
from google.protobuf.json_format import ParseDict

from smart_money_radar.data_sources.yellowstone_receiver import (
    YellowstoneFrameReceiver,
    load_yellowstone_decoder,
)
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.storage.collector_authority import check_collector


@dataclass(frozen=True)
class YellowstoneCapture:
    stream_id: str
    ordering_domain_id: str
    frame_count: int
    outcome: str


def capture_yellowstone(
    store: SQLiteGeyserRawStore, *, target: str, source_id: str,
    descriptor: bytes, subscription: dict, token: str | None = None,
    max_frames: int = 1000, timeout: float = 60,
) -> YellowstoneCapture:
    """Capture one TLS connection. A later call gets a fresh ordering domain."""
    import grpc
    check_collector(store)

    if not 1 <= max_frames <= 100_000 or not 0 < timeout <= 600:
        raise ValueError("limites de captura Yellowstone inválidos")
    if not target or "://" in target or "/" in target:
        raise ValueError("destino Yellowstone deve usar host:porta")
    if not any(subscription.get(field) for field in (
        "accounts", "slots", "transactions", "transactionsStatus",
        "blocks", "blocksMeta", "entry", "blockFooter",
    )):
        raise ValueError("a captura Yellowstone exige filtros explícitos")
    decode = load_yellowstone_decoder(descriptor)
    descriptors = descriptor_pb2.FileDescriptorSet.FromString(descriptor)
    request_type = message_factory.GetMessages(descriptors.file).get("geyser.SubscribeRequest")
    if request_type is None:
        raise ValueError("descriptor sem geyser.SubscribeRequest")
    subscribe = ParseDict(subscription, request_type()).SerializeToString()

    stream_id = str(uuid4())
    domain = str(uuid4())
    receiver = YellowstoneFrameReceiver(
        store, decode, source_id=source_id, stream_id=stream_id,
        ordering_domain_id=domain, initial_sequence=0,
    )
    store.start_capture_session(source_id, stream_id)
    pending: Queue[bytes | None] = Queue()

    def requests():
        yield subscribe
        while (message := pending.get()) is not None:
            yield message

    metadata = (("x-token", token),) if token else ()
    frames = 0
    outcome = "eof"
    with grpc.secure_channel(target, grpc.ssl_channel_credentials()) as channel:
        call = None
        try:
            call = channel.stream_stream("/geyser.Geyser/Subscribe")(
                requests(), timeout=timeout, metadata=metadata,
            )
            for payload in call:
                receipt = receiver.receive(payload, stream_sequence=frames)
                frames += 1
                if receipt.interrupted:
                    outcome = "invalid_frame"
                    break
                if frames == max_frames:
                    outcome = "frame_limit"
                    break
                if decode(payload).WhichOneof("update_oneof") == "ping":
                    pong = request_type()
                    pong.ping.id = frames
                    pending.put(pong.SerializeToString())
        except grpc.RpcError as exc:
            outcome = exc.code().name.lower()
        finally:
            pending.put(None)
            if call is not None:
                call.cancel()
    frame_count = store.finish_capture_session(source_id, stream_id, outcome)
    return YellowstoneCapture(stream_id, domain, frame_count, outcome)


def capture_yellowstone_sessions(
    store: SQLiteGeyserRawStore, *, target: str, source_id: str,
    descriptor: bytes, subscription: dict, token: str | None = None,
    max_frames: int = 1000, timeout: int = 60, max_attempts: int = 1,
) -> tuple[YellowstoneCapture, ...]:
    """Retry transient disconnections within a shared frame and time budget."""
    if not 1 <= max_attempts <= 5 or not 1 <= timeout <= 600 or not 1 <= max_frames <= 100_000:
        raise ValueError("limites de captura Yellowstone inválidos")
    deadline = monotonic() + timeout
    attempts = []
    for attempt in range(max_attempts):
        remaining_time = deadline - monotonic()
        if remaining_time <= 0:
            break
        capture = capture_yellowstone(
            store, target=target, source_id=source_id, descriptor=descriptor,
            subscription=subscription, token=token, max_frames=max_frames,
            timeout=remaining_time,
        )
        attempts.append(capture)
        max_frames -= capture.frame_count
        if capture.outcome != "unavailable" or attempt + 1 == max_attempts or max_frames <= 0:
            break
        backoff = 2**attempt
        if monotonic() + backoff >= deadline:
            break
        check_collector(store)
        sleep(backoff)
        check_collector(store)
    return tuple(attempts)
