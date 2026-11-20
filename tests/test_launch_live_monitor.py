"""Adversarial websocket tests for the Solana Launch Radar live monitor.

Applied to a temporary integration branch after the implementation branch.
"""
import asyncio
import json
import unittest
from dataclasses import dataclass

from smart_money_radar.services.launch_live_monitor import LaunchLiveMonitor


@dataclass
class Outcome:
    new_deliveries: int = 0


class Backfill:
    def __init__(self, events=None):
        self.calls = []
        self.events = events or []
        self.fail = False

    async def synchronize(self, address, *, stop_event=None):
        self.calls.append(address)
        if self.fail:
            raise RuntimeError("RPC 429: exhausted retries")
        return Outcome(self.events.pop(0) if self.events else 0)


class Socket:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def send(self, value):
        self.sent.append(json.loads(value))

    async def recv(self):
        frame = next(self.frames, ConnectionError("disconnect"))
        if isinstance(frame, Exception):
            raise frame
        return json.dumps(frame)


class Connector:
    def __init__(self, *sessions):
        self.sessions = list(sessions)
        self.calls = 0
    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.sessions.pop(0)


class LaunchLiveMonitorTests(unittest.TestCase):
    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    @staticmethod
    def ack(subid=101):
        return {"jsonrpc":"2.0","id":1,"result":subid}

    @staticmethod
    def notify(sig="abc", subid=101):
        return {"jsonrpc":"2.0","method":"logsNotification",
                "params":{"subscription":subid,
                          "result":{"value":{"signature":sig, "err":None},
                                    "context":{"slot":987}}}}

    def monitor(self, backfill, connector, *, sleep=None, heartbeat=30):
        return LaunchLiveMonitor(
            "wss://solana.example.invalid", backfill, ("watched-address",),
            connector=connector, sleep=sleep or asyncio.sleep,
            heartbeat_seconds=heartbeat, jitter=lambda:0,
            initial_backoff=0.001, max_backoff=0.002,
        )

    def test_subscribe_ack_and_reconcile_before_notifications(self):
        store = Backfill([2, 1])
        conn = Connector(Socket([self.ack(), self.notify("A"), ConnectionError("drop")]))
        monitor = self.monitor(store, conn)
        self.run_async(monitor.run(asyncio.Event(), max_sessions=1))
        self.assertEqual([call["method"] for call in conn.sessions[0].sent], ["logsSubscribe"]) if conn.sessions else None
        self.assertEqual(store.calls, ["watched-address", "watched-address"])
        self.assertEqual(monitor.metrics.recovered_deliveries, 3)
        self.assertEqual(monitor.metrics.notifications, 1)
        self.assertEqual(monitor.metrics.coverage, "UNKNOWN")

    def test_reconnection_replays_finalized_history_before_new_notifications(self):
        store = Backfill([1, 2, 0])
        sockets = [
            Socket([self.ack(), ConnectionError("disconnect")]),
            Socket([self.ack(202), self.notify("overlap", 202), ConnectionError("disconnect")]),
        ]
        conn = Connector(*sockets)
        monitor = self.monitor(store, conn, sleep=lambda _: asyncio.sleep(0))
        self.run_async(monitor.run(asyncio.Event(), max_sessions=2))
        self.assertEqual(conn.calls, 2)
        self.assertEqual(monitor.metrics.sessions, 2)
        self.assertEqual(store.calls, ["watched-address"]*3)
        self.assertEqual(monitor.metrics.recovered_deliveries, 3)

    def test_failed_rpc_during_backfill_never_accepts_notification_as_finalized(self):
        store = Backfill()
        store.fail = True
        conn = Connector(Socket([self.ack(), self.notify()]))
        monitor = self.monitor(store, conn)
        self.run_async(monitor.run(asyncio.Event(), max_sessions=1))
        self.assertEqual(monitor.metrics.notifications, 0)
        self.assertEqual(monitor.metrics.reconciliations, 0)
        self.assertEqual(monitor.metrics.incomplete_reconciliations, 1)

    def test_malformed_notification_forces_reconnect(self):
        store = Backfill()
        conn = Connector(Socket([self.ack(), self.notify(subid=999)]))
        monitor = self.monitor(store, conn)
        self.run_async(monitor.run(asyncio.Event(), max_sessions=1))
        self.assertEqual(monitor.metrics.notifications, 0)
        self.assertEqual(monitor.metrics.reconnects, 1)

    def test_invalid_subscription_ack_never_advances_recovery(self):
        store = Backfill()
        conn = Connector(Socket([{"id": 1, "error":{"code":429}}]))
        monitor = self.monitor(store, conn)
        self.run_async(monitor.run(asyncio.Event(), max_sessions=1))
        self.assertEqual(store.calls, [])
        self.assertEqual(monitor.metrics.sessions, 1)
        self.assertEqual(monitor.metrics.reconciliations, 0)

    def test_periodic_rpc_recovery_when_socket_is_silent(self):
        store = Backfill([1, 0])
        class QuietSocket(Socket):
            def __init__(self, frames):
                super().__init__(frames)
                self.receives = 0

            async def recv(self):
                self.receives += 1
                if self.receives > 1:
                    await asyncio.sleep(3600)
                return await super().recv()
        conn = Connector(QuietSocket([self.ack()]))
        monitor = self.monitor(store, conn, heartbeat=0.01)
        self.run_async(monitor.run(asyncio.Event(), max_sessions=1))
        self.assertEqual(monitor.metrics.reconciliations, 2)
        self.assertEqual(monitor.metrics.reconnects, 1)

    def test_shutdown_during_backoff(self):
        stop = asyncio.Event()
        async def stopping_sleep(_):
            stop.set()
        conn = Connector(Socket([self.ack(), ConnectionError("lost")]))
        monitor = self.monitor(Backfill(), conn, sleep=stopping_sleep)
        self.run_async(monitor.run(stop))
        self.assertEqual(conn.calls, 1)


if __name__ == "__main__":
    unittest.main()
