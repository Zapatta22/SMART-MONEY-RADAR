"""Dedicated SQLite persistence for immutable Geyser RAW events and deliveries.

Logical events and exact transport envelopes have independent storage and
continuity. This offline store does not connect to Yellowstone.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3


_EVENT_KINDS = {"account", "slot", "block_meta", "entry_update_parent"}
_ENCODINGS = {"protobuf_wire", "protobuf_decoded", "normalized_json"}
_DELIVERY_KINDS = {"live", "replay", "backfill", "unknown"}


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve ser texto não vazio")
    return value


def _sequence(value: int | None, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} deve ser inteiro não negativo ou None")
    return value


def _frame_sequence(value: int) -> int:
    sequence = _sequence(value, "stream_sequence")
    if sequence is None or sequence > (1 << 63) - 1:
        raise ValueError("stream_sequence fora do intervalo inteiro do SQLite")
    return sequence


@dataclass(frozen=True)
class WireFrameReceipt:
    frame_id: int
    payload_sha256: str
    status: str
    contiguous_sequence: int
    last_seen_sequence: int
    tainted: bool

    @property
    def interrupted(self) -> bool:
        return self.tainted or self.contiguous_sequence != self.last_seen_sequence


@dataclass(frozen=True)
class RawEventInput:
    """Exact bytes captured at the declared boundary and stable source identity."""

    event_id: str
    source_id: str
    event_kind: str
    schema_version: str
    payload_encoding: str
    payload_bytes: bytes


@dataclass(frozen=True)
class RawDeliveryInput:
    """One observed delivery; transport identity is deliberately not event identity."""

    stream_id: str
    stream_sequence: int | None
    delivery_kind: str = "unknown"
    received_at: str | None = None


@dataclass(frozen=True)
class RawIngestResult:
    status: str
    event_id: str | None
    delivery_id: int
    payload_sha256: str
    conflict_id: int | None = None


class SQLiteGeyserRawStore:
    """Persist immutable event content separately from every transport delivery.

    A content identity reused with different bytes is retained as a conflict;
    the original RAW row is never overwritten. Every attempted delivery is
    recorded, including conflicting deliveries.
    """

    SCHEMA_VERSION = 3

    def __init__(self, database_path: Path | str, *, read_only: bool = False) -> None:
        self.database_path = str(database_path)
        self._read_only = read_only
        self._memory_connection: sqlite3.Connection | None = None
        if read_only:
            if self.database_path == ":memory:":
                raise ValueError("a leitura do journal exige um arquivo SQLite")
            with self._connection() as connection:
                row = connection.execute("SELECT MAX(version) FROM geyser_schema_migrations").fetchone()
                if row[0] != self.SCHEMA_VERSION:
                    raise ValueError("schema SQLite incompatível com a leitura do journal Yellowstone")
        elif self.database_path == ":memory:":
            self._memory_connection = sqlite3.connect(":memory:")
            self._initialize(self._memory_connection)
        else:
            path = Path(database_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as connection:
                self._initialize(connection)

    def _connect(self) -> sqlite3.Connection:
        if self._read_only:
            uri = Path(self.database_path).resolve().as_uri() + "?mode=ro"
            return sqlite3.connect(uri, uri=True, timeout=15.0)
        if self._memory_connection is not None:
            return self._memory_connection
        connection = sqlite3.connect(self.database_path, timeout=15.0)
        connection.execute("PRAGMA busy_timeout = 15000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            if connection is not self._memory_connection:
                connection.close()

    def _initialize(self, connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS geyser_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)
            current = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM geyser_schema_migrations"
            ).fetchone()[0]
            if current > self.SCHEMA_VERSION:
                raise sqlite3.DatabaseError("Schema Geyser mais novo que esta versão do SMR")
            if current < 1:
                connection.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE geyser_raw_events (
                        event_id TEXT PRIMARY KEY,
                        source_id TEXT NOT NULL,
                        event_kind TEXT NOT NULL CHECK(event_kind IN
                            ('account','slot','block_meta','entry_update_parent')),
                        schema_version TEXT NOT NULL,
                        payload_encoding TEXT NOT NULL CHECK(payload_encoding IN
                            ('protobuf_wire','protobuf_decoded','normalized_json')),
                        payload_bytes BLOB NOT NULL,
                        payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
                        first_received_at TEXT NOT NULL
                    );
                    CREATE INDEX idx_geyser_raw_source_kind
                        ON geyser_raw_events(source_id, event_kind, first_received_at);
                    CREATE TABLE geyser_raw_deliveries (
                        delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT REFERENCES geyser_raw_events(event_id),
                        source_id TEXT NOT NULL,
                        stream_id TEXT NOT NULL,
                        stream_sequence INTEGER CHECK(stream_sequence IS NULL OR stream_sequence >= 0),
                        delivery_kind TEXT NOT NULL CHECK(delivery_kind IN
                            ('live','replay','backfill','unknown')),
                        received_at TEXT NOT NULL,
                        conflict_id INTEGER
                    );
                    CREATE INDEX idx_geyser_deliveries_stream_sequence
                        ON geyser_raw_deliveries(source_id, stream_id, stream_sequence);
                    CREATE INDEX idx_geyser_deliveries_event
                        ON geyser_raw_deliveries(event_id, delivery_id);
                    CREATE TABLE geyser_raw_conflicts (
                        conflict_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL,
                        source_id TEXT NOT NULL,
                        existing_sha256 TEXT NOT NULL,
                        incoming_sha256 TEXT NOT NULL,
                        incoming_payload BLOB NOT NULL,
                        detected_at TEXT NOT NULL,
                        reason TEXT NOT NULL
                    );
                    CREATE INDEX idx_geyser_raw_conflicts_event
                        ON geyser_raw_conflicts(event_id, conflict_id);
                    INSERT INTO geyser_schema_migrations(version, applied_at)
                        VALUES (1, CURRENT_TIMESTAMP);
                    COMMIT;
                """)
            if current < 2:
                connection.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE geyser_transport_checkpoints (
                        source_id TEXT NOT NULL,
                        stream_id TEXT NOT NULL,
                        initial_sequence INTEGER NOT NULL CHECK(initial_sequence >= 0),
                        contiguous_sequence INTEGER NOT NULL,
                        last_seen_sequence INTEGER NOT NULL,
                        baseline_kind TEXT NOT NULL CHECK(baseline_kind IN
                            ('adapter_declared','first_observed_unverified')),
                        interrupted INTEGER NOT NULL DEFAULT 0 CHECK(interrupted IN (0,1)),
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(source_id, stream_id)
                    );
                    CREATE TABLE geyser_transport_gaps (
                        gap_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_id TEXT NOT NULL,
                        stream_id TEXT NOT NULL,
                        missing_from INTEGER NOT NULL CHECK(missing_from >= 0),
                        missing_to INTEGER NOT NULL CHECK(missing_to >= missing_from),
                        status TEXT NOT NULL CHECK(status IN ('OPEN','RESOLVED','SUPERSEDED')),
                        detected_at TEXT NOT NULL,
                        resolved_at TEXT
                    );
                    CREATE INDEX idx_geyser_transport_gaps_open
                        ON geyser_transport_gaps(source_id, stream_id, status, missing_from);
                    CREATE TABLE geyser_transport_anomalies (
                        anomaly_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_id TEXT NOT NULL,
                        stream_id TEXT NOT NULL,
                        stream_sequence INTEGER NOT NULL CHECK(stream_sequence >= 0),
                        delivery_id INTEGER NOT NULL REFERENCES geyser_raw_deliveries(delivery_id),
                        reason TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('OPEN','RESOLVED')),
                        detected_at TEXT NOT NULL,
                        resolved_at TEXT,
                        resolution_note TEXT
                    );
                    CREATE INDEX idx_geyser_transport_anomalies_open
                        ON geyser_transport_anomalies(source_id, stream_id, status, stream_sequence);
                    INSERT INTO geyser_schema_migrations(version, applied_at)
                        VALUES (2, CURRENT_TIMESTAMP);
                    COMMIT;
                """)

            if current < 3:
                connection.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS geyser_frame_streams (
                        source_id TEXT NOT NULL,
                        stream_id TEXT NOT NULL,
                        ordering_domain_id TEXT NOT NULL,
                        initial_sequence INTEGER NOT NULL,
                        contiguous_sequence INTEGER NOT NULL,
                        last_seen_sequence INTEGER NOT NULL,
                        tainted INTEGER NOT NULL DEFAULT 0 CHECK(tainted IN (0,1)),
                        PRIMARY KEY(source_id, stream_id),
                        UNIQUE(source_id, ordering_domain_id)
                    );
                    CREATE TABLE IF NOT EXISTS geyser_wire_frames (
                        frame_id INTEGER PRIMARY KEY,
                        source_id TEXT NOT NULL,
                        stream_id TEXT NOT NULL,
                        stream_sequence INTEGER NOT NULL CHECK(stream_sequence >= 0),
                        frame_kind TEXT,
                        payload_bytes BLOB NOT NULL,
                        payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
                        status TEXT NOT NULL CHECK(status IN
                            ('accepted','duplicate','collision','invalid','before_baseline')),
                        received_at TEXT NOT NULL,
                        FOREIGN KEY(source_id, stream_id)
                            REFERENCES geyser_frame_streams(source_id, stream_id)
                    );
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_geyser_wire_accepted
                        ON geyser_wire_frames(source_id, stream_id, stream_sequence)
                        WHERE status = 'accepted';
                    INSERT OR IGNORE INTO geyser_schema_migrations(version, applied_at)
                        VALUES (3, CURRENT_TIMESTAMP);
                    COMMIT;
                """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_geyser_wire_stream_frame
                ON geyser_wire_frames(source_id, stream_id, frame_id)
            """)

    def register_frame_stream(
        self, source_id: str, stream_id: str, ordering_domain_id: str, initial_sequence: int
    ) -> None:
        """Bind a transport connection to a fresh ordering domain before capture."""
        source_id = _text(source_id, "source_id")
        stream_id = _text(stream_id, "stream_id")
        ordering_domain_id = _text(ordering_domain_id, "ordering_domain_id")
        initial = _frame_sequence(initial_sequence)
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """SELECT stream_id, ordering_domain_id, initial_sequence
                   FROM geyser_frame_streams WHERE source_id = ?
                   AND (stream_id = ? OR ordering_domain_id = ?)""",
                (source_id, stream_id, ordering_domain_id),
            ).fetchall()
            if rows:
                if rows != [(stream_id, ordering_domain_id, initial)]:
                    raise ValueError("stream ou domínio já associado a outro baseline")
                return
            connection.execute(
                """INSERT INTO geyser_frame_streams
                   (source_id, stream_id, ordering_domain_id, initial_sequence,
                    contiguous_sequence, last_seen_sequence) VALUES (?, ?, ?, ?, ?, ?)""",
                (source_id, stream_id, ordering_domain_id, initial, initial - 1, initial - 1),
            )

    def require_frame_stream(self, source_id: str, stream_id: str, ordering_domain_id: str) -> None:
        """Check that the journal already contains the requested connection."""
        with self._connection() as connection:
            row = connection.execute(
                """SELECT 1 FROM geyser_frame_streams
                   WHERE source_id = ? AND stream_id = ? AND ordering_domain_id = ?""",
                (source_id, stream_id, ordering_domain_id),
            ).fetchone()
        if row is None:
            raise ValueError("stream e domínio desconhecidos")

    def append_wire_frame(
        self, *, source_id: str, stream_id: str, ordering_domain_id: str,
        stream_sequence: int, payload: bytes, frame_kind: str | None,
    ) -> WireFrameReceipt:
        """Archive a delivery and atomically update its transport continuity."""
        sequence = _frame_sequence(stream_sequence)
        if not isinstance(payload, bytes):
            raise TypeError("payload deve ser bytes")
        if frame_kind is not None:
            _text(frame_kind, "frame_kind")
        digest = hashlib.sha256(payload).hexdigest()
        coordinate = (source_id, stream_id, sequence)
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            stream = connection.execute(
                """SELECT initial_sequence, contiguous_sequence, last_seen_sequence, tainted
                   FROM geyser_frame_streams
                   WHERE source_id = ? AND stream_id = ? AND ordering_domain_id = ?""",
                (source_id, stream_id, ordering_domain_id),
            ).fetchone()
            if stream is None:
                raise ValueError("stream e domínio precisam ser registrados antes da captura")
            initial, contiguous, last_seen, tainted = stream
            prior = connection.execute(
                """SELECT payload_bytes, payload_sha256, frame_kind FROM geyser_wire_frames
                   WHERE source_id = ? AND stream_id = ? AND stream_sequence = ?
                   AND status = 'accepted'""",
                coordinate,
            ).fetchone()
            if sequence < initial:
                status = "before_baseline"
            elif frame_kind is None:
                status = "invalid"
            elif prior is None:
                status = "accepted"
            elif prior == (payload, digest, frame_kind):
                status = "duplicate"
            else:
                status = "collision"
            delivery = connection.execute(
                """INSERT INTO geyser_wire_frames
                   (source_id, stream_id, stream_sequence, payload_bytes, payload_sha256,
                    frame_kind, status, received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (*coordinate, payload, digest, frame_kind, status,
                 datetime.now(timezone.utc).isoformat()),
            )
            if status == "accepted" and sequence == contiguous + 1:
                for (candidate,) in connection.execute(
                    """SELECT stream_sequence FROM geyser_wire_frames
                       WHERE source_id = ? AND stream_id = ? AND stream_sequence >= ?
                       AND status = 'accepted' ORDER BY stream_sequence""",
                    coordinate,
                ):
                    if candidate != contiguous + 1:
                        break
                    contiguous = candidate
            last_seen = max(last_seen, sequence)
            tainted = bool(tainted or status in {"collision", "invalid", "before_baseline"})
            connection.execute(
                """UPDATE geyser_frame_streams SET contiguous_sequence = ?,
                   last_seen_sequence = ?, tainted = ? WHERE source_id = ? AND stream_id = ?""",
                (contiguous, last_seen, int(tainted), source_id, stream_id),
            )
            return WireFrameReceipt(delivery.lastrowid, digest, status, contiguous, last_seen, tainted)

    def get_wire_frame(self, frame_id: int) -> bytes | None:
        """Read exact persisted bytes and verify their digest before returning them."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_bytes, payload_sha256 FROM geyser_wire_frames WHERE frame_id = ?",
                (frame_id,),
            ).fetchone()
        if row is None:
            return None
        payload, digest = row
        if not isinstance(payload, bytes) or hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("SHA-256 do frame persistido diverge")
        return payload

    def iter_wire_frames(
        self, source_id: str, stream_id: str, ordering_domain_id: str,
    ) -> Iterator[tuple[int, bytes]]:
        """Replay one uninterrupted domain from a consistent read snapshot."""
        with self._connection() as connection, connection:
            connection.execute("BEGIN")
            stream = connection.execute(
                """SELECT initial_sequence, contiguous_sequence, last_seen_sequence, tainted
                   FROM geyser_frame_streams
                   WHERE source_id = ? AND stream_id = ? AND ordering_domain_id = ?""",
                (source_id, stream_id, ordering_domain_id),
            ).fetchone()
            if stream is None:
                raise ValueError("stream e domínio desconhecidos")
            initial, contiguous, last_seen, tainted = stream
            if tainted or contiguous != last_seen:
                raise ValueError("stream interrompido ou com anomalia histórica")
            rows = connection.execute(
                """SELECT stream_sequence, payload_bytes, payload_sha256
                   FROM geyser_wire_frames WHERE source_id = ? AND stream_id = ?
                   AND status = 'accepted' ORDER BY stream_sequence""",
                (source_id, stream_id),
            )
            expected = initial
            for sequence, payload, digest in rows:
                if (sequence != expected or sequence > contiguous or not isinstance(payload, bytes)
                        or hashlib.sha256(payload).hexdigest() != digest):
                    raise ValueError("integridade dos frames persistidos diverge")
                yield sequence, payload
                expected += 1
            if expected != contiguous + 1:
                raise ValueError("sequência persistida está incompleta")

    def register_stream(
        self, source_id: str, stream_id: str, initial_sequence: int
    ) -> dict:
        """Declare the first expected sequence before ingesting a new stream."""
        source_id = _text(source_id, "source_id")
        stream_id = _text(stream_id, "stream_id")
        initial_sequence = _sequence(initial_sequence, "initial_sequence")
        if initial_sequence is None:
            raise ValueError("initial_sequence é obrigatório")
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            with connection:
                existing = connection.execute(
                    "SELECT initial_sequence, baseline_kind FROM geyser_transport_checkpoints "
                    "WHERE source_id = ? AND stream_id = ?", (source_id, stream_id)
                ).fetchone()
                if existing is not None:
                    if existing[1] == "first_observed_unverified":
                        raise ValueError("não é possível declarar baseline após ingestão")
                    if existing[0] != initial_sequence:
                        raise ValueError("stream já possui baseline incompatível")
                else:
                    deliveries = connection.execute(
                        "SELECT COUNT(*) FROM geyser_raw_deliveries "
                        "WHERE source_id = ? AND stream_id = ?", (source_id, stream_id)
                    ).fetchone()[0]
                    if deliveries:
                        raise ValueError("não é possível declarar baseline após ingestão")
                    connection.execute(
                        "INSERT INTO geyser_transport_checkpoints "
                        "(source_id, stream_id, initial_sequence, contiguous_sequence, "
                        "last_seen_sequence, baseline_kind, interrupted, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, 'adapter_declared', 0, ?)",
                        (source_id, stream_id, initial_sequence, initial_sequence - 1,
                         initial_sequence - 1, now),
                    )
        return self.get_transport_checkpoint(source_id, stream_id)

    def _record_transport_sequence(
        self, connection: sqlite3.Connection, *, source_id: str, stream_id: str,
        sequence: int | None, delivery_id: int, event_id: str | None, received_at: str,
    ) -> None:
        if sequence is None:
            return
        checkpoint = connection.execute(
            "SELECT initial_sequence, contiguous_sequence, last_seen_sequence, baseline_kind "
            "FROM geyser_transport_checkpoints WHERE source_id = ? AND stream_id = ?",
            (source_id, stream_id),
        ).fetchone()
        if checkpoint is None:
            connection.execute(
                "INSERT INTO geyser_transport_checkpoints "
                "(source_id, stream_id, initial_sequence, contiguous_sequence, "
                "last_seen_sequence, baseline_kind, interrupted, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'first_observed_unverified', 0, ?)",
                (source_id, stream_id, sequence, sequence - 1, sequence - 1, received_at),
            )
            initial_sequence = sequence
        else:
            initial_sequence = checkpoint[0]

        if sequence < initial_sequence:
            self._record_transport_anomaly(
                connection, source_id, stream_id, sequence, delivery_id,
                "sequence_before_declared_baseline", received_at,
            )
        else:
            prior_ids = {
                row[0] for row in connection.execute(
                    "SELECT DISTINCT event_id FROM geyser_raw_deliveries "
                    "WHERE source_id = ? AND stream_id = ? AND stream_sequence = ? "
                    "AND delivery_id != ?",
                    (source_id, stream_id, sequence, delivery_id),
                ).fetchall()
            }
            if event_id is None:
                self._record_transport_anomaly(
                    connection, source_id, stream_id, sequence, delivery_id,
                    "raw_identity_conflict", received_at,
                )
            elif prior_ids and (None in prior_ids or any(value != event_id for value in prior_ids)):
                self._record_transport_anomaly(
                    connection, source_id, stream_id, sequence, delivery_id,
                    "sequence_reused_for_different_event", received_at,
                )

        rows = connection.execute(
            "SELECT DISTINCT stream_sequence FROM geyser_raw_deliveries "
            "WHERE source_id = ? AND stream_id = ? AND stream_sequence IS NOT NULL "
            "AND stream_sequence >= ? ORDER BY stream_sequence",
            (source_id, stream_id, initial_sequence),
        ).fetchall()
        seen = [int(row[0]) for row in rows]
        last_seen = max(seen) if seen else initial_sequence - 1
        contiguous = initial_sequence - 1
        missing_ranges = []
        cursor = initial_sequence
        blocked_by_gap = False
        for value in seen:
            if value < cursor:
                continue
            if value > cursor:
                missing_ranges.append((cursor, value - 1))
                blocked_by_gap = True
            elif not blocked_by_gap:
                contiguous = value
            cursor = value + 1

        open_rows = connection.execute(
            "SELECT gap_id, missing_from, missing_to FROM geyser_transport_gaps "
            "WHERE source_id = ? AND stream_id = ? AND status = 'OPEN'",
            (source_id, stream_id),
        ).fetchall()
        current_ranges = set(missing_ranges)
        old_ranges = {(row[1], row[2]) for row in open_rows}
        for gap_id, start, end in open_rows:
            if (start, end) not in current_ranges:
                status = "RESOLVED" if not missing_ranges else "SUPERSEDED"
                connection.execute(
                    "UPDATE geyser_transport_gaps SET status = ?, resolved_at = ? "
                    "WHERE gap_id = ?", (status, received_at, gap_id)
                )
        for start, end in missing_ranges:
            if (start, end) not in old_ranges:
                connection.execute(
                    "INSERT INTO geyser_transport_gaps "
                    "(source_id, stream_id, missing_from, missing_to, status, detected_at) "
                    "VALUES (?, ?, ?, ?, 'OPEN', ?)",
                    (source_id, stream_id, start, end, received_at),
                )

        # A resolved anomaly is administratively closed, not proof that its
        # historical sequence is trustworthy. Keep the stream tainted until a
        # separate evidence-backed repair procedure exists.
        historical_anomalies = connection.execute(
            "SELECT COUNT(*) FROM geyser_transport_anomalies "
            "WHERE source_id = ? AND stream_id = ?",
            (source_id, stream_id),
        ).fetchone()[0]
        interrupted = bool(missing_ranges or historical_anomalies)
        connection.execute(
            "UPDATE geyser_transport_checkpoints SET contiguous_sequence = ?, "
            "last_seen_sequence = ?, interrupted = ?, updated_at = ? "
            "WHERE source_id = ? AND stream_id = ?",
            (contiguous, last_seen, int(interrupted), received_at, source_id, stream_id),
        )

    @staticmethod
    def _record_transport_anomaly(
        connection: sqlite3.Connection, source_id: str, stream_id: str,
        sequence: int, delivery_id: int, reason: str, received_at: str,
    ) -> None:
        exists = connection.execute(
            "SELECT 1 FROM geyser_transport_anomalies WHERE source_id = ? AND stream_id = ? "
            "AND stream_sequence = ? AND reason = ? AND status = 'OPEN'",
            (source_id, stream_id, sequence, reason),
        ).fetchone()
        if exists is None:
            connection.execute(
                "INSERT INTO geyser_transport_anomalies "
                "(source_id, stream_id, stream_sequence, delivery_id, reason, status, detected_at) "
                "VALUES (?, ?, ?, ?, ?, 'OPEN', ?)",
                (source_id, stream_id, sequence, delivery_id, reason, received_at),
            )

    def get_transport_checkpoint(self, source_id: str, stream_id: str) -> dict | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT source_id, stream_id, initial_sequence, contiguous_sequence, "
                "last_seen_sequence, baseline_kind, interrupted, updated_at "
                "FROM geyser_transport_checkpoints WHERE source_id = ? AND stream_id = ?",
                (source_id, stream_id),
            ).fetchone()
        if row is None:
            return None
        keys = ("source_id", "stream_id", "initial_sequence", "contiguous_sequence",
                "last_seen_sequence", "baseline_kind", "interrupted", "updated_at")
        result = dict(zip(keys, row))
        result["interrupted"] = bool(result["interrupted"])
        return result

    def list_transport_gaps(
        self, source_id: str, stream_id: str, *, status: str | None = None
    ) -> list[dict]:
        with self._connection() as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT gap_id, missing_from, missing_to, status, detected_at, resolved_at "
                    "FROM geyser_transport_gaps WHERE source_id = ? AND stream_id = ? "
                    "ORDER BY gap_id", (source_id, stream_id)
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT gap_id, missing_from, missing_to, status, detected_at, resolved_at "
                    "FROM geyser_transport_gaps WHERE source_id = ? AND stream_id = ? "
                    "AND status = ? ORDER BY gap_id", (source_id, stream_id, status)
                ).fetchall()
        keys = ("gap_id", "missing_from", "missing_to", "status", "detected_at", "resolved_at")
        return [dict(zip(keys, row)) for row in rows]

    def list_transport_anomalies(
        self, source_id: str, stream_id: str, *, status: str | None = None
    ) -> list[dict]:
        with self._connection() as connection:
            sql = (
                "SELECT anomaly_id, stream_sequence, delivery_id, reason, status, "
                "detected_at, resolved_at, resolution_note FROM geyser_transport_anomalies "
                "WHERE source_id = ? AND stream_id = ?"
            )
            params: tuple = (source_id, stream_id)
            if status is not None:
                sql += " AND status = ?"
                params += (status,)
            rows = connection.execute(sql + " ORDER BY anomaly_id", params).fetchall()
        keys = ("anomaly_id", "stream_sequence", "delivery_id", "reason", "status",
                "detected_at", "resolved_at", "resolution_note")
        return [dict(zip(keys, row)) for row in rows]

    def resolve_transport_anomaly(self, anomaly_id: int, resolution_note: str) -> None:
        if isinstance(anomaly_id, bool) or not isinstance(anomaly_id, int) or anomaly_id <= 0:
            raise ValueError("anomaly_id deve ser inteiro positivo")
        resolution_note = _text(resolution_note, "resolution_note")
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            with connection:
                row = connection.execute(
                    "SELECT source_id, stream_id, status FROM geyser_transport_anomalies "
                    "WHERE anomaly_id = ?", (anomaly_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(anomaly_id)
                if row[2] == "OPEN":
                    connection.execute(
                        "UPDATE geyser_transport_anomalies SET status = 'RESOLVED', "
                        "resolved_at = ?, resolution_note = ? WHERE anomaly_id = ?",
                        (now, resolution_note, anomaly_id),
                    )
                    # RESOLVED closes the administrative record only. Historical
                    # sequence taint remains until an evidence-backed repair exists.
                    historical = connection.execute(
                        "SELECT COUNT(*) FROM geyser_transport_anomalies "
                        "WHERE source_id = ? AND stream_id = ?",
                        (row[0], row[1]),
                    ).fetchone()[0]
                    gaps = connection.execute(
                        "SELECT COUNT(*) FROM geyser_transport_gaps "
                        "WHERE source_id = ? AND stream_id = ? AND status = 'OPEN'",
                        (row[0], row[1]),
                    ).fetchone()[0]
                    connection.execute(
                        "UPDATE geyser_transport_checkpoints SET interrupted = ? "
                        "WHERE source_id = ? AND stream_id = ?",
                        (int(bool(historical or gaps)), row[0], row[1]),
                    )

    @staticmethod
    def _validate_event(event: RawEventInput) -> None:
        _text(event.event_id, "event_id")
        _text(event.source_id, "source_id")
        _text(event.schema_version, "schema_version")
        if event.event_kind not in _EVENT_KINDS:
            raise ValueError("event_kind não suportado")
        if event.payload_encoding not in _ENCODINGS:
            raise ValueError("payload_encoding não suportado")
        if not isinstance(event.payload_bytes, bytes):
            raise TypeError("payload_bytes deve ser bytes")

    def ingest(self, event: RawEventInput, delivery: RawDeliveryInput) -> RawIngestResult:
        self._validate_event(event)
        stream_id = _text(delivery.stream_id, "stream_id")
        sequence = _sequence(delivery.stream_sequence, "stream_sequence")
        if delivery.delivery_kind not in _DELIVERY_KINDS:
            raise ValueError("delivery_kind não suportado")
        received_at = delivery.received_at or datetime.now(timezone.utc).isoformat()
        _text(received_at, "received_at")
        digest = hashlib.sha256(event.payload_bytes).hexdigest()

        with self._connection() as connection:
            with connection:
                existing = connection.execute(
                    "SELECT source_id, event_kind, schema_version, payload_encoding, "
                    "payload_bytes, payload_sha256 FROM geyser_raw_events WHERE event_id = ?",
                    (event.event_id,),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO geyser_raw_events(event_id, source_id, event_kind, "
                        "schema_version, payload_encoding, payload_bytes, payload_sha256, "
                        "first_received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (event.event_id, event.source_id, event.event_kind,
                         event.schema_version, event.payload_encoding, event.payload_bytes,
                         digest, received_at),
                    )
                    cursor = connection.execute(
                        "INSERT INTO geyser_raw_deliveries(event_id, source_id, stream_id, "
                        "stream_sequence, delivery_kind, received_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (event.event_id, event.source_id, stream_id, sequence,
                         delivery.delivery_kind, received_at),
                    )
                    self._record_transport_sequence(
                        connection, source_id=event.source_id, stream_id=stream_id,
                        sequence=sequence, delivery_id=cursor.lastrowid,
                        event_id=event.event_id, received_at=received_at,
                    )
                    return RawIngestResult("inserted", event.event_id, cursor.lastrowid, digest)

                same_content = (
                    existing[0] == event.source_id
                    and existing[1] == event.event_kind
                    and existing[2] == event.schema_version
                    and existing[3] == event.payload_encoding
                    and existing[4] == event.payload_bytes
                    and existing[5] == digest
                )
                if same_content:
                    cursor = connection.execute(
                        "INSERT INTO geyser_raw_deliveries(event_id, source_id, stream_id, "
                        "stream_sequence, delivery_kind, received_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (event.event_id, event.source_id, stream_id, sequence,
                         delivery.delivery_kind, received_at),
                    )
                    self._record_transport_sequence(
                        connection, source_id=event.source_id, stream_id=stream_id,
                        sequence=sequence, delivery_id=cursor.lastrowid,
                        event_id=event.event_id, received_at=received_at,
                    )
                    return RawIngestResult("duplicate", event.event_id, cursor.lastrowid, digest)

                conflict = connection.execute(
                    "INSERT INTO geyser_raw_conflicts(event_id, source_id, existing_sha256, "
                    "incoming_sha256, incoming_payload, detected_at, reason) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (event.event_id, event.source_id, existing[5], digest,
                     event.payload_bytes, received_at,
                     "event_id reutilizado com identidade, encoding, schema ou bytes incompatíveis"),
                )
                conflict_id = conflict.lastrowid
                cursor = connection.execute(
                    "INSERT INTO geyser_raw_deliveries(event_id, source_id, stream_id, "
                    "stream_sequence, delivery_kind, received_at, conflict_id) "
                    "VALUES (NULL, ?, ?, ?, ?, ?, ?)",
                    (event.source_id, stream_id, sequence, delivery.delivery_kind,
                     received_at, conflict_id),
                )
                self._record_transport_sequence(
                    connection, source_id=event.source_id, stream_id=stream_id,
                    sequence=sequence, delivery_id=cursor.lastrowid,
                    event_id=None, received_at=received_at,
                )
                return RawIngestResult(
                    "conflict", None, cursor.lastrowid, digest, conflict_id
                )

    def get_raw_event(self, event_id: str) -> dict | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT event_id, source_id, event_kind, schema_version, payload_encoding, "
                "payload_bytes, payload_sha256, first_received_at "
                "FROM geyser_raw_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        if row is None:
            return None
        return dict(zip(
            ("event_id", "source_id", "event_kind", "schema_version", "payload_encoding",
             "payload_bytes", "payload_sha256", "first_received_at"), row
        ))

    def counts(self) -> dict[str, int]:
        with self._connection() as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in ("geyser_raw_events", "geyser_raw_deliveries", "geyser_raw_conflicts")
            }

    def integrity_check(self) -> list[str]:
        with self._connection() as connection:
            return [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]

    def close(self) -> None:
        if self._memory_connection is not None:
            self._memory_connection.close()
            self._memory_connection = None
