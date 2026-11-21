"""Bounded Linux/Termux-compatible offline supervisor soak and resource probe."""

import argparse
import json
from math import ceil, isfinite
from pathlib import Path
import resource
import statistics
import tempfile
import time
from datetime import datetime, timezone

from smart_money_radar.services.operational_controls import LocalOperationalControls
from smart_money_radar.services.persistent_supervisor import (
    PersistentSupervisor,
    SupervisorPolicy,
    read_supervisor_status,
)
from smart_money_radar.storage.event_store import SQLiteEventStore


def measure(*, cycles=100, restart_every=None, max_wall_seconds=120, realtime=False):
    """Exercise both radars with a fresh empty archive and optional clean restarts."""
    if type(cycles) is not int or not 1 <= cycles <= 100_000:
        raise ValueError("cycles must be between 1 and 100,000")
    if restart_every is not None and (
        type(restart_every) is not int or not 1 <= restart_every <= cycles
    ):
        raise ValueError("restart interval must be within the cycle budget")
    if type(max_wall_seconds) not in (int, float) or not (
        isfinite(max_wall_seconds) and 0 < max_wall_seconds <= 172_800
    ):
        raise ValueError("wall-time limit must be positive and at most 172,800 seconds")

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "smr.sqlite"
        store = SQLiteEventStore(path)
        key = b"benchmark-local-only" * 2
        synthetic_time = time.time()

        def accelerated_clock():
            return synthetic_time

        clock = time.time if realtime else accelerated_clock
        policy = SupervisorPolicy(interval_seconds=1)

        def size():
            return sum(file.stat().st_size for file in path.parent.glob("smr.sqlite*"))

        before = size()
        wall = time.monotonic()
        deadline = wall + max_wall_seconds
        cpu = time.process_time()
        latencies = []
        restarts = 0
        supervisor = None
        try:
            controls = LocalOperationalControls(store, operator_capability=key)
            for radar in ("launch", "smart_money"):
                controls.apply(
                    capability=key, event_id="start-" + radar, action="START", actor="benchmark",
                    reason="offline empty archive benchmark", radar=radar,
                    at=datetime.fromtimestamp(clock(), timezone.utc),
                )
            supervisor = PersistentSupervisor(store, policy=policy, clock=clock)
            supervisor.acquire()
            while len(latencies) < cycles and time.monotonic() < deadline:
                started = time.monotonic()
                supervisor.cycle()
                latencies.append(time.monotonic() - started)
                if len(latencies) == cycles:
                    break

                if realtime:
                    time.sleep(min(policy.interval_seconds, max(0, deadline - time.monotonic())))
                else:
                    synthetic_time += policy.interval_seconds
                if time.monotonic() >= deadline:
                    break

                if restart_every is not None and len(latencies) % restart_every == 0:
                    supervisor.stop()
                    supervisor = None
                    store.close()
                    store = SQLiteEventStore(path)
                    supervisor = PersistentSupervisor(store, policy=policy, clock=clock)
                    if supervisor.acquire() != restarts + 2:
                        raise RuntimeError("supervisor generation did not advance on restart")
                    restarts += 1
        finally:
            try:
                if supervisor is not None and supervisor.generation is not None:
                    supervisor.stop()
                status = read_supervisor_status(store, now=clock())
                integrity = store.integrity_check()
            finally:
                store.close()

        count = len(latencies)
        actual = {radar: task["cycles"] for radar, task in status["radars"].items()}
        if actual != {"launch": count, "smart_money": count} or status["status"] != "STOPPED":
            raise RuntimeError("supervisor benchmark did not complete every radar cycle")
        metrics = {
            "scope": "EMPTY_ARCHIVE_OFFLINE",
            "clock_mode": "REALTIME" if realtime else "ACCELERATED",
            "completion": "CYCLE_LIMIT" if count == cycles else "WALL_TIME_LIMIT",
            "configured_cycles": cycles,
            "configured_max_wall_seconds": max_wall_seconds,
            "cycles": count,
            "radar_cycles": sum(actual.values()),
            "cycles_by_radar": actual,
            "restarts": restarts,
            "last_generation": status["generation"],
            "cycle_mean_ms": 1000 * statistics.mean(latencies) if count else None,
            "cycle_median_ms": 1000 * statistics.median(latencies) if count else None,
            "cycle_p95_ms": 1000 * sorted(latencies)[ceil(count * 0.95) - 1] if count else None,
            "cycle_max_ms": 1000 * max(latencies) if count else None,
            "wall_seconds": time.monotonic() - wall,
            "cpu_seconds": time.process_time() - cpu,
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "storage_before_bytes": before,
            "storage_after_bytes": size(),
            "sqlite_integrity": integrity,
            "autonomy_24h_verified": False,
        }
        return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=100)
    parser.add_argument("--restart-every", type=int)
    parser.add_argument("--max-wall-seconds", type=float, default=120)
    parser.add_argument("--realtime", action="store_true")
    try:
        metrics = measure(**vars(parser.parse_args()))
    except ValueError as exc:
        parser.error(str(exc))
    print("CM36_BENCHMARK " + json.dumps(metrics, sort_keys=True))
    if metrics["sqlite_integrity"] != ["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
