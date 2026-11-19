"""Offline recovery, backfill-job, and projection-checkpoint persistence.

This module shares the dedicated smr_geyser.sqlite database. It never connects
to a provider. Backfill coverage is an auditable assertion supplied by a
provider adapter; this store records it but cannot independently prove a
provider's historical-retention or pagination guarantees.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


_COVERAGE = {"COMPLETE", "PARTIAL", "UNKNOWN"}
_JOB_STATES = {"PENDING", "RUNNING", "PARTIAL", "COMPLETED", "FAILED"}
_TERMINAL_STATES = {"PARTIAL", "COMPLETED", "FAILED"}


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve ser texto não vazio")
    return value


def _count(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} deve ser inteiro não negativo")
    return value


def _json_object(value: dict | None, field: str) -> str:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise TypeError(f"{field} deve ser um objeto")
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} não é JSON válido") from exc


def _coverage(value: str) -> str:
    if value not in _COVERAGE:
        raise ValueError("coverage_status deve ser COMPLETE, PARTIAL ou UNKNOWN")
    return value


class SQLiteGeyserRecoveryStore:
    """Persist resumable backfill jobs and source-scoped projection checkpoints."""

    SCHEMA_VERSION = 1

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("recovery store deve compartilhar o arquivo SQLite Geyser persistente")
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS geyser_recovery_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)
            current = connection.execute(
                "SELECT COALESCE(MAX(version),0) FROM geyser_recovery_schema_migrations"
            ).fetchone()[0]
            if current > self.SCHEMA_VERSION:
                raise sqlite3.DatabaseError("Schema de recovery Geyser mais novo que esta versão do SMR")
            if current < 1:
                connection.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE geyser_projection_checkpoints (
                        projection_name TEXT NOT NULL,
                        projection_version INTEGER NOT NULL CHECK(projection_version > 0),
                        source_id TEXT NOT NULL,
                        generation INTEGER NOT NULL CHECK(generation > 0),
                        last_delivery_id INTEGER NOT NULL CHECK(last_delivery_id >= 0),
                        last_event_id TEXT,
                        source_delivery_count INTEGER NOT NULL CHECK(source_delivery_count >= 0),
                        projected_event_count INTEGER NOT NULL CHECK(projected_event_count >= 0),
                        skipped_unsequenced_count INTEGER NOT NULL CHECK(skipped_unsequenced_count >= 0),
                        input_coverage_status TEXT NOT NULL CHECK(input_coverage_status IN ('COMPLETE','PARTIAL','UNKNOWN')),
                        continuity_interrupted INTEGER NOT NULL CHECK(continuity_interrupted IN (0,1)),
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(projection_name, projection_version, source_id)
                    );
                    CREATE TABLE geyser_backfill_jobs (
                        job_id TEXT PRIMARY KEY,
                        source_id TEXT NOT NULL,
                        start_slot INTEGER NOT NULL CHECK(start_slot >= 0),
                        end_slot INTEGER NOT NULL CHECK(end_slot >= start_slot),
                        provider TEXT NOT NULL,
                        adapter_version TEXT NOT NULL,
                        schema_version TEXT NOT NULL,
                        query_semantics TEXT NOT NULL,
                        cursor_start TEXT,
                        cursor_current TEXT,
                        cursor_end TEXT,
                        status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','PARTIAL','COMPLETED','FAILED')),
                        coverage_status TEXT NOT NULL CHECK(coverage_status IN ('COMPLETE','PARTIAL','UNKNOWN')),
                        requested_count INTEGER NOT NULL DEFAULT 0 CHECK(requested_count >= 0),
                        received_count INTEGER NOT NULL DEFAULT 0 CHECK(received_count >= 0),
                        normalized_count INTEGER NOT NULL DEFAULT 0 CHECK(normalized_count >= 0),
                        rejected_count INTEGER NOT NULL DEFAULT 0 CHECK(rejected_count >= 0),
                        retry_count INTEGER NOT NULL DEFAULT 0 CHECK(retry_count >= 0),
                        last_error TEXT,
                        coverage_evidence_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        updated_at TEXT NOT NULL,
                        finished_at TEXT
                    );
                    CREATE INDEX idx_geyser_backfill_source_status
                        ON geyser_backfill_jobs(source_id,status,start_slot,end_slot);
                    CREATE TABLE geyser_backfill_attempts (
                        attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id TEXT NOT NULL REFERENCES geyser_backfill_jobs(job_id),
                        attempt_number INTEGER NOT NULL CHECK(attempt_number > 0),
                        status TEXT NOT NULL CHECK(status IN ('RUNNING','INTERRUPTED','PARTIAL','COMPLETED','FAILED')),
                        cursor_start TEXT,
                        cursor_end TEXT,
                        started_at TEXT NOT NULL,
                        ended_at TEXT,
                        error TEXT,
                        UNIQUE(job_id,attempt_number)
                    );
                    INSERT INTO geyser_recovery_schema_migrations(version,applied_at)
                        VALUES (1,CURRENT_TIMESTAMP);
                    COMMIT;
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
    def _job(row) -> dict:
        keys = (
            "job_id", "source_id", "start_slot", "end_slot", "provider",
            "adapter_version", "schema_version", "query_semantics",
            "cursor_start", "cursor_current", "cursor_end", "status",
            "coverage_status", "requested_count", "received_count",
            "normalized_count", "rejected_count", "retry_count", "last_error",
            "coverage_evidence_json", "created_at", "started_at", "updated_at",
            "finished_at",
        )
        result = dict(zip(keys, row))
        result["coverage_evidence"] = json.loads(result.pop("coverage_evidence_json"))
        return result

    def create_backfill_job(
        self, *, source_id: str, start_slot: int, end_slot: int,
        provider: str, adapter_version: str, schema_version: str,
        query_semantics: str, cursor_start: str | None = None,
        cursor_end: str | None = None,
    ) -> dict:
        source_id = _text(source_id, "source_id")
        provider = _text(provider, "provider")
        adapter_version = _text(adapter_version, "adapter_version")
        schema_version = _text(schema_version, "schema_version")
        query_semantics = _text(query_semantics, "query_semantics")
        start_slot = _count(start_slot, "start_slot")
        end_slot = _count(end_slot, "end_slot")
        if end_slot < start_slot:
            raise ValueError("end_slot deve ser maior ou igual a start_slot")
        if cursor_start is not None:
            cursor_start = _text(cursor_start, "cursor_start")
        if cursor_end is not None:
            cursor_end = _text(cursor_end, "cursor_end")
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection, connection:
            connection.execute("""
                INSERT INTO geyser_backfill_jobs
                (job_id,source_id,start_slot,end_slot,provider,adapter_version,
                 schema_version,query_semantics,cursor_start,cursor_current,cursor_end,
                 status,coverage_status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,'PENDING','UNKNOWN',?,?)
            """, (job_id,source_id,start_slot,end_slot,provider,adapter_version,
                  schema_version,query_semantics,cursor_start,cursor_start,cursor_end,now,now))
        return self.get_backfill_job(job_id)

    def start_backfill_job(self, job_id: str) -> dict:
        job_id = _text(job_id, "job_id")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection, connection:
            row = connection.execute(
                "SELECT status,retry_count,cursor_current FROM geyser_backfill_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row[0] not in {"PENDING","PARTIAL","FAILED"}:
                raise ValueError(f"não é possível iniciar job no estado {row[0]}")
            attempt = row[1] + 1
            connection.execute("""
                INSERT INTO geyser_backfill_attempts
                (job_id,attempt_number,status,cursor_start,started_at)
                VALUES (?,?, 'RUNNING', ?, ?)
            """, (job_id,attempt,row[2],now))
            connection.execute("""
                UPDATE geyser_backfill_jobs SET status='RUNNING',retry_count=?,
                    started_at=COALESCE(started_at,?),updated_at=?,finished_at=NULL,last_error=NULL
                WHERE job_id=?
            """, (attempt-1,now,now,job_id))
        return self.get_backfill_job(job_id)

    def update_backfill_progress(
        self, job_id: str, *, cursor_current: str | None = None,
        requested_count: int | None = None, received_count: int | None = None,
        normalized_count: int | None = None, rejected_count: int | None = None,
        coverage_status: str | None = None, coverage_evidence: dict | None = None,
    ) -> dict:
        job_id = _text(job_id, "job_id")
        now = datetime.now(timezone.utc).isoformat()
        updates = {}
        for name, value in (
            ("requested_count",requested_count),("received_count",received_count),
            ("normalized_count",normalized_count),("rejected_count",rejected_count),
        ):
            if value is not None:
                updates[name] = _count(value,name)
        if cursor_current is not None:
            updates["cursor_current"] = _text(cursor_current,"cursor_current")
        if coverage_status is not None:
            updates["coverage_status"] = _coverage(coverage_status)
        if coverage_evidence is not None:
            updates["coverage_evidence_json"] = _json_object(coverage_evidence,"coverage_evidence")
        with self._connect() as connection, connection:
            row = connection.execute(
                "SELECT status,requested_count,received_count,normalized_count,rejected_count "
                "FROM geyser_backfill_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row[0] != "RUNNING":
                raise ValueError("progresso só pode ser registrado em job RUNNING")
            for index,name in enumerate(("requested_count","received_count","normalized_count","rejected_count"),1):
                if name in updates and updates[name] < row[index]:
                    raise ValueError(f"{name} não pode regredir")
            if updates:
                assignments = ",".join(f"{key}=?" for key in updates)
                connection.execute(
                    f"UPDATE geyser_backfill_jobs SET {assignments},updated_at=? WHERE job_id=?",
                    (*updates.values(),now,job_id),
                )
        return self.get_backfill_job(job_id)

    def finish_backfill_job(
        self, job_id: str, *, status: str, coverage_status: str,
        coverage_evidence: dict, error: str | None = None,
    ) -> dict:
        job_id = _text(job_id, "job_id")
        if status not in _TERMINAL_STATES:
            raise ValueError("status final deve ser PARTIAL, COMPLETED ou FAILED")
        coverage_status = _coverage(coverage_status)
        evidence_json = _json_object(coverage_evidence,"coverage_evidence")
        evidence = json.loads(evidence_json)
        if status == "COMPLETED":
            required = (
                evidence.get("provider_contract") == "confirmed",
                evidence.get("range_covered") is True,
                evidence.get("pagination_exhausted") is True,
                isinstance(evidence.get("query_semantics"), str) and bool(evidence["query_semantics"].strip()),
            )
            if coverage_status != "COMPLETE" or not all(required):
                raise ValueError("COMPLETED exige coverage COMPLETE e evidência explícita do contrato, intervalo e paginação")
        if status == "PARTIAL" and coverage_status == "COMPLETE":
            raise ValueError("job PARTIAL não pode declarar coverage COMPLETE")
        if error is not None:
            error = _text(error,"error")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection, connection:
            row = connection.execute(
                "SELECT status,retry_count FROM geyser_backfill_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row[0] != "RUNNING":
                raise ValueError("somente job RUNNING pode ser finalizado")
            connection.execute("""
                UPDATE geyser_backfill_jobs SET status=?,coverage_status=?,
                    coverage_evidence_json=?,last_error=?,updated_at=?,finished_at=?
                WHERE job_id=?
            """, (status,coverage_status,evidence_json,error,now,now,job_id))
            connection.execute("""
                UPDATE geyser_backfill_attempts SET status=?,cursor_end=(
                    SELECT cursor_current FROM geyser_backfill_jobs WHERE job_id=?
                ),ended_at=?,error=? WHERE job_id=? AND attempt_number=?
            """, (status,job_id,now,error,job_id,row[1]+1))
        return self.get_backfill_job(job_id)

    def recover_interrupted_jobs(self) -> list[dict]:
        """Mark abandoned RUNNING jobs partial/failed without inventing coverage."""
        now = datetime.now(timezone.utc).isoformat()
        recovered = []
        with self._connect() as connection, connection:
            rows = connection.execute("""
                SELECT job_id,retry_count,received_count,coverage_status
                FROM geyser_backfill_jobs WHERE status='RUNNING' ORDER BY created_at,job_id
            """).fetchall()
            for job_id,attempt,received,prior_coverage in rows:
                status = "PARTIAL" if received else "FAILED"
                coverage = "PARTIAL" if received else "UNKNOWN"
                note = "execução interrompida; cursor preservado para retomada"
                connection.execute("""
                    UPDATE geyser_backfill_jobs SET status=?,coverage_status=?,
                        last_error=?,updated_at=?,finished_at=? WHERE job_id=?
                """, (status,coverage,note,now,now,job_id))
                connection.execute("""
                    UPDATE geyser_backfill_attempts SET status='INTERRUPTED',
                        cursor_end=(SELECT cursor_current FROM geyser_backfill_jobs WHERE job_id=?),
                        ended_at=?,error=? WHERE job_id=? AND attempt_number=?
                """, (job_id,now,note,job_id,attempt+1))
                recovered.append(job_id)
        return [self.get_backfill_job(job_id) for job_id in recovered]

    def get_backfill_job(self, job_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("""
                SELECT job_id,source_id,start_slot,end_slot,provider,adapter_version,
                    schema_version,query_semantics,cursor_start,cursor_current,cursor_end,
                    status,coverage_status,requested_count,received_count,normalized_count,
                    rejected_count,retry_count,last_error,coverage_evidence_json,created_at,
                    started_at,updated_at,finished_at
                FROM geyser_backfill_jobs WHERE job_id=?
            """, (_text(job_id,"job_id"),)).fetchone()
        return None if row is None else self._job(row)

    def list_backfill_jobs(self, *, source_id: str | None = None, status: str | None = None) -> list[dict]:
        clauses, params = [], []
        if source_id is not None:
            clauses.append("source_id=?")
            params.append(_text(source_id,"source_id"))
        if status is not None:
            if status not in _JOB_STATES:
                raise ValueError("status de job inválido")
            clauses.append("status=?")
            params.append(status)
        sql = "SELECT job_id FROM geyser_backfill_jobs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at,job_id"
        with self._connect() as connection:
            ids = [row[0] for row in connection.execute(sql,params).fetchall()]
        return [self.get_backfill_job(job_id) for job_id in ids]

    def list_backfill_attempts(self, job_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT attempt_id,attempt_number,status,cursor_start,cursor_end,
                    started_at,ended_at,error FROM geyser_backfill_attempts
                WHERE job_id=? ORDER BY attempt_number
            """, (_text(job_id,"job_id"),)).fetchall()
        keys = ("attempt_id","attempt_number","status","cursor_start","cursor_end",
                "started_at","ended_at","error")
        return [dict(zip(keys,row)) for row in rows]

    def record_projection_checkpoint(
        self, *, projection_name: str, projection_version: int, source_id: str,
        generation: int, last_delivery_id: int, last_event_id: str | None,
        source_delivery_count: int, projected_event_count: int,
        skipped_unsequenced_count: int, input_coverage_status: str,
        continuity_interrupted: bool,
    ) -> dict:
        projection_name = _text(projection_name,"projection_name")
        source_id = _text(source_id,"source_id")
        for name,value in (("projection_version",projection_version),("generation",generation),
                           ("last_delivery_id",last_delivery_id),("source_delivery_count",source_delivery_count),
                           ("projected_event_count",projected_event_count),
                           ("skipped_unsequenced_count",skipped_unsequenced_count)):
            _count(value,name)
        if projection_version == 0 or generation == 0:
            raise ValueError("projection_version e generation devem ser positivos")
        if last_event_id is not None:
            last_event_id = _text(last_event_id,"last_event_id")
        if not isinstance(continuity_interrupted,bool):
            raise TypeError("continuity_interrupted deve ser bool")
        coverage = _coverage(input_coverage_status)
        if coverage == "COMPLETE" and (continuity_interrupted or skipped_unsequenced_count):
            raise ValueError("input COMPLETE exige continuidade não interrompida e zero evento sem sequência")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection, connection:
            prior = connection.execute("""
                SELECT generation,last_delivery_id FROM geyser_projection_checkpoints
                WHERE projection_name=? AND projection_version=? AND source_id=?
            """, (projection_name,projection_version,source_id)).fetchone()
            if prior and (generation <= prior[0] or last_delivery_id < prior[1]):
                raise ValueError("generation deve avançar e last_delivery_id não pode regredir")
            connection.execute("""
                INSERT INTO geyser_projection_checkpoints
                (projection_name,projection_version,source_id,generation,last_delivery_id,
                 last_event_id,source_delivery_count,projected_event_count,
                 skipped_unsequenced_count,input_coverage_status,continuity_interrupted,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(projection_name,projection_version,source_id) DO UPDATE SET
                    generation=excluded.generation,last_delivery_id=excluded.last_delivery_id,
                    last_event_id=excluded.last_event_id,source_delivery_count=excluded.source_delivery_count,
                    projected_event_count=excluded.projected_event_count,
                    skipped_unsequenced_count=excluded.skipped_unsequenced_count,
                    input_coverage_status=excluded.input_coverage_status,
                    continuity_interrupted=excluded.continuity_interrupted,updated_at=excluded.updated_at
            """, (projection_name,projection_version,source_id,generation,last_delivery_id,
                  last_event_id,source_delivery_count,projected_event_count,
                  skipped_unsequenced_count,coverage,int(continuity_interrupted),now))
        return self.get_projection_checkpoint(projection_name,projection_version,source_id)

    def get_projection_checkpoint(self, projection_name: str, projection_version: int, source_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("""
                SELECT projection_name,projection_version,source_id,generation,last_delivery_id,
                    last_event_id,source_delivery_count,projected_event_count,
                    skipped_unsequenced_count,input_coverage_status,continuity_interrupted,updated_at
                FROM geyser_projection_checkpoints
                WHERE projection_name=? AND projection_version=? AND source_id=?
            """, (_text(projection_name,"projection_name"),_count(projection_version,"projection_version"),
                  _text(source_id,"source_id"))).fetchone()
        if row is None:
            return None
        keys = ("projection_name","projection_version","source_id","generation","last_delivery_id",
                "last_event_id","source_delivery_count","projected_event_count",
                "skipped_unsequenced_count","input_coverage_status","continuity_interrupted","updated_at")
        result = dict(zip(keys,row))
        result["continuity_interrupted"] = bool(result["continuity_interrupted"])
        return result
