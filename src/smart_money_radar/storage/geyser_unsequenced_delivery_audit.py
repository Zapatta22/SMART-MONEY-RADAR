"""Rebuildable audit projection for RAW deliveries without transport sequence.

The projection is deliberately separate from the account timeline. It never
changes RAW events, deliveries, transport checkpoints, or transport anomalies.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from smart_money_radar.storage.collector_authority import collector_write, bind_projection


POLICY_ID = "geyser-unsequenced-delivery:v2"
PROJECTION_NAME = "geyser_unsequenced_delivery_audit"
PROJECTION_VERSION = 1


class SQLiteGeyserUnsequencedDeliveryAudit:
    """Classify each persisted delivery using only deterministic RAW evidence."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = str(database_path)
        self.last_rebuild_metrics: dict[str, object] = {}
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
                CREATE TABLE IF NOT EXISTS geyser_unsequenced_delivery_audit_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
            """)
            current_schema = connection.execute(
                "SELECT COALESCE(MAX(version), 0) "
                "FROM geyser_unsequenced_delivery_audit_schema_migrations"
            ).fetchone()[0]
            if current_schema > PROJECTION_VERSION:
                raise sqlite3.DatabaseError(
                    "Schema da auditoria Geyser é mais novo que esta versão do SMR"
                )
            if current_schema < 1:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO geyser_unsequenced_delivery_audit_schema_migrations "
                    "(version, applied_at) VALUES (?, ?)",
                    (1, datetime.now(timezone.utc).isoformat()),
                )
                connection.commit()

    def bind_collector(self, authority):
        return bind_projection(self,authority)

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
        """Rebuild atomically while keeping delivery-sized working sets in SQLite."""
        batch_size = 500
        with self._connect() as connection, collector_write(connection,getattr(self,"_collector_authority",None)):

            # Materialize only eligible witnesses in a connection-local SQLite
            # table. This replaces the Python-wide delivery list, conflict set,
            # anomaly set, and event-to-witness dictionary from the old rebuild.
            connection.execute("""
                CREATE TEMP TABLE eligible_geyser_audit_witnesses (
                    event_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    delivery_id INTEGER NOT NULL
                )
            """)
            connection.execute("""
                INSERT INTO eligible_geyser_audit_witnesses
                    (event_id, source_id, payload_sha256, delivery_id)
                SELECT d.event_id, d.source_id, e.payload_sha256, d.delivery_id
                FROM geyser_raw_deliveries d
                JOIN geyser_raw_events e ON e.event_id=d.event_id
                WHERE d.stream_sequence IS NOT NULL
                  AND d.event_id IS NOT NULL
                  AND d.conflict_id IS NULL
                  AND e.source_id=d.source_id
                  AND e.payload_sha256 IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM geyser_raw_conflicts c
                      WHERE c.event_id=d.event_id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM geyser_transport_anomalies a
                      WHERE a.source_id=d.source_id
                        AND a.stream_id=d.stream_id
                        AND a.stream_sequence=d.stream_sequence
                  )
            """)
            connection.execute("""
                CREATE INDEX temp.idx_eligible_geyser_audit_witness_key
                ON eligible_geyser_audit_witnesses
                    (event_id, source_id, payload_sha256, delivery_id)
            """)
            temp_page_count = connection.execute("PRAGMA temp.page_count").fetchone()[0]
            temp_page_size = connection.execute("PRAGMA temp.page_size").fetchone()[0]
            self.last_rebuild_metrics = {
                "temp_db_pages": temp_page_count,
                "temp_db_page_size_bytes": temp_page_size,
                "temp_db_allocated_bytes": temp_page_count * temp_page_size,
                "temp_store_pragma": connection.execute("PRAGMA temp_store").fetchone()[0],
                "sqlite_compile_options": [
                    row[0] for row in connection.execute("PRAGMA compile_options")
                    if row[0].startswith(("TEMP_STORE=", "DEFAULT_CACHE_SIZE="))
                ],
            }

            prior = connection.execute(
                "SELECT generation FROM geyser_unsequenced_delivery_audit_checkpoint "
                "WHERE projection_name=?", (PROJECTION_NAME,)
            ).fetchone()
            generation = (prior[0] if prior else 0) + 1
            counts = {
                "delivery_count": 0, "unsequenced_count": 0,
                "reconciled_count": 0, "unresolved_count": 0,
                "conflict_count": 0,
            }

            connection.execute("DELETE FROM geyser_unsequenced_delivery_audit")
            insert_sql = """
                INSERT INTO geyser_unsequenced_delivery_audit
                (generation,delivery_id,policy_id,classification,reason_code,event_id,
                 source_id,stream_id,stream_sequence,payload_sha256,witness_delivery_ids_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """
            cursor = connection.execute("""
                SELECT d.delivery_id,d.event_id,d.source_id,d.stream_id,
                       d.stream_sequence,d.conflict_id,e.source_id,e.payload_sha256,
                       EXISTS (
                           SELECT 1 FROM geyser_raw_conflicts c
                           WHERE c.event_id=d.event_id
                       ) AS has_raw_conflict,
                       EXISTS (
                           SELECT 1 FROM geyser_transport_anomalies a
                           WHERE a.source_id=d.source_id
                             AND a.stream_id=d.stream_id
                             AND a.stream_sequence=d.stream_sequence
                       ) AS has_transport_anomaly
                FROM geyser_raw_deliveries d
                LEFT JOIN geyser_raw_events e ON e.event_id=d.event_id
                ORDER BY d.delivery_id
            """)
            while True:
                source_rows = cursor.fetchmany(batch_size)
                if not source_rows:
                    break
                audit_rows = []
                for row in source_rows:
                    (delivery_id,event_id,source_id,stream_id,sequence,conflict_id,
                     event_source,payload_hash,has_raw_conflict,has_transport_anomaly) = row
                    counts["delivery_count"] += 1
                    if sequence is None:
                        counts["unsequenced_count"] += 1

                    if conflict_id is not None or event_id is None or event_source != source_id:
                        classification,reason = "IDENTITY_CONFLICT","raw_identity_or_source_conflict"
                        counts["conflict_count"] += 1
                    elif has_raw_conflict:
                        classification,reason = "IDENTITY_CONFLICT","event_identity_has_raw_conflict"
                        counts["conflict_count"] += 1
                    elif sequence is not None and has_transport_anomaly:
                        classification,reason = "SEQUENCE_ANOMALY","historical_transport_anomaly"
                    elif sequence is not None:
                        classification,reason = "SEQUENCED","transport_sequence_present"
                    else:
                        witness_json = connection.execute("""
                            SELECT '[' || group_concat(delivery_id, ',') || ']'
                            FROM (
                                SELECT delivery_id
                                FROM eligible_geyser_audit_witnesses
                                WHERE event_id=? AND source_id=? AND payload_sha256=?
                                ORDER BY delivery_id
                            )
                        """,(event_id,source_id,payload_hash)).fetchone()[0]
                        witnesses_json = witness_json if witness_json is not None else "[]"
                        if witnesses_json != "[]":
                            classification,reason = (
                                "UNSEQUENCED_RECONCILED",
                                "exact_sequenced_identity_and_hash_match",
                            )
                            counts["reconciled_count"] += 1
                        else:
                            classification,reason = (
                                "UNSEQUENCED_UNRESOLVED",
                                "no_eligible_sequenced_witness",
                            )
                            counts["unresolved_count"] += 1
                        audit_rows.append((
                            generation,delivery_id,POLICY_ID,classification,reason,event_id,
                            source_id,stream_id,sequence,payload_hash,witnesses_json,
                        ))
                        continue

                    audit_rows.append((
                        generation,delivery_id,POLICY_ID,classification,reason,event_id,
                        source_id,stream_id,sequence,payload_hash,"[]",
                    ))

                connection.executemany(insert_sql,audit_rows)

            completed_at = datetime.now(timezone.utc).isoformat()
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
                PROJECTION_NAME,PROJECTION_VERSION,POLICY_ID,generation,
                counts["delivery_count"],counts["unsequenced_count"],
                counts["reconciled_count"],counts["unresolved_count"],
                counts["conflict_count"],completed_at,
            ))
        return {"generation":generation, **counts}

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
