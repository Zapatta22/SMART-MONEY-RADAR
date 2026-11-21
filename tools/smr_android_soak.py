"""Run an isolated, time-bounded SMR offline soak with a supervised worker."""

import argparse
import json
import math
import os
import platform
import resource
import secrets
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread

from smart_money_radar.services.operational_controls import LocalOperationalControls
from smart_money_radar.services.persistent_supervisor import (
    PersistentSupervisor,
    SupervisorPolicy,
    read_supervisor_status,
)
from smart_money_radar.services.synthetic_paper_ledger import RADARS
from smart_money_radar.storage.event_store import SQLiteEventStore

FULL_DURATION = 86_400
SCOPE = "EMPTY_ARCHIVE_OFFLINE"
DATABASE = "offline-soak.sqlite"
CLOCK_NAME = "CLOCK_BOOTTIME" if hasattr(time, "CLOCK_BOOTTIME") else "MONOTONIC"
RESTARTABLE_LEASES = {"NOT_STARTED", "STOPPED", "EXPIRED"}
LEASE_STATES = RESTARTABLE_LEASES | {"ACTIVE", "CLOCK_CONFLICT", "CONFLICTED"}
TASK_STATES = {"IDLE", "PAUSED", "READY", "FAULTED", "BACKOFF"}


def _now():
    if CLOCK_NAME == "CLOCK_BOOTTIME":
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    return time.monotonic()


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _policy(interval):
    return SupervisorPolicy(interval_seconds=interval, lease_seconds=max(2.0, 3 * interval))


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def _write_report(workspace, report):
    with tempfile.NamedTemporaryFile(mode="w", dir=workspace, delete=False) as output:
        temporary_path = Path(output.name)
        try:
            output.write(_json(report) + "\n")
            output.flush()
            os.fsync(output.fileno())
            temporary_path.replace(workspace / "report.json")
            directory = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary_path.unlink(missing_ok=True)


def _initialize_archive(database):
    store = SQLiteEventStore(database)
    try:
        key = secrets.token_bytes(32)
        controls = LocalOperationalControls(store, operator_capability=key)
        for radar in RADARS:
            controls.apply(
                capability=key, event_id=f"soak-start-{radar}", action="START",
                actor="offline-soak", reason="isolated empty archive", radar=radar,
                at=datetime.now(timezone.utc),
            )
    finally:
        store.close()


def _runtime_snapshot(store):
    snapshot = {"lease": "CONFLICTED", "radars": {},
                "live_authorized": False, "execution_enabled": False}
    try:
        with store._bounded_lock_wait(seconds=0.25, deadline=time.monotonic() + 0.25):
            status = read_supervisor_status(store)
        if status["live_authorized"] is not False or status["execution_enabled"] is not False:
            raise ValueError("unexpected supervisor authorization")
        if status["status"] not in LEASE_STATES or not isinstance(status["radars"], dict):
            raise ValueError("invalid supervisor status")
        generation = status.get("generation")
        if status["status"] in {"ACTIVE", "STOPPED", "EXPIRED", "CLOCK_CONFLICT"} and (
            type(generation) is not int or generation < 1
        ):
            raise ValueError("invalid supervisor generation")
        radars = {}
        for radar, task in status["radars"].items():
            if radar not in RADARS or task["status"] not in TASK_STATES or any(
                type(task[key]) is not int or task[key] < 0 for key in ("cycles", "failures")
            ):
                raise ValueError("invalid radar progress")
            radars[radar] = {key: task[key] for key in (
                "status", "cycles", "failures", "last_activity",
            )}
        snapshot.update(
            lease=status["status"], generation=generation,
            last_heartbeat=status.get("last_heartbeat"), radars=radars,
        )
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        snapshot["probe_error"] = str(exc)
    return snapshot


def _worker(workspace, parent_pid, deadline, interval):
    # The controller always passes its newly created private workspace, never
    # an incoming database path or SMR_DB_PATH.
    database = workspace / DATABASE
    if not math.isfinite(deadline) or not 0 < deadline - _now() <= 172_800:
        raise ValueError("invalid offline soak deadline")
    if not math.isfinite(interval) or not 0.05 <= interval <= 60:
        raise ValueError("invalid offline soak interval")
    if (
        os.getppid() != parent_pid or not workspace.name.startswith("smr-soak-")
        or workspace.is_symlink() or workspace.stat().st_uid != os.getuid()
        or stat.S_IMODE(workspace.stat().st_mode) != 0o700
        or database.is_symlink() or not database.is_file() or database.stat().st_nlink != 1
        or database.stat().st_uid != os.getuid() or stat.S_IMODE(database.stat().st_mode) != 0o600
    ):
        raise ValueError("invalid offline soak workspace or parent process")
    stop = Event()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: stop.set())

    def watch_controller():
        while not stop.is_set():
            if os.getppid() != parent_pid or _now() >= deadline:
                stop.set()
                return
            stop.wait(min(0.25, max(0, deadline - _now())))

    Thread(target=watch_controller, daemon=True).start()
    store = SQLiteEventStore(database)
    try:
        supervisor = PersistentSupervisor(store, policy=_policy(interval))
        print(_json({"event": "worker_started", "at": _utc(), "pid": os.getpid()}), flush=True)
        cycles = supervisor.run(stop)
        print(_json({
            "event": "worker_stopped", "at": _utc(),
            "cycles": cycles, "generation": supervisor.generation,
        }), flush=True)
    finally:
        store.close()


def _spawn_worker(workspace, deadline, interval, output):
    return subprocess.Popen(
        [
            sys.executable, "-u", str(Path(__file__).resolve()), "_worker",
            str(workspace), str(os.getpid()), str(deadline), str(interval),
        ],
        stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _stop_worker(process):
    if process.poll() is not None:
        return False
    # The worker independently observes the same deadline. Give its supervisor
    # time to persist STOPPED and exit normally before sending SIGTERM.
    try:
        process.wait(timeout=3.0)
        return False
    except subprocess.TimeoutExpired:
        pass
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
        return True
    return False


def _read_integrity(store):
    try:
        with store._bounded_lock_wait(seconds=0.25, deadline=time.monotonic() + 0.25):
            return store.integrity_check()
    except sqlite3.Error as exc:
        return [f"{type(exc).__name__}: {exc}"]


def _monitor(workspace, store, journal, worker_log, stop, duration, interval, max_restarts):
    started = _now()
    monotonic_started = time.monotonic()
    cpu_started = time.process_time()
    deadline = started + duration
    policy = _policy(interval)
    poll = min(5.0, interval)
    stall_limit = policy.lease_seconds + interval
    last_written_progress = started - 30
    previous_cycles = dict.fromkeys(RADARS, 0)
    last_advance = dict.fromkeys(RADARS, started)
    maximum_gaps = dict.fromkeys(RADARS, 0.0)
    last_sample = started
    maximum_sample_gap = 0.0
    worker_exit_codes = []
    children_started = 0
    watchdog_stops = 0
    forced_stops = 0
    process = None
    outcome = "COMPLETED"
    failure = None

    def log(event, **fields):
        journal.write(_json({
            "event": event, "at": _utc(), "elapsed_seconds": _now() - started, **fields,
        }) + "\n")
        journal.flush()
        os.fsync(journal.fileno())

    started_at = _utc()
    log("started", duration_seconds=duration, interval_seconds=interval, scope=SCOPE)
    try:
        while not stop.is_set() and _now() < deadline:
            snapshot = _runtime_snapshot(store)
            # Retry only a read/probe error. A verified persisted integrity
            # conflict has no probe_error and must fence immediately.
            if snapshot["lease"] == "CONFLICTED" and "probe_error" in snapshot:
                stop.wait(min(0.1, max(0, deadline - _now())))
                snapshot = _runtime_snapshot(store)
            now = _now()
            maximum_sample_gap = max(maximum_sample_gap, now - last_sample)
            last_sample = now
            for radar, task in snapshot["radars"].items():
                cycles = task["cycles"]
                if cycles < previous_cycles[radar]:
                    raise ValueError(f"cycle counter regressed for {radar}")
                gap = now - last_advance[radar]
                maximum_gaps[radar] = max(maximum_gaps[radar], gap)
                if cycles > previous_cycles[radar]:
                    previous_cycles[radar] = cycles
                    last_advance[radar] = now
            if now - last_written_progress >= 30:
                log("sample", **snapshot)
                last_written_progress = now
            # Exhausted restart budget is terminal after the worker has exited.
            # Do not attempt to reacquire a lease or restart a fenced worker.
            if (process is not None and process.poll() is not None
                    and children_started > max_restarts):
                worker_exit_codes.append(process.returncode)
                log("worker_exit", pid=process.pid, code=process.returncode, expected=False)
                process = None
                raise RuntimeError("worker restart limit reached")
            if snapshot["lease"] in ("CLOCK_CONFLICT", "CONFLICTED"):
                detail = snapshot.get("probe_error", snapshot["lease"])
                log("unsafe_supervisor_state", lease=snapshot["lease"],
                    probe_error=snapshot.get("probe_error"),
                    worker_pid=process.pid if process is not None else None,
                    worker_exit_code=process.poll() if process is not None else None)
                raise ValueError(f"unsafe supervisor state: {detail}")
            if process is not None and process.poll() is None and any(
                now - last_advance[radar] >= stall_limit for radar in RADARS
            ):
                watchdog_stops += 1
                log("worker_stalled", pid=process.pid, **snapshot)
                forced_stops += _stop_worker(process)
            if process is not None and process.poll() is not None:
                worker_exit_codes.append(process.returncode)
                log("worker_exit", pid=process.pid, code=process.returncode, expected=False)
                process = None
                if children_started > max_restarts and _now() < deadline and not stop.is_set():
                    raise RuntimeError("worker restart limit reached")
            if process is None and snapshot["lease"] in RESTARTABLE_LEASES:
                if children_started > max_restarts:
                    raise RuntimeError("worker restart limit reached")
                if stop.is_set() or _now() >= deadline:
                    break
                process = _spawn_worker(workspace, deadline, interval, worker_log)
                children_started += 1
                last_advance = dict.fromkeys(RADARS, _now())
                log("worker_spawn", pid=process.pid, attempt=children_started)
            stop.wait(min(poll, max(0, deadline - _now())))
        if stop.is_set():
            outcome = "INTERRUPTED"
    except (OSError, RuntimeError, ValueError, sqlite3.Error, subprocess.TimeoutExpired) as exc:
        outcome = "FAILED"
        failure = str(exc)
        log("failure", error=failure)
    finally:
        finished_monitoring = _now()
        elapsed = finished_monitoring - started
        suspended_seconds = max(0.0, elapsed - (time.monotonic() - monotonic_started))
        maximum_sample_gap = max(maximum_sample_gap, finished_monitoring - last_sample)
        for radar in RADARS:
            maximum_gaps[radar] = max(
                maximum_gaps[radar], finished_monitoring - last_advance[radar]
            )
        if process is not None:
            try:
                forced_stop = _stop_worker(process)
                forced_stops += forced_stop
                worker_exit_codes.append(process.returncode)
                log("worker_exit", pid=process.pid, code=process.returncode, expected=True,
                    forced=forced_stop)
                if process.returncode != 0 and outcome == "COMPLETED":
                    raise RuntimeError("worker did not exit cleanly at completion")
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                outcome = "FAILED"
                failure = failure or str(exc)
                log("shutdown_failure", error=str(exc))

    final = _runtime_snapshot(store)
    integrity = _read_integrity(store)
    if outcome == "COMPLETED" and any(
        finished_monitoring - progress >= stall_limit for progress in last_advance.values()
    ):
        outcome = "FAILED"
        failure = "offline progress was interrupted before the target duration"
    if outcome == "COMPLETED" and (
        final["lease"] != "STOPPED" or integrity != ["ok"] or
        set(final["radars"]) != set(RADARS) or any(
            task["cycles"] < 1 or task["status"] != "READY" or task["failures"] != 0
            for task in final["radars"].values()
        )
    ):
        outcome = "FAILED"
        failure = "final offline supervisor state is incomplete or unhealthy"
    log("finished", outcome=outcome, **final)
    children_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "schema_version": 1, "scope": SCOPE, "outcome": outcome, "failure": failure,
        "started_at": started_at, "finished_at": _utc(), "clock": CLOCK_NAME,
        "clock_includes_device_suspend": CLOCK_NAME == "CLOCK_BOOTTIME",
        "estimated_suspend_seconds": suspended_seconds if CLOCK_NAME == "CLOCK_BOOTTIME" else None,
        "device_power_policy_changed": False,
        "elapsed_seconds": elapsed, "target_duration_seconds": duration,
        "interval_seconds": interval, "max_restarts": max_restarts,
        "target_24h_reached": outcome == "COMPLETED" and elapsed >= FULL_DURATION,
        "physical_android_verified": False, "autonomy_24h_verified": False,
        "platform": {"system": platform.system(), "release": platform.release(),
                     "machine": platform.machine()},
        "worker_restarts": max(0, children_started - 1), "worker_exit_codes": worker_exit_codes,
        "watchdog_stops": watchdog_stops, "forced_stops": forced_stops,
        "max_observed_gap_seconds": maximum_gaps,
        "max_monitoring_gap_seconds": maximum_sample_gap,
        "stall_limit_seconds": stall_limit, "supervisor": final,
        "resource_usage": {
            "controller_cpu_seconds": time.process_time() - cpu_started,
            "worker_cpu_seconds": children_usage.ru_utime + children_usage.ru_stime,
            "worker_peak_rss_kib": children_usage.ru_maxrss,
            "archive_bytes": sum(
                item.stat().st_size for item in workspace.glob(f"{DATABASE}*")
            ),
        },
        "sqlite_integrity": integrity,
        "artifacts": {"progress": "progress.jsonl", "worker": "worker.log", "sqlite": DATABASE},
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 5 and argv[0] == "_worker":
        _worker(Path(argv[1]), int(argv[2]), float(argv[3]), float(argv[4]))
        return 0

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path.home() / "smr-soak-results",
        help="parent directory for private artifacts in Termux app storage",
    )
    parser.add_argument("--duration-seconds", type=float, default=FULL_DURATION)
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    parser.add_argument("--max-restarts", type=int, default=5)
    args = parser.parse_args(argv)
    if not math.isfinite(args.duration_seconds) or not 0 < args.duration_seconds <= 172_800:
        parser.error("--duration-seconds must be positive and at most 172800")
    if not math.isfinite(args.interval_seconds) or not 0.05 <= args.interval_seconds <= 60:
        parser.error("--interval-seconds must be between 0.05 and 60")
    if not 0 <= args.max_restarts <= 20:
        parser.error("--max-restarts must be between 0 and 20")

    os.umask(0o077)
    stop = Event()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: stop.set())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="smr-soak-", dir=args.output_dir.resolve()))
    print(f"SMR offline soak: {workspace}", flush=True)
    _initialize_archive(workspace / DATABASE)
    store = SQLiteEventStore(workspace / DATABASE, read_only=True)
    try:
        with (workspace / "progress.jsonl").open("w") as journal, (
            workspace / "worker.log"
        ).open("ab", buffering=0) as worker_log:
            report = _monitor(
                workspace, store, journal, worker_log, stop, args.duration_seconds,
                args.interval_seconds, args.max_restarts,
            )
        _write_report(workspace, report)
    finally:
        store.close()
    print(f"{report['outcome']}: {workspace / 'report.json'}", flush=True)
    return {"COMPLETED": 0, "FAILED": 1, "INTERRUPTED": 130}[report["outcome"]]


if __name__ == "__main__":
    raise SystemExit(main())
