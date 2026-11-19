"""Reproducible synthetic benchmark for the Geyser unsequenced-delivery audit.

The fixture is inserted directly into the real SQLite schema in one transaction.
A separate worker process performs the rebuild so its RSS high-water mark excludes
fixture construction. No provider or network connection is used.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.storage.geyser_unsequenced_delivery_audit import (
    SQLiteGeyserUnsequencedDeliveryAudit,
)


class _BenchmarkAudit(SQLiteGeyserUnsequencedDeliveryAudit):
    """Keep TEMP mode overrides confined to this diagnostic benchmark."""

    def __init__(self, database_path: Path, temp_store: str | None) -> None:
        if temp_store not in (None, "FILE", "MEMORY"):
            raise ValueError("modo TEMP de benchmark inválido")
        self._benchmark_temp_store = temp_store
        super().__init__(database_path)

    @contextmanager
    def _connect(self):
        with super()._connect() as connection:
            if self._benchmark_temp_store is not None:
                connection.execute(
                    f"PRAGMA temp_store = {self._benchmark_temp_store}"
                )
            yield connection


def seed_database(database: Path, logical_events: int) -> None:
    raw = SQLiteGeyserRawStore(database)
    raw.close()
    now = "2026-01-01T00:00:00+00:00"
    with sqlite3.connect(database) as connection:
        events = []
        deliveries = []
        for index in range(logical_events):
            event_id = f"benchmark-event-{index:09d}"
            payload = f"benchmark-payload-{index:09d}".encode("ascii")
            digest = hashlib.sha256(payload).hexdigest()
            events.append((
                event_id, "benchmark-source", "account", "benchmark-v1",
                "normalized_json", payload, digest, now,
            ))
            deliveries.append((
                event_id, "benchmark-source", "unsequenced-stream", None,
                "unknown", now,
            ))
            deliveries.append((
                event_id, "benchmark-source", "sequenced-replay-stream", index,
                "replay", now,
            ))
        connection.executemany(
            """INSERT INTO geyser_raw_events
            (event_id,source_id,event_kind,schema_version,payload_encoding,
             payload_bytes,payload_sha256,first_received_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            events,
        )
        connection.executemany(
            """INSERT INTO geyser_raw_deliveries
            (event_id,source_id,stream_id,stream_sequence,delivery_kind,received_at)
            VALUES (?,?,?,?,?,?)""",
            deliveries,
        )


def process_memory_snapshot() -> dict:
    snapshot = {"vmrss_kib": None, "vmhwm_kib": None,
                "smaps_rss_kib": None, "smaps_pss_kib": None,
                "smaps_private_dirty_kib": None}
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith(("VmRSS:", "VmHWM:")):
                key, value = line.split(":", 1)
                snapshot["vmrss_kib" if key == "VmRSS" else "vmhwm_kib"] = int(value.strip().split()[0])
        smaps = Path("/proc/self/smaps_rollup").read_text().splitlines()
        fields = {"Rss:": "smaps_rss_kib", "Pss:": "smaps_pss_kib",
                  "Private_Dirty:": "smaps_private_dirty_kib"}
        for line in smaps:
            for prefix, key in fields.items():
                if line.startswith(prefix):
                    snapshot[key] = int(line.split()[1])
    except OSError:
        pass
    return snapshot


def run_rebuild_worker(database: Path, temp_store: str | None) -> dict:
    audit = _BenchmarkAudit(database, temp_store)
    before_memory = process_memory_snapshot()
    tracemalloc.start()
    started = time.perf_counter()
    summary = audit.rebuild()
    elapsed = time.perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    after_memory = process_memory_snapshot()
    # Use this process' own /proc high-water mark. getrusage.ru_maxrss can
    # retain the pre-fork parent's peak on Linux and contaminate this worker.
    # VmHWM covers the worker lifetime (imports/construction included), not rebuild alone.\n    rss_peak_kib = after_memory["vmhwm_kib"]
    rss_peak_mib = round(rss_peak_kib / 1024, 2) if rss_peak_kib is not None else None
    return {
        "summary": summary,
        "rebuild_seconds": round(elapsed, 6),
        "tracemalloc_peak_mib": round(peak_bytes / (1024 * 1024), 2),
        "process_rss_peak_mib": rss_peak_mib,\n        "rss_peak_scope": "worker_process_lifetime_including_imports_and_audit_construction",
        "memory_before_rebuild": before_memory,
        "memory_after_rebuild": after_memory,
        "temp_store_requested": temp_store or "DEFAULT",
        "temp_store_requested": temp_store or "DEFAULT",
        **audit.last_rebuild_metrics,
    }


def benchmark_size(logical_events: int, temp_store: str | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="smr-geyser-audit-bench-") as tmp:
        database = Path(tmp) / "benchmark.sqlite"
        seed_database(database, logical_events)

        # Isolate RSS high-water measurement from Python allocations used to seed
        # the synthetic fixture. The child process starts only after seeding ends.
        worker = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--worker-db", str(database),
             "--temp-store", temp_store or "DEFAULT"],
            check=True,
            capture_output=True,
            text=True,
        )
        measured = json.loads(worker.stdout)
        summary = measured.pop("summary")

        with sqlite3.connect(database) as connection:
            class_counts = dict(connection.execute(
                """SELECT classification, COUNT(*)
                   FROM geyser_unsequenced_delivery_audit
                   GROUP BY classification"""
            ).fetchall())
            raw_delivery_count = connection.execute(
                "SELECT COUNT(*) FROM geyser_raw_deliveries"
            ).fetchone()[0]
            raw_event_count = connection.execute(
                "SELECT COUNT(*) FROM geyser_raw_events"
            ).fetchone()[0]

        expected_deliveries = logical_events * 2
        if summary["delivery_count"] != expected_deliveries:
            raise AssertionError(f"delivery_count inesperado: {summary}")
        if summary["reconciled_count"] != logical_events:
            raise AssertionError(f"reconciled_count inesperado: {summary}")
        if class_counts.get("UNSEQUENCED_RECONCILED") != logical_events:
            raise AssertionError(f"classificação reconciled inesperada: {class_counts}")
        if class_counts.get("SEQUENCED") != logical_events:
            raise AssertionError(f"classificação sequenced inesperada: {class_counts}")
        if raw_delivery_count != expected_deliveries or raw_event_count != logical_events:
            raise AssertionError("contagens RAW foram alteradas ou fixture incompleta")

        return {
            "logical_events": logical_events,
            "deliveries": expected_deliveries,
            "rebuild_seconds": measured["rebuild_seconds"],
            "deliveries_per_second": round(
                expected_deliveries / measured["rebuild_seconds"], 2
            ) if measured["rebuild_seconds"] else None,
            "tracemalloc_peak_mib": measured["tracemalloc_peak_mib"],
            "process_rss_peak_mib": measured["process_rss_peak_mib"],
            "memory_before_rebuild": measured["memory_before_rebuild"],
            "memory_after_rebuild": measured["memory_after_rebuild"],
            "temp_store_requested": measured["temp_store_requested"],
            "temp_store_pragma": measured["temp_store_pragma"],
            "sqlite_compile_options": measured["sqlite_compile_options"],
            "temp_db_pages": measured["temp_db_pages"],
            "temp_db_page_size_bytes": measured["temp_db_page_size_bytes"],
            "temp_db_allocated_bytes": measured["temp_db_allocated_bytes"],
            "classification_counts": class_counts,
            "raw_events_after_rebuild": raw_event_count,
            "raw_deliveries_after_rebuild": raw_delivery_count,
            "integrity_check": SQLiteGeyserRawStore(database).integrity_check(),
        }


def benchmark_witness_fanout(witness_count: int, temp_store: str | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="smr-geyser-audit-fanout-") as tmp:
        database = Path(tmp) / "fanout.sqlite"
        raw = SQLiteGeyserRawStore(database)
        raw.close()
        now = "2026-01-01T00:00:00+00:00"
        event_id = "fanout-event"
        payload = b"one-logical-event-many-sequenced-deliveries"
        digest = hashlib.sha256(payload).hexdigest()
        with sqlite3.connect(database) as connection:
            connection.execute(
                """INSERT INTO geyser_raw_events
                (event_id,source_id,event_kind,schema_version,payload_encoding,
                 payload_bytes,payload_sha256,first_received_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (event_id,"fanout-source","account","benchmark-v1",
                 "normalized_json",payload,digest,now),
            )
            connection.executemany(
                """INSERT INTO geyser_raw_deliveries
                (event_id,source_id,stream_id,stream_sequence,delivery_kind,received_at)
                VALUES (?,?,?,?,?,?)""",
                [(event_id,"fanout-source","unsequenced",None,"unknown",now)]
                + [
                    (event_id,"fanout-source","fanout-replay",sequence,"replay",now)
                    for sequence in range(1,witness_count + 1)
                ],
            )

        worker = subprocess.run(
            [sys.executable,str(Path(__file__).resolve()),
             "--worker-db",str(database),
             "--temp-store",temp_store or "DEFAULT"],
            check=True,capture_output=True,text=True,
        )
        measured = json.loads(worker.stdout)
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                """SELECT witness_delivery_ids_json
                   FROM geyser_unsequenced_delivery_audit
                   WHERE classification='UNSEQUENCED_RECONCILED'"""
            ).fetchone()
            raw_count = connection.execute(
                "SELECT COUNT(*) FROM geyser_raw_deliveries"
            ).fetchone()[0]
        witness_ids = json.loads(row[0]) if row else []
        if len(witness_ids) != witness_count or witness_ids != sorted(witness_ids):
            raise AssertionError("lista de testemunhas incompleta ou fora de ordem")
        integrity = SQLiteGeyserRawStore(database).integrity_check()
        if integrity != ["ok"] or raw_count != witness_count + 1:
            raise AssertionError("integridade RAW/SQLite falhou no cenário fanout")
        return {
            "logical_events": 1,
            "deliveries": witness_count + 1,
            "witness_count": len(witness_ids),
            "rebuild_seconds": measured["rebuild_seconds"],
            "tracemalloc_peak_mib": measured["tracemalloc_peak_mib"],
            "process_rss_peak_mib": measured["process_rss_peak_mib"],
            "memory_before_rebuild": measured["memory_before_rebuild"],
            "memory_after_rebuild": measured["memory_after_rebuild"],
            "temp_store_requested": measured["temp_store_requested"],
            "temp_store_pragma": measured["temp_store_pragma"],
            "sqlite_compile_options": measured["sqlite_compile_options"],
            "temp_db_pages": measured["temp_db_pages"],
            "temp_db_page_size_bytes": measured["temp_db_page_size_bytes"],
            "temp_db_allocated_bytes": measured["temp_db_allocated_bytes"],
            "raw_deliveries_after_rebuild": raw_count,
            "integrity_check": integrity,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes", nargs="+", type=int,
        default=[1000, 10000, 50000, 100000],
        help="número de eventos lógicos; cada um gera duas deliveries",
    )
    parser.add_argument("--fanout-witnesses", type=int, default=10000)
    parser.add_argument("--temp-store", choices=("DEFAULT", "FILE", "MEMORY"), default="DEFAULT")
    parser.add_argument(
        "--worker-db", type=Path,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args.worker_db is not None:
        selected_store = None if args.temp_store == "DEFAULT" else args.temp_store
        print(json.dumps(run_rebuild_worker(args.worker_db, selected_store), sort_keys=True))
        return
    if not args.sizes or any(size <= 0 for size in args.sizes):
        parser.error("todos os tamanhos devem ser inteiros positivos")
    if args.fanout_witnesses <= 0:
        parser.error("--fanout-witnesses deve ser positivo")

    selected_store = None if args.temp_store == "DEFAULT" else args.temp_store
    results = [benchmark_size(size, selected_store) for size in args.sizes]
    fanout = benchmark_witness_fanout(args.fanout_witnesses, selected_store)
    mode_comparison = {
        mode: benchmark_size(100000, None if mode == "DEFAULT" else mode)
        for mode in ("DEFAULT", "FILE", "MEMORY")
    }
    print(json.dumps({
        "benchmark": "geyser_unsequenced_delivery_audit_rebuild",
        "fixture": "synthetic_sqlite_two_deliveries_per_event",
        "rss_method": "isolated_worker_process_proc_status_VmHWM_worker_lifetime_not_rebuild_only",
        "temp_storage_method": "sqlite_temp_page_count_times_page_size",
        "process_memory_method": "/proc/self/status and smaps_rollup on Linux",
        "high_cardinality_witness_fanout": fanout,
        "temp_store_mode_comparison_100k": mode_comparison,
        "results": results,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
