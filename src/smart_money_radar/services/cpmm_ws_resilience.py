"""Bounded, offline-testable resilience policy for public Solana WebSocket.

Only the receiver is authorized to read frames. Retry is permitted ONLY when
a new transport connection and fresh four-account subscriptions + a fresh
RPC baseline can be established. Neither the retry counter nor a local frame
sequence certifies ledger continuity. The policy never enables finance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Literal

Failure = Literal["CLOSED", "PING_TIMEOUT", "IDLE_TIMEOUT", "NETWORK_ERROR",
                  "SUBSCRIPTION_FAILED", "BASELINE_FAILED", "PERSISTENCE_FAILED",
                  "NORMAL_END"]


@dataclass(frozen=True)
class WsResiliencePolicy:
    max_reconnects: int = 1
    ping_interval_seconds: int = 20
    ping_timeout_seconds: int = 10
    read_timeout_seconds: int = 3
    max_silent_seconds: int = 45
    backoff_initial_seconds: float = 1.0
    backoff_max_seconds: float = 4.0
    jitter_fraction: float = 0.15

    def __post_init__(self):
        if type(self.max_reconnects) is not int or not 0 <= self.max_reconnects <= 3:
            raise ValueError("reconnect limit invalid")
        if (not 5 <= self.ping_interval_seconds <= 120 or
            not 2 <= self.ping_timeout_seconds <= 60 or
            not 1 <= self.read_timeout_seconds <= 30 or
            not 5 <= self.max_silent_seconds <= 360):
            raise ValueError("heartbeat and timeout bounds invalid")
        if not (0.25 <= self.backoff_initial_seconds <=
                self.backoff_max_seconds <= 30):
            raise ValueError("backoff bounds invalid")
        if not 0 <= self.jitter_fraction <= .5:
            raise ValueError("jitter bound invalid")

    def backoff(self, reconnect_number: int, *, seed: str) -> float:
        if not isinstance(seed, str) or not seed:
            raise ValueError("stable seed required")
        if type(reconnect_number) is not int or not 1 <= reconnect_number <= self.max_reconnects:
            raise ValueError("reconnect budget exhausted")
        base=min(self.backoff_max_seconds,
                 self.backoff_initial_seconds * (2 ** (reconnect_number-1)))
        n=int.from_bytes(hashlib.sha256(
            (seed+"|"+str(reconnect_number)).encode()).digest()[:8],"big")
        # Stable deterministic bounded jitter, no randomness in unit tests.
        factor=1+self.jitter_fraction*(2*(n/(2**64-1))-1)
        return max(0.,min(self.backoff_max_seconds,base*factor))


def classify_ws_failure(exc: BaseException | None, *, phase: str) -> Failure:
    """Do not claim cause from class name alone; preserve exception details."""
    if exc is None:
        return "NORMAL_END"
    if phase=="persist":
        return "PERSISTENCE_FAILED"
    if phase=="baseline":
        return "BASELINE_FAILED"
    if phase=="subscribe":
        return "SUBSCRIPTION_FAILED"
    name=type(exc).__name__
    if name in {"ConnectionClosed","ConnectionClosedOK","ConnectionClosedError"}:
        return "CLOSED"
    if name in {"TimeoutError","CancelledError"}:
        return "PING_TIMEOUT" if phase=="ping" else "IDLE_TIMEOUT"
    return "NETWORK_ERROR"


@dataclass(frozen=True)
class DisconnectRecord:
    previous_session_id: str
    failure: Failure
    phase: str
    detected_at: str
    error_type: str
    error_message: str
    previous_frame_count: int
    gap_marked: bool = True
    coverage: str = "UNKNOWN"
    checkpoint_proves_ledger_coverage: bool = False
    operation_authorized: bool = False


def disconnect_record(*, session_id: str, exc: BaseException,
                      phase: str, frames: int, when: datetime) -> DisconnectRecord:
    if not isinstance(when,datetime) or when.utcoffset() is None:
        raise ValueError("timestamp must have timezone")
    if type(frames) is not int or frames<0:
        raise ValueError("frame count invalid")
    if not session_id:
        raise ValueError("session required")
    return DisconnectRecord(session_id,classify_ws_failure(exc,phase=phase),
                            phase,when.astimezone(timezone.utc).isoformat(),
                            type(exc).__name__,str(exc)[:500],frames)


def reconnection_is_new_observation(*, previous_session_id: str,
                                    new_session_id: str,
                                    acked_accounts: int,
                                    baseline_verified: bool,
                                    previous_gap: DisconnectRecord) -> bool:
    if previous_session_id==new_session_id or not new_session_id:
        raise ValueError("reconnection must use new stream/domain identity")
    if previous_gap.previous_session_id!=previous_session_id:
        raise ValueError("previous gap identity mismatch")
    if not previous_gap.gap_marked or previous_gap.coverage!="UNKNOWN":
        raise ValueError("reconnection attempted without preserved gap")
    return acked_accounts==4 and baseline_verified
