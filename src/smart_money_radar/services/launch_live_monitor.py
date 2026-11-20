"""Read-only live Solana launch subscriptions reconciled against finalized RPC.

Notifications are *hints*, not final evidence or a durable delivery stream.
No checkpoint advances from a WebSocket message. Every notification triggers
bounded finalized RPC reconciliation, and reconnect always starts with backfill.
"""
from __future__ import annotations

import asyncio
import math
import json
import logging
import random
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from websockets import connect

from smart_money_radar.services.launch_live_backfill import (
    FinalizedLaunchBackfill, LaunchBackfillGap,
)


@dataclass(frozen=True)
class LaunchLiveMetrics:
    sessions: int
    reconnects: int
    notifications: int
    reconciliations: int
    recovered_deliveries: int
    incomplete_reconciliations: int
    last_reconciliation_seconds: float | None
    coverage: str = "UNKNOWN"
    finalized_hints: int = 0
    duplicate_notifications: int = 0
    unresolved_hints: int = 0
    rate_limit_errors: int = 0
    notification_to_finalized_p50_ms: float | None = None
    notification_to_finalized_p95_ms: float | None = None
    notification_to_finalized_p99_ms: float | None = None
    finalized_samples: int = 0
    rpc_collection_p95_ms: float | None = None
    persistence_p95_ms: float | None = None
    reconnect_p95_ms: float | None = None


def _percentile(samples: deque[float], proportion: float) -> float | None:
    """Nearest-rank empirical percentile, only with >=20 observations."""
    if len(samples) < 20:
        return None
    ordered = sorted(samples)
    return round(ordered[max(0, math.ceil(len(ordered) * proportion) - 1)], 3)


class LaunchLiveMonitor:
    """Subscribe before backfill to reduce races; reconcile on every notification.

    `logsSubscribe` uses confirmed notifications solely to wake a finalized
    RPC collector. Fail closed on RPC gaps. Provider inactivity never proves
    completeness. A watchdog triggers periodic reconciliation even when no
    notifications arrive, then forces reconnect to repair subscriptions.
    """

    def __init__(
        self,
        websocket_url: str,
        backfill: FinalizedLaunchBackfill,
        addresses: Sequence[str],
        *,
        connector: Callable[..., Any] = connect,
        sleep: Callable[..., Any] = asyncio.sleep,
        logger: logging.Logger | None = None,
        initial_backoff: float = 1.0,
        max_backoff: float = 30.0,
        heartbeat_seconds: float = 30.0,
        jitter: Callable[[], float] = random.random,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(websocket_url, str) or not websocket_url.startswith("wss://"):
            raise ValueError("WebSocket TLS obrigatório")
        if (not addresses or any(not isinstance(a, str) or not a.strip() for a in addresses)
                or len(set(addresses)) != len(addresses)):
            raise ValueError("endereços públicos inválidos ou duplicados")
        if (initial_backoff <= 0 or max_backoff < initial_backoff
                or heartbeat_seconds <= 0):
            raise ValueError("limites de conexão inválidos")
        self.websocket_url = websocket_url
        self.backfill = backfill
        self.addresses = tuple(addresses)
        self.connector = connector
        self.sleep = sleep
        self.logger = logger or logging.getLogger(__name__)
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.heartbeat_seconds = heartbeat_seconds
        self.jitter = jitter
        self.clock = clock
        self.sessions = self.reconnects = self.notifications = 0
        self.reconciliations = self.recovered_deliveries = 0
        self.incomplete_reconciliations = 0
        self.last_reconciliation_seconds = None
        self.finalized_hints = 0
        self.duplicate_notifications = 0
        self.rate_limit_errors = 0
        self._pending_hints: dict[tuple[str, str], float] = {}
        self._finalized_latency_ms: deque[float] = deque(maxlen=4096)
        self._rpc_latency_ms: deque[float] = deque(maxlen=4096)
        self._persistence_latency_ms: deque[float] = deque(maxlen=4096)
        self._reconnect_latency_ms: deque[float] = deque(maxlen=4096)
        self._disconnected_since: float | None = None

    @property
    def metrics(self) -> LaunchLiveMetrics:
        return LaunchLiveMetrics(
            sessions=self.sessions,
            reconnects=self.reconnects,
            notifications=self.notifications,
            reconciliations=self.reconciliations,
            recovered_deliveries=self.recovered_deliveries,
            incomplete_reconciliations=self.incomplete_reconciliations,
            last_reconciliation_seconds=self.last_reconciliation_seconds,
            finalized_hints=self.finalized_hints,
            duplicate_notifications=self.duplicate_notifications,
            unresolved_hints=len(self._pending_hints),
            rate_limit_errors=self.rate_limit_errors,
            notification_to_finalized_p50_ms=_percentile(self._finalized_latency_ms, 0.50),
            notification_to_finalized_p95_ms=_percentile(self._finalized_latency_ms, 0.95),
            notification_to_finalized_p99_ms=_percentile(self._finalized_latency_ms, 0.99),
            finalized_samples=len(self._finalized_latency_ms),
            rpc_collection_p95_ms=_percentile(self._rpc_latency_ms, 0.95),
            persistence_p95_ms=_percentile(self._persistence_latency_ms, 0.95),
            reconnect_p95_ms=_percentile(self._reconnect_latency_ms, 0.95),
        )

    async def _reconcile(self, address: str, stop: asyncio.Event) -> None:
        start = self.clock()
        try:
            outcome = await self.backfill.synchronize(address, stop_event=stop)
        except Exception as exc:
            self.incomplete_reconciliations += 1
            if "429" in str(exc):
                self.rate_limit_errors += 1
            raise
        self.reconciliations += 1
        self.recovered_deliveries += outcome.new_deliveries
        self.last_reconciliation_seconds = max(0.0, self.clock() - start)
        rpc_elapsed = getattr(outcome, "rpc_elapsed_seconds", None)
        persistence_elapsed = getattr(outcome, "persistence_seconds", None)
        if rpc_elapsed is not None:
            self._rpc_latency_ms.append(max(0.0, rpc_elapsed) * 1000)
        if persistence_elapsed is not None:
            self._persistence_latency_ms.append(max(0.0, persistence_elapsed) * 1000)
        # The timestamp is local reception, not provider emission time.
        # Only the matching signature returned by finalized RPC can close a hint.
        for signature in getattr(outcome, "finalized_signatures", ()):
            received_at = self._pending_hints.pop((address, signature), None)
            if received_at is not None:
                self._finalized_latency_ms.append(
                    max(0.0, self.clock() - received_at) * 1000
                )
                self.finalized_hints += 1

    async def _listen(self, stop: asyncio.Event) -> None:
        async with self.connector(
            self.websocket_url, ping_interval=20, ping_timeout=20,
            open_timeout=10, max_size=1_048_576,
        ) as ws:
            self.sessions += 1
            requests = {index: address for index, address in enumerate(self.addresses, 1)}
            subs: dict[int, str] = {}
            for request_id, address in requests.items():
                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "id": request_id, "method": "logsSubscribe",
                    "params": [{"mentions": [address]}, {"commitment": "confirmed"}],
                }))
            # Wait until all subscriptions are positively acknowledged.
            # Subscription replies can arrive out of order.
            while len(subs) < len(requests):
                raw = await asyncio.wait_for(ws.recv(), self.heartbeat_seconds)
                reply = json.loads(raw)
                if not isinstance(reply, dict) or type(reply.get("id")) is not int:
                    raise ConnectionError("assinatura WebSocket sem confirmação")
                request_id = reply["id"]
                subscription_id = reply.get("result")
                if (request_id not in requests or "error" in reply
                        or type(subscription_id) is not int
                        or subscription_id in subs):
                    raise ConnectionError("logsSubscribe foi recusado ou retornou ID inválido")
                subs[subscription_id] = requests[request_id]
            if self._disconnected_since is not None:
                self._reconnect_latency_ms.append(
                    max(0.0, self.clock() - self._disconnected_since) * 1000
                )
                self._disconnected_since = None
            # Subscribe first, then bounded backfill; socket buffers hints.
            for address in self.addresses:
                await self._reconcile(address, stop)
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), self.heartbeat_seconds)
                except asyncio.TimeoutError:
                    # Quiet stream: periodic RPC reconciliation, not proof of continuity.
                    for address in self.addresses:
                        await self._reconcile(address, stop)
                    raise ConnectionError("heartbeat de aplicação ausente: renovar assinatura")
                message = json.loads(raw)
                if not isinstance(message, dict):
                    raise ConnectionError("mensagem WebSocket inesperada")
                params = message.get("params")
                if not isinstance(params, dict):
                    raise ConnectionError("mensagem WebSocket não reconhecida")
                address = subs.get(params.get("subscription"))
                value = (params.get("result") or {}).get("value")
                if address is None or not isinstance(value, dict):
                    raise ConnectionError("notificação não pertence à assinatura ativa")
                if not isinstance(value.get("signature"), str) or not value["signature"]:
                    raise ConnectionError("notificação sem assinatura")
                signature = value["signature"]
                self.notifications += 1
                key = (address, signature)
                if key in self._pending_hints:
                    self.duplicate_notifications += 1
                else:
                    if len(self._pending_hints) >= 4096:
                        raise ConnectionError(
                            "limite de notificações não finalizadas atingido; "
                            "auditoria de cobertura obrigatória"
                        )
                    self._pending_hints[key] = self.clock()
                # Never use a confirmed notification to populate finalized evidence.
                await self._reconcile(address, stop)

    async def run(self, stop: asyncio.Event, *, max_sessions: int | None = None) -> None:
        if max_sessions is not None and (type(max_sessions) is not int or max_sessions < 1):
            raise ValueError("max_sessions inválido")
        delay = self.initial_backoff
        while not stop.is_set():
            if max_sessions is not None and self.sessions >= max_sessions:
                return
            started = self.clock()
            try:
                await self._listen(stop)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if stop.is_set():
                    return
                self.logger.warning("Launch WebSocket pausado: %s", type(exc).__name__)
            else:
                if stop.is_set():
                    return
            self.reconnects += 1
            if self._disconnected_since is None:
                self._disconnected_since = self.clock()
            if self.clock() - started >= 60:
                delay = self.initial_backoff
            jitter_value = self.jitter()
            if not 0 <= jitter_value <= 1:
                raise ValueError("jitter fora de [0,1]")
            await self._sleep_or_stop(stop, delay * (1 + jitter_value * 0.2))
            delay = min(delay * 2, self.max_backoff)

    async def _sleep_or_stop(self, stop: asyncio.Event, delay: float) -> None:
        wait = asyncio.create_task(self.sleep(delay))
        signal = asyncio.create_task(stop.wait())
        try:
            await asyncio.wait((wait, signal), return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (wait, signal):
                if not task.done():
                    task.cancel()
            await asyncio.gather(wait, signal, return_exceptions=True)
