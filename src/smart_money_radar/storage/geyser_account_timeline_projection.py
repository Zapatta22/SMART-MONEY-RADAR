"""Rebuildable persistent account timeline and bank-lineage projection.

The immutable RAW event table remains authoritative. Rebuild replays the first
recorded delivery of each logical event in delivery order, then atomically
replaces derived timeline and bank-lineage tables. Arrival order is replay
order only; it is never used to declare a canonical fork.
"""
from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate
from smart_money_radar.data_sources.geyser_account_timeline import AccountUpdateTimeline
from smart_money_radar.data_sources.geyser_bank_lineage import (
    BankKey, NormalizedBlockMeta, NormalizedEntryUpdateParent, NormalizedSlotUpdate,
)
from smart_money_radar.data_sources.geyser_event_identity import derive_event_identity


PROJECTION_NAME = "geyser_account_timeline"
PROJECTION_VERSION = 1


def _u64(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**64:
        raise ValueError(f"{field} deve ser u64")
    return value


def _text(value, field, allow_none=False):
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve ser texto não vazio")
    return value


class SQLiteGeyserAccountTimelineProjection:
    """Rebuild account continuity and bank lineage from normalized RAW events."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("a timeline deve compartilhar arquivo SQLite persistente com o RAW store")
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS geyser_account_timeline_writes (
                    event_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    pubkey TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    write_version INTEGER NOT NULL,
                    bank_id INTEGER,
                    txn_signature TEXT,
                    continuity_epoch INTEGER NOT NULL,
                    baseline INTEGER NOT NULL CHECK(baseline IN (0,1)),
                    continuity_baseline INTEGER NOT NULL CHECK(continuity_baseline IN (0,1)),
                    bank_observation_status TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_geyser_timeline_account_order
                    ON geyser_account_timeline_writes(source_id,pubkey,slot,write_version);
                CREATE TABLE IF NOT EXISTS geyser_bank_lineage_nodes (
                    source_id TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    bank_id INTEGER NOT NULL,
                    parent_slot INTEGER,
                    blockhash TEXT,
                    parent_blockhash TEXT,
                    parent_source_id TEXT,
                    parent_bank_slot INTEGER,
                    parent_bank_id INTEGER,
                    statuses_json TEXT NOT NULL,
                    dead INTEGER NOT NULL CHECK(dead IN (0,1)),
                    invalidated INTEGER NOT NULL CHECK(invalidated IN (0,1)),
                    cleared_by_parent_update INTEGER NOT NULL CHECK(cleared_by_parent_update IN (0,1)),
                    parent_block_id_hex TEXT,
                    replaces_bank_slot INTEGER,
                    replaces_bank_id INTEGER,
                    PRIMARY KEY(source_id,slot,bank_id)
                );
                CREATE TABLE IF NOT EXISTS geyser_timeline_gaps (
                    generation INTEGER NOT NULL,
                    ordinal INTEGER NOT NULL,
                    stream_id TEXT NOT NULL,
                    expected_sequence INTEGER,
                    received_sequence INTEGER,
                    reason TEXT NOT NULL,
                    continuity_epoch INTEGER NOT NULL,
                    PRIMARY KEY(generation,ordinal)
                );
                CREATE TABLE IF NOT EXISTS geyser_timeline_conflicts (
                    generation INTEGER NOT NULL,
                    ordinal INTEGER NOT NULL,
                    conflict_kind TEXT NOT NULL,
                    source_id TEXT,
                    pubkey TEXT,
                    slot INTEGER,
                    write_version INTEGER,
                    reason TEXT NOT NULL,
                    detail TEXT,
                    PRIMARY KEY(generation,ordinal)
                );
                CREATE TABLE IF NOT EXISTS geyser_timeline_checkpoints (
                    projection_name TEXT PRIMARY KEY,
                    projection_version INTEGER NOT NULL,
                    generation INTEGER NOT NULL,
                    source_event_count INTEGER NOT NULL,
                    replayed_event_count INTEGER NOT NULL,
                    account_write_count INTEGER NOT NULL,
                    bank_count INTEGER NOT NULL,
                    skipped_count INTEGER NOT NULL,
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
    def _decode_event(row):
        event_id, source_id, event_kind, schema_version, payload_encoding, payload_bytes, stream_id, sequence = row
        if payload_encoding != "normalized_json":
            return None
        if sequence is None:
            return None
        envelope = json.loads(payload_bytes.decode("utf-8"))
        if (
            not isinstance(envelope, dict)
            or envelope.get("event_kind") != event_kind
            or envelope.get("source_id") != source_id
            or envelope.get("schema_version") != schema_version
            or not isinstance(envelope.get("payload"), dict)
        ):
            raise ValueError(f"envelope RAW inválido: {event_id}")
        p = envelope["payload"]
        sequence = _u64(sequence, "stream_sequence")
        stream_id = _text(stream_id, "stream_id")
        if event_kind == "account":
            data64 = p.get("data_base64")
            if not isinstance(data64, str):
                raise ValueError(f"data_base64 ausente: {event_id}")
            try:
                data = base64.b64decode(data64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError(f"data_base64 inválido: {event_id}") from exc
            return NormalizedAccountUpdate(
                pubkey=_text(p.get("pubkey"), "pubkey"),
                slot=_u64(p.get("slot"), "slot"),
                write_version=_u64(p.get("write_version"), "write_version"),
                txn_signature=_text(p.get("txn_signature"), "txn_signature", True),
                lamports=_u64(p.get("lamports"), "lamports"),
                owner=_text(p.get("owner"), "owner"),
                executable=p.get("executable"),
                rent_epoch=_u64(p.get("rent_epoch"), "rent_epoch"),
                data=data, stream_id=stream_id, stream_sequence=sequence,
                source=source_id, bank_id=None if p.get("bank_id") is None else _u64(p["bank_id"], "bank_id"),
                is_startup=p.get("is_startup"),
            )
        if event_kind == "slot":
            return NormalizedSlotUpdate(
                source_id, stream_id, sequence, _u64(p.get("slot"), "slot"),
                None if p.get("parent_slot") is None else _u64(p["parent_slot"], "parent_slot"),
                _text(p.get("status"), "status"),
                None if p.get("bank_id") is None else _u64(p["bank_id"], "bank_id"),
                _text(p.get("dead_error"), "dead_error", True),
            )
        if event_kind == "block_meta":
            return NormalizedBlockMeta(
                source_id, stream_id, sequence, _u64(p.get("slot"), "slot"),
                _u64(p.get("bank_id"), "bank_id"), _text(p.get("blockhash"), "blockhash"),
                _u64(p.get("parent_slot"), "parent_slot"),
                _text(p.get("parent_blockhash"), "parent_blockhash"),
            )
        if event_kind == "entry_update_parent":
            parent_hex = p.get("parent_block_id_hex")
            if not isinstance(parent_hex, str):
                raise ValueError(f"parent_block_id_hex ausente: {event_id}")
            try:
                parent_bytes = bytes.fromhex(parent_hex)
            except ValueError as exc:
                raise ValueError(f"parent_block_id_hex inválido: {event_id}") from exc
            return NormalizedEntryUpdateParent(
                source_id, stream_id, sequence, _u64(p.get("slot"), "slot"),
                _u64(p.get("cleared_bank_id"), "cleared_bank_id"),
                _u64(p.get("parent_slot"), "parent_slot"), parent_bytes,
            )
        return None

    def rebuild(self) -> dict[str, int | str]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("""
                SELECT e.event_id,e.source_id,e.event_kind,e.schema_version,
                       e.payload_encoding,e.payload_bytes,d.stream_id,d.stream_sequence
                FROM geyser_raw_events e
                JOIN geyser_raw_deliveries d ON d.delivery_id=(
                    SELECT MIN(d2.delivery_id) FROM geyser_raw_deliveries d2
                    WHERE d2.event_id=e.event_id
                )
                ORDER BY d.delivery_id,e.event_id
            """).fetchall()
            source_count = connection.execute(
                "SELECT COUNT(*) FROM geyser_raw_events"
            ).fetchone()[0]
            timeline = AccountUpdateTimeline()
            replayed = 0
            skipped = 0
            for row in rows:
                event = self._decode_event(row)
                if event is None:
                    skipped += 1
                    continue
                replayed += 1
                if isinstance(event, NormalizedAccountUpdate):
                    timeline.add(event)
                elif isinstance(event, NormalizedSlotUpdate):
                    timeline.add_slot_update(event)
                elif isinstance(event, NormalizedBlockMeta):
                    timeline.add_block_meta(event)
                elif isinstance(event, NormalizedEntryUpdateParent):
                    timeline.add_entry_update_parent(event)

            prior = connection.execute(
                "SELECT generation FROM geyser_timeline_checkpoints WHERE projection_name=?",
                (PROJECTION_NAME,),
            ).fetchone()
            generation = (prior[0] if prior else 0) + 1
            account_rows = []
            for record in timeline.timeline_records():
                update = record.update
                event_id = self._event_id_for(update, rows)
                account_rows.append((
                    event_id, update.source, update.pubkey, update.slot,
                    update.write_version, update.bank_id, update.txn_signature,
                    record.continuity_epoch, int(record.baseline),
                    int(record.continuity_baseline),
                    timeline.bank_lineage_tracker.account_bank_status(update),
                ))
            # Account event IDs are resolved from the stable logical identity; no transport fields enter it.
            connection.execute("DELETE FROM geyser_account_timeline_writes")
            connection.executemany("""
                INSERT INTO geyser_account_timeline_writes
                (event_id,source_id,pubkey,slot,write_version,bank_id,txn_signature,
                 continuity_epoch,baseline,continuity_baseline,bank_observation_status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, account_rows)

            tracker = timeline.bank_lineage_tracker
            bank_rows = []
            for node in tracker.banks:
                parent = node.parent_key
                replaces = node.replaces_bank
                bank_rows.append((
                    node.key.source_id,node.key.slot,node.key.bank_id,node.parent_slot,
                    node.blockhash,node.parent_blockhash,
                    parent.source_id if parent else None,parent.slot if parent else None,
                    parent.bank_id if parent else None,
                    json.dumps(sorted(node.statuses),separators=(",",":")),
                    int(node.dead),int(node.invalidated),int(node.cleared_by_parent_update),
                    node.parent_block_id.hex() if node.parent_block_id is not None else None,
                    replaces.slot if replaces else None,replaces.bank_id if replaces else None,
                ))
            connection.execute("DELETE FROM geyser_bank_lineage_nodes")
            connection.executemany("""
                INSERT INTO geyser_bank_lineage_nodes
                (source_id,slot,bank_id,parent_slot,blockhash,parent_blockhash,
                 parent_source_id,parent_bank_slot,parent_bank_id,statuses_json,dead,
                 invalidated,cleared_by_parent_update,parent_block_id_hex,
                 replaces_bank_slot,replaces_bank_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, bank_rows)

            connection.execute("DELETE FROM geyser_timeline_gaps")
            connection.executemany("""
                INSERT INTO geyser_timeline_gaps
                (generation,ordinal,stream_id,expected_sequence,received_sequence,reason,continuity_epoch)
                VALUES (?,?,?,?,?,?,?)
            """, [
                (generation,i,g.stream_id,g.expected_sequence,g.received_sequence,g.reason,g.continuity_epoch)
                for i,g in enumerate(timeline.gaps)
            ])
            conflicts = []
            for c in timeline.conflicts:
                conflicts.append(("account",None,c.pubkey,c.slot,c.write_version,c.reason,None))
            for c in tracker.conflicts:
                key = c.key
                conflicts.append(("bank",key.source_id if key else None,None,
                                  key.slot if key else None,None,c.reason,c.detail))
            connection.execute("DELETE FROM geyser_timeline_conflicts")
            connection.executemany("""
                INSERT INTO geyser_timeline_conflicts
                (generation,ordinal,conflict_kind,source_id,pubkey,slot,write_version,reason,detail)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, [
                (generation,i,kind,source,pubkey,slot,write_version,reason,detail)
                for i,(kind,source,pubkey,slot,write_version,reason,detail) in enumerate(conflicts)
            ])
            completed_at = datetime.now(timezone.utc).isoformat()
            connection.execute("""
                INSERT INTO geyser_timeline_checkpoints
                (projection_name,projection_version,generation,source_event_count,
                 replayed_event_count,account_write_count,bank_count,skipped_count,completed_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(projection_name) DO UPDATE SET
                 projection_version=excluded.projection_version,generation=excluded.generation,
                 source_event_count=excluded.source_event_count,
                 replayed_event_count=excluded.replayed_event_count,
                 account_write_count=excluded.account_write_count,bank_count=excluded.bank_count,
                 skipped_count=excluded.skipped_count,completed_at=excluded.completed_at
            """, (PROJECTION_NAME,PROJECTION_VERSION,generation,source_count,replayed,
                  len(account_rows),len(bank_rows),skipped,completed_at))
            connection.commit()
        return {"generation":generation,"source_event_count":source_count,
                "replayed_event_count":replayed,"account_write_count":len(account_rows),
                "bank_count":len(bank_rows),"skipped_count":skipped,"completed_at":completed_at}

    @staticmethod
    def _event_id_for(update, rows):
        # Recompute the versioned logical identity, including account state bytes.
        for row in rows:
            if row[1] != update.source or row[2] != "account" or row[4] != "normalized_json":
                continue
            identity = derive_event_identity(update, schema_version=row[3])
            if identity.event_id == row[0]:
                return row[0]
        raise ValueError("não foi possível associar escrita à identidade RAW")

    def get_checkpoint(self):
        with self._connect() as connection:
            row=connection.execute("""
                SELECT projection_name,projection_version,generation,source_event_count,
                       replayed_event_count,account_write_count,bank_count,skipped_count,completed_at
                FROM geyser_timeline_checkpoints WHERE projection_name=?
            """,(PROJECTION_NAME,)).fetchone()
        if row is None:
            return None
        return dict(zip(("projection_name","projection_version","generation","source_event_count",
                         "replayed_event_count","account_write_count","bank_count","skipped_count",
                         "completed_at"),row))

    def list_account_writes(self, pubkey: str | None = None):
        sql="SELECT event_id,source_id,pubkey,slot,write_version,bank_id,txn_signature,continuity_epoch,baseline,continuity_baseline,bank_observation_status FROM geyser_account_timeline_writes"
        params=()
        if pubkey is not None:
            sql+=" WHERE pubkey=?"; params=(pubkey,)
        sql+=" ORDER BY source_id,pubkey,slot,write_version,event_id"
        with self._connect() as connection:
            rows=connection.execute(sql,params).fetchall()
        names=("event_id","source_id","pubkey","slot","write_version","bank_id","txn_signature",
               "continuity_epoch","baseline","continuity_baseline","bank_observation_status")
        return [dict(zip(names,row)) for row in rows]

    def list_banks(self):
        with self._connect() as connection:
            rows=connection.execute("""
                SELECT source_id,slot,bank_id,parent_slot,blockhash,parent_blockhash,
                       parent_source_id,parent_bank_slot,parent_bank_id,statuses_json,dead,
                       invalidated,cleared_by_parent_update,parent_block_id_hex,
                       replaces_bank_slot,replaces_bank_id
                FROM geyser_bank_lineage_nodes ORDER BY source_id,slot,bank_id
            """).fetchall()
        names=("source_id","slot","bank_id","parent_slot","blockhash","parent_blockhash",
               "parent_source_id","parent_bank_slot","parent_bank_id","statuses_json","dead",
               "invalidated","cleared_by_parent_update","parent_block_id_hex",
               "replaces_bank_slot","replaces_bank_id")
        return [dict(zip(names,row)) for row in rows]
