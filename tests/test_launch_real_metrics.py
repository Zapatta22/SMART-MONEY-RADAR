"""Independent regressions for Solana Live timing, deduplication and fail-closed metrics.

No external network, credentials or claims of measured mainnet latency.
"""
import asyncio
import json
import unittest
from dataclasses import dataclass

from smart_money_radar.services.launch_live_monitor import (
    LaunchLiveMonitor, _percentile,
)


@dataclass
class FinalizedResult:
    new_deliveries: int = 0
    finalized_signatures: tuple[str, ...] = ()
    rpc_elapsed_seconds: float | None = 0.001
    persistence_seconds: float | None = 0.002


class FinalizedRPC:
    def __init__(self):
        self.calls = []
        self.responses = []
        self.error = None

    async def synchronize(self, address, *, stop_event=None):
        self.calls.append(address)
        if self.error:
            raise self.error
        if self.responses:
            return self.responses.pop(0)
        return FinalizedResult()


class ScriptedSocket:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def send(self, message):
        self.sent.append(json.loads(message))

    async def recv(self):
        value = next(self.frames, ConnectionError("disconnect"))
        if isinstance(value, Exception):
            raise value
        return json.dumps(value)


def notification(signature):
    return {"jsonrpc": "2.0", "method": "logsNotification",
            "params": {"subscription": 81,
                       "result": {"context": {"slot": 100},
                                  "value": {"signature": signature, "err": None}}}}


def build_monitor(rpc, frames):
    socket = ScriptedSocket([{"jsonrpc": "2.0", "id": 1, "result": 81}, *frames])
    monitor = LaunchLiveMonitor(
        "wss://example.invalid", rpc, ("public-solana-address",),
        connector=lambda *args, **kwargs: socket,
        sleep=lambda _: asyncio.sleep(0),
        jitter=lambda: 0, initial_backoff=0.001, max_backoff=0.002,
    )
    return monitor, socket


class LiveEvidenceMetricsTests(unittest.TestCase):
    def test_unfinalized_hint_is_not_claimed_as_finalized(self):
        rpc = FinalizedRPC()
        monitor, socket = build_monitor(rpc, [notification("pending")])
        asyncio.run(monitor.run(asyncio.Event(), max_sessions=1))
        metrics = monitor.metrics
        self.assertEqual(metrics.notifications, 1)
        self.assertEqual(metrics.finalized_hints, 0)
        self.assertEqual(metrics.unresolved_hints, 1)
        self.assertIsNone(metrics.notification_to_finalized_p95_ms)
        self.assertEqual(metrics.coverage, "UNKNOWN")
        self.assertEqual(socket.sent[0]["params"][1]["commitment"], "confirmed")

    def test_p50_p95_p99_need_at_least_twenty_matched_samples(self):
        rpc = FinalizedRPC()
        sigs = [f"signature-{idx}" for idx in range(20)]
        rpc.responses = [FinalizedResult()] + [
            FinalizedResult(finalized_signatures=(sig,)) for sig in sigs
        ]
        monitor, _ = build_monitor(rpc, [notification(sig) for sig in sigs])
        asyncio.run(monitor.run(asyncio.Event(), max_sessions=1))
        m = monitor.metrics
        self.assertEqual(m.finalized_hints, 20)
        self.assertEqual(m.unresolved_hints, 0)
        self.assertEqual(m.finalized_samples, 20)
        self.assertEqual(m.duplicate_notifications, 0)
        self.assertIsNotNone(m.notification_to_finalized_p95_ms)
        self.assertIsNotNone(m.notification_to_finalized_p99_ms)
        self.assertLessEqual(m.notification_to_finalized_p50_ms,
                             m.notification_to_finalized_p95_ms)
        self.assertLessEqual(m.notification_to_finalized_p95_ms,
                             m.notification_to_finalized_p99_ms)
        self.assertIsNotNone(m.rpc_collection_p95_ms)
        self.assertIsNotNone(m.persistence_p95_ms)

    def test_duplicate_hint_only_has_one_finalized_latency_sample(self):
        rpc = FinalizedRPC()
        rpc.responses = [
            FinalizedResult(), FinalizedResult(),
            FinalizedResult(finalized_signatures=("same",)),
        ]
        monitor, _ = build_monitor(rpc, [notification("same"), notification("same")])
        asyncio.run(monitor.run(asyncio.Event(), max_sessions=1))
        self.assertEqual(monitor.metrics.notifications, 2)
        self.assertEqual(monitor.metrics.duplicate_notifications, 1)
        self.assertEqual(monitor.metrics.finalized_hints, 1)
        self.assertEqual(monitor.metrics.unresolved_hints, 0)

    def test_rate_limit_never_promotes_hint(self):
        rpc = FinalizedRPC()
        rpc.responses = [FinalizedResult()]
        class FailOnSecond(FinalizedRPC):
            async def synchronize(self, address, *, stop_event=None):
                self.calls.append(address)
                if len(self.calls) > 1:
                    raise RuntimeError("RPC HTTP 429")
                return FinalizedResult()
        rpc = FailOnSecond()
        monitor, _ = build_monitor(rpc, [notification("not-final")])
        asyncio.run(monitor.run(asyncio.Event(), max_sessions=1))
        self.assertEqual(monitor.metrics.rate_limit_errors, 1)
        self.assertEqual(monitor.metrics.finalized_hints, 0)
        self.assertEqual(monitor.metrics.unresolved_hints, 1)
        self.assertEqual(monitor.metrics.incomplete_reconciliations, 1)

    def test_sample_percentile_not_fabricated_for_small_samples(self):
        from collections import deque
        self.assertIsNone(_percentile(deque(), 0.95))
        self.assertIsNone(_percentile(deque([100.0] * 19), 0.95))
        self.assertEqual(_percentile(deque(range(1, 21)), 0.95), 19)
        self.assertEqual(_percentile(deque(range(1, 21)), 0.99), 20)


if __name__ == "__main__":
    unittest.main()
