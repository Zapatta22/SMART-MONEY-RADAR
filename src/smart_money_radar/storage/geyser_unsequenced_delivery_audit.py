"""Rebuildable audit projection for RAW deliveries without transport sequence.

The projection is deliberately separate from the account timeline. It never
changes RAW events, deliveries, transport checkpoints, or transport anomalies.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3


POLICY_ID = "geyser-unsequenced-delivery:v1"
PROJECTION_NAME = "geyser_unsequenced_delivery_audit"
PROJECTION_VERSION = 1


class SQLiteGeyserUnsequencedDeliveryAudit:
    """Classify each persisted delivery using only deterministic RAW evidence."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("a auditoria deve compartilhar o arquivo SQLite persistente do RAW store")
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS geyser_unsequenced_delivery_audit (
                    generation INTEGER NOT NULL,
                    delivery_id INTEGER PRIMARY KEY,
                    policy_id TEXT NOT NULL,
                    classification TEXT NOT NULL CHECK(classification IN (
                        'SEQUENCED','UNSEQUENCED_UNRESOLVED',
                        'UNSEQUENCED_RECONCILED','IDENTITY_CONFLICT',
                        'SEQUENCE_ANOMALY'
                    )),
                    reason_code TEXT NOT NULL,
                    event_id TEXT,
                    source_id TEXT NOT NULL,
                    stream_id TEXT NOT NULL,
                    stream_sequence INTEGER,
                    payload_sha256 TEXT,
                    witness_delivery_ids_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_geyser_unseq_audit_classification
                    ON geyser_unsequenced_delivery_audit(classification, delivery_id);
                CREATE INDEX IF NOT EXISTS idx_geyser_unseq_audit_event
                    ON geyser_unsequenced_delivery_audit(event_id, delivery_id);
                CREATE TABLE IF NOT EXISTS geyser_unsequenced_delivery_audit_checkpoint (
                    projection_name TEXT PRIMARY KEY,
                    projection_version INTEGER NOT NULL,
                    policy_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    delivery_count INTEGER NOT NULL,
                    unsequenced_count INTEGER NOT NULL,
                    reconciled_count INTEGER NOT NULL,
                    unresolved_count INTEGER NOT NULL,
                    conflict_count INTEGER NOT NULL,
                    completed_at TEXT NOT NULL
                );
            """)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        try:
            connection.execute("PRAGMA busy_timeout = 30000")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            yield connection
        finally:
            connection.close()

    def rebuild(self) -> dict[str, int | str]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("""
                SELECT d.delivery_id,d.event_id,d.source_id,d.stream_id,
                       d.stream_sequence,d.conflict_id,e.source_id,e.payload_sha256
                FROM geyser_raw_deliveries d
                LEFT JOIN geyser_raw_events e ON e.event_id=d.event_id
                ORDER BY d.delivery_id
            """).fetchall()

            raw_conflict_event_ids = {
                row[0] for row in connection.execute(
                    "SELECT DISTINCT event_id FROM geyser_raw_conflicts"
                ).fetchall()
            }
            open_anomalies = {
                row[0] for row in connection.execute(
                    "SELECT delivery_id FROM geyser_transport_anomalies WHERE status='OPEN'"
                ).fetchall()
            }

            sequenced_witnesses: dict[tuple[str, str, str], list[int]] = {}
            for row in rows:
                delivery_id,event_id,source_id,stream_id,sequence,conflict_id,event_source,payload_hash = row
                if (
                    sequence is not None and event_id is not None and conflict_id is None
                    and event_source == source_id and event_id not in raw_conflict_event_ids
                    and delivery_id not in open_anomalies and payload_hash is not None
                ):
                    key = (event_id, source_id, payload_hash)
                    sequenced_witnesses.setdefault(key, []).append(delivery_id)

            prior = connection.execute(
                "SELECT generation FROM geyser_unsequenced_delivery_audit_checkpoint "
                "WHERE projection_name=?", (PROJECTION_NAME,)
            ).fetchone()
            generation = (prior[0] if prior else 0) + 1
            audit_rows = []
            counts = {
                "unsequenced_count": 0, "reconciled_count": 0,
                "unresolved_count": 0, "conflict_count": 0,
            }

            for row in rows:
                delivery_id,event_id,source_id,stream_id,sequence,conflict_id,event_source,payload_hash = row
                witnesses: list[int] = []
                if conflict_id is not None or event_id is None or event_source != source_id:
                    classification,reason = "IDENTITY_CONFLICT","raw_identity_or_source_conflict"
                    counts["conflict_count"] += 1
                elif event_id in raw_conflict_event_ids:
                    classification,reason = "IDENTITY_CONFLICT","event_identity_has_raw_conflict"
                    counts["conflict_count"] += 1
                elif sequence is not None and delivery_id in open_anomalies:
                    classification,reason = "SEQUENCE_ANOMALY","open_transport_anomaly"
                elif sequence is not None:
                    classification,reason = "SEQUENCED","transport_sequence_present"
                else:
                    counts["unsequenced_count"] += 1
                    witnesses = sequenced_witnesses.get(
                        (event_id,source_id,payload_hash), []
                    )
                    if witnesses:
                        classification,reason = "UNSEQUENCED_RECONCILED","exact_sequenced_identity_and_hash_match"
                        counts["reconciled_count"] += 1
                    else:
                        classification,reason = "UNSEQUENCED_UNRESOLVED","no_eligible_sequenced_witness"
                        counts["unresolved_count"] += 1
                audit_rows.append((
                    generation,delivery_id,POLICY_ID,classification,reason,event_id,
                    source_id,stream_id,sequence,payload_hash,
                    json.dumps(witnesses,separators=(",",":")),
                ))

            connection.execute("DELETE FROM geyser_unsequenced_delivery_audit")
            connection.executemany("""
                INSERT INTO geyser_unsequenced_delivery_audit
                (generation,delivery_id,policy_id,classification,reason_code,event_id,
                 source_id,stream_id,stream_sequence,payload_sha256,witness_delivery_ids_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, audit_rows)
            completed_at = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat()
            connection.execute("""
                INSERT INTO geyser_unsequenced_delivery_audit_checkpoint
                (projection_name,projection_version,policy_id,generation,delivery_count,
                 unsequenced_count,reconciled_count,unresolved_count,conflict_count,completed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(projection_name) DO UPDATE SET
                 projection_version=excluded.projection_version,policy_id=excluded.policy_id,
                 generation=excluded.generation,delivery_count=excluded.delivery_count,
                 unsequenced_count=excluded.unsequenced_count,
                 reconciled_count=excluded.reconciled_count,
                 unresolved_count=excluded.unresolved_count,
                 conflict_count=excluded.conflict_count,completed_at=excluded.completed_at
            """, (
                PROJECTION_NAME,PROJECTION_VERSION,POLICY_ID,generation,len(rows),
                counts["unsequenced_count"],counts["reconciled_count"],
                counts["unresolved_count"],counts["conflict_count"],completed_at,
            ))
            connection.commit()
        return {
            "generation":generation,"delivery_count":len(rows),
            **counts,
        }

    def list_deliveries(self, classification: str | None = None) -> list[dict]:
        with self._connect() as connection:
            sql = """
                SELECT generation,delivery_id,policy_id,classification,reason_code,event_id,
                       source_id,stream_id,stream_sequence,payload_sha256,witness_delivery_ids_json
                FROM geyser_unsequenced_delivery_audit
            """
            params: tuple = ()
            if classification is not None:
                sql += " WHERE classification=?"
                params = (classification,)
            sql += " ORDER BY delivery_id"
            rows = connection.execute(sql,params).fetchall()
        keys = (
            "generation","delivery_id","policy_id","classification","reason_code",
            "event_id","source_id","stream_id","stream_sequence","payload_sha256",
            "witness_delivery_ids_json",
        )
        result = []
        for row in rows:
            item = dict(zip(keys,row))
            item["witness_delivery_ids"] = json.loads(item.pop("witness_delivery_ids_json"))
            result.append(item)
        return result

    def get_checkpoint(self) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("""
                SELECT projection_name,projection_version,policy_id,generation,
                       delivery_count,unsequenced_count,reconciled_count,
                       unresolved_count,conflict_count,completed_at
                FROM geyser_unsequenced_delivery_audit_checkpoint
                WHERE projection_name=?
            """,(PROJECTION_NAME,)).fetchone()
        if row is None:
            return None
        return dict(zip((
            "projection_name","projection_version","policy_id","generation",
            "delivery_count","unsequenced_count","reconciled_count",
            "unresolved_count","conflict_count","completed_at",
        ),row))
