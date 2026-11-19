"""Reproducible synthetic benchmark for the Geyser unsequenced-delivery audit.

The fixture is inserted directly into the real SQLite schema in one transaction.
This isolates projection rebuild cost from per-event ingestion/transport overhead.
Each logical event has two deliveries: one without sequence and one sequenced
witness in another stream. No provider or network connection is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
import time
import tracemalloc
from pathlib import Path

from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.storage.geyser_unsequenced_delivery_audit import (
    SQLiteGeyserUnsequencedDeliveryAudit,
)


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
            # The unsequenced delivery appears first; its witness is in a
            # separate stream and must remain a reference, not sequence transfer.
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


def benchmark_size(logical_events: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="smr-geyser-audit-bench-") as tmp:
        database = Path(tmp) / "benchmark.sqlite"
        seed_database(database, logical_events)
        audit = SQLiteGeyserUnsequencedDeliveryAudit(database)

        tracemalloc.start()
        started = time.perf_counter()
        summary = audit.rebuild()
        elapsed = time.perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

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
            "rebuild_seconds": round(elapsed, 6),
            "deliveries_per_second": round(expected_deliveries / elapsed, 2)
                if elapsed else None,
            "tracemalloc_peak_mib": round(peak_bytes / (1024 * 1024), 2),
            "classification_counts": class_counts,
            "raw_events_after_rebuild": raw_event_count,
            "raw_deliveries_after_rebuild": raw_delivery_count,
            "integrity_check": SQLiteGeyserRawStore(database).integrity_check(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes", nargs="+", type=int,
        default=[1000, 10000, 50000, 100000],
        help="número de eventos lógicos; cada um gera duas deliveries",
    )
    args = parser.parse_args()
    if not args.sizes or any(size <= 0 for size in args.sizes):
        parser.error("todos os tamanhos devem ser inteiros positivos")

    results = [benchmark_size(size) for size in args.sizes]
    print(json.dumps({
        "benchmark": "geyser_unsequenced_delivery_audit_rebuild",
        "fixture": "synthetic_sqlite_two_deliveries_per_event",
        "results": results,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
