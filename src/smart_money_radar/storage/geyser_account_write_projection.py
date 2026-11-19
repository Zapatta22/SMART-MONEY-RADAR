"""Rebuildable SQLite projection of normalized Geyser account writes.

RAW events remain immutable and authoritative. This first projection version
uses a full, atomic rebuild instead of an incremental cursor: that avoids
missing late-arriving/backfilled RAW events whose logical event IDs sort
before a previously processed cursor. A rebuild holds a SQLite write
transaction while reading the RAW snapshot and replacing the projection.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import binascii
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


PROJECTION_NAME = "geyser_account_writes"
PROJECTION_VERSION = 1


def _required_text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve ser texto não vazio")
    return value


def _u64(value, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**64:
        raise ValueError(f"{field} deve ser u64")
    return value


def _optional_text(value, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


class SQLiteGeyserAccountWriteProjection:
    """Materialize account writes from normalized_json RAW records."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("a projeção deve compartilhar um arquivo SQLite persistente com o RAW store")
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS geyser_account_writes (
                    event_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    pubkey TEXT NOT NULL,
                    slot INTEGER NOT NULL CHECK(slot >= 0),
                    write_version INTEGER NOT NULL CHECK(write_version >= 0),
                    bank_id INTEGER CHECK(bank_id IS NULL OR bank_id >= 0),
                    is_startup INTEGER NOT NULL CHECK(is_startup IN (0,1)),
                    txn_signature TEXT,
                    lamports TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    executable INTEGER NOT NULL CHECK(executable IN (0,1)),
                    rent_epoch TEXT NOT NULL,
                    data_base64 TEXT NOT NULL,
                    data_length INTEGER NOT NULL CHECK(data_length >= 0),
                    data_sha256 TEXT NOT NULL CHECK(length(data_sha256) = 64),
                    schema_version TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_geyser_account_writes_order
                    ON geyser_account_writes(source_id, pubkey, slot, write_version);
                CREATE INDEX IF NOT EXISTS idx_geyser_account_writes_signature
                    ON geyser_account_writes(txn_signature);
                CREATE TABLE IF NOT EXISTS geyser_projection_checkpoints (
                    projection_name TEXT PRIMARY KEY,
                    projection_version INTEGER NOT NULL,
                    generation INTEGER NOT NULL CHECK(generation >= 0),
                    source_event_count INTEGER NOT NULL CHECK(source_event_count >= 0),
                    projected_count INTEGER NOT NULL CHECK(projected_count >= 0),
                    skipped_count INTEGER NOT NULL CHECK(skipped_count >= 0),
                    source_max_event_id TEXT,
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

    @staticmethod
    def _decode_account(row):
        event_id, source_id, schema_version, payload_bytes = row
        try:
            envelope = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"RAW account {event_id} não contém JSON normalizado válido") from exc
        if (
            not isinstance(envelope, dict)
            or envelope.get("event_kind") != "account"
            or envelope.get("source_id") != source_id
            or envelope.get("schema_version") != schema_version
            or not isinstance(envelope.get("payload"), dict)
        ):
            raise ValueError(f"envelope RAW account inválido: {event_id}")
        payload = envelope["payload"]
        pubkey = _required_text(payload.get("pubkey"), "pubkey")
        slot = _u64(payload.get("slot"), "slot")
        write_version = _u64(payload.get("write_version"), "write_version")
        lamports = _u64(payload.get("lamports"), "lamports")
        rent_epoch = _u64(payload.get("rent_epoch"), "rent_epoch")
        owner = _required_text(payload.get("owner"), "owner")
        txn_signature = _optional_text(payload.get("txn_signature"), "txn_signature")
        bank_id = payload.get("bank_id")
        if bank_id is not None:
            bank_id = _u64(bank_id, "bank_id")
        executable = payload.get("executable")
        is_startup = payload.get("is_startup")
        if not isinstance(executable, bool) or not isinstance(is_startup, bool):
            raise ValueError(f"flags booleanas inválidas no RAW account {event_id}")
        encoded = payload.get("data_base64")
        if not isinstance(encoded, str):
            raise ValueError(f"data_base64 ausente no RAW account {event_id}")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"data_base64 inválido no RAW account {event_id}") from exc
        return (
            event_id, source_id, pubkey, slot, write_version, bank_id,
            int(is_startup), txn_signature, str(lamports), owner,
            int(executable), str(rent_epoch), encoded, len(data),
            hashlib.sha256(data).hexdigest(), schema_version,
        )

    def rebuild(self) -> dict[str, int | str]:
        """Atomically replace this projection from the complete RAW snapshot.

        Non-account events and account events not encoded as normalized_json
        are counted as skipped. Malformed normalized account records abort the
        transaction, preserving the previous complete projection/checkpoint.
        """
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT event_id, source_id, schema_version, payload_bytes "
                "FROM geyser_raw_events WHERE event_kind='account' "
                "AND payload_encoding='normalized_json' ORDER BY event_id"
            ).fetchall()
            source_count = connection.execute(
                "SELECT COUNT(*) FROM geyser_raw_events"
            ).fetchone()[0]
            skipped_count = source_count - len(rows)
            materialized = [self._decode_account(row) for row in rows]
            prior = connection.execute(
                "SELECT generation FROM geyser_projection_checkpoints WHERE projection_name=?",
                (PROJECTION_NAME,),
            ).fetchone()
            generation = (prior[0] if prior else 0) + 1
            connection.execute("DELETE FROM geyser_account_writes")
            connection.executemany(
                "INSERT INTO geyser_account_writes "
                "(event_id,source_id,pubkey,slot,write_version,bank_id,is_startup,"
                "txn_signature,lamports,owner,executable,rent_epoch,data_base64,"
                "data_length,data_sha256,schema_version) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                materialized,
            )
            completed_at = datetime.now(timezone.utc).isoformat()
            max_event_id = max((row[0] for row in rows), default=None)
            connection.execute(
                "INSERT INTO geyser_projection_checkpoints "
                "(projection_name,projection_version,generation,source_event_count,"
                "projected_count,skipped_count,source_max_event_id,completed_at) "
                "VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(projection_name) DO UPDATE SET "
                "projection_version=excluded.projection_version,"
                "generation=excluded.generation,"
                "source_event_count=excluded.source_event_count,"
                "projected_count=excluded.projected_count,"
                "skipped_count=excluded.skipped_count,"
                "source_max_event_id=excluded.source_max_event_id,"
                "completed_at=excluded.completed_at",
                (PROJECTION_NAME, PROJECTION_VERSION, generation, source_count,
                 len(materialized), skipped_count, max_event_id, completed_at),
            )
            connection.commit()
        return {
            "generation": generation,
            "source_event_count": source_count,
            "projected_count": len(materialized),
            "skipped_count": skipped_count,
            "completed_at": completed_at,
        }

    def get_checkpoint(self) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT projection_name,projection_version,generation,source_event_count,"
                "projected_count,skipped_count,source_max_event_id,completed_at "
                "FROM geyser_projection_checkpoints WHERE projection_name=?",
                (PROJECTION_NAME,),
            ).fetchone()
        if row is None:
            return None
        return dict(zip(
            ("projection_name","projection_version","generation","source_event_count",
             "projected_count","skipped_count","source_max_event_id","completed_at"),
            row,
        ))

    def list_writes(self, *, pubkey: str | None = None) -> list[dict]:
        query = (
            "SELECT event_id,source_id,pubkey,slot,write_version,bank_id,is_startup,"
            "txn_signature,lamports,owner,executable,rent_epoch,data_base64,"
            "data_length,data_sha256,schema_version FROM geyser_account_writes"
        )
        params: tuple = ()
        if pubkey is not None:
            query += " WHERE pubkey=?"
            params = (pubkey,)
        query += " ORDER BY source_id,pubkey,slot,write_version,event_id"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        names = (
            "event_id","source_id","pubkey","slot","write_version","bank_id","is_startup",
            "txn_signature","lamports","owner","executable","rent_epoch","data_base64",
            "data_length","data_sha256","schema_version",
        )
        return [dict(zip(names, row)) for row in rows]
