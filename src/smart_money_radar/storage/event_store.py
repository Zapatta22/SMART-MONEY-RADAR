"""Armazenamento histórico SQLite, com deduplicação local de eventos."""

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from smart_money_radar.domain.models import (
    ActivityEvent, SwapClassification, SwapEvidence, SwapObservation, TokenBalanceDelta,
    build_swap_operation_id,
)
from smart_money_radar.domain.normalization import NormalizedObservation
from smart_money_radar.domain.swap_bundle_builder import SwapDomainBundle
from smart_money_radar.storage.collector_authority import collector_write, verify_collector_authority


@dataclass(frozen=True)
class SwapReconciliationRecord:
    """Resultado auditável de uma tentativa de reconciliar um swap CPMM."""

    operation_id: str
    instruction_index: int
    inner_instruction_index: int | None
    cpi_path: tuple[int, ...]
    status: str
    reason: str


class SQLiteEventStore:
    """Persiste eventos sem armazenar chaves ou credenciais."""

    def __init__(
        self, database_path: Path | str, *, read_only: bool = False
    ) -> None:
        if not isinstance(read_only, bool):
            raise TypeError("read_only deve ser bool")
        self.database_path = Path(database_path)
        self.read_only = read_only
        self._memory_connection: sqlite3.Connection | None = None
        if read_only:
            if str(database_path) == ":memory:":
                raise ValueError("read_only exige um arquivo SQLite existente.")
            if not self.database_path.is_file():
                raise FileNotFoundError(
                    f"Banco SQLite não encontrado para abertura somente leitura: {self.database_path}"
                )
            self._validate_read_only_schema()
        elif str(database_path) == ":memory:":
            # Keep one connection alive: a fresh SQLite :memory: connection is
            # a different database and would lose the schema/data immediately.
            self._memory_connection = sqlite3.connect(":memory:")
            self._initialize()
        else:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    def bind_collector(self, authority):
        """Bind a new handle to an immutable generation, without migrations."""
        from smart_money_radar.storage.collector_authority import CollectorAuthority, AuthorityLost
        if not isinstance(authority, CollectorAuthority) or self.read_only:
            raise ValueError("writable store and collector authority required")
        if str(self.database_path)==":memory:" or not Path(self.database_path).samefile(authority.database_path):
            raise AuthorityLost("collector database mismatch")
        if getattr(self,"_collector_authority",None) is not None:
            raise AuthorityLost("a bound collector handle cannot be rebound")
        bound = object.__new__(type(self))
        bound.__dict__ = self.__dict__.copy()
        bound._collector_authority = authority
        return bound

    def assert_collector_authority(self, radar=None):
        with self._connection_scope() as conn, conn:
            conn.execute("BEGIN")
            verify_collector_authority(conn,getattr(self,"_collector_authority",None),radar)

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            self._memory_connection.execute("PRAGMA foreign_keys = ON")
            return self._memory_connection
        if self.read_only:
            uri = self.database_path.resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=15.0)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 15000")
            return connection
        connection = sqlite3.connect(self.database_path, timeout=15.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def _validate_read_only_schema(self) -> None:
        """Valida o esquema existente sem criar tabelas, índices ou migrações."""
        required = {
            "activity_events", "wallet_checkpoints", "observed_transactions",
            "token_balance_deltas", "processed_signatures", "swap_observations",
            "swap_classifications", "swap_evidence", "swap_reconciliation_attempts",
        }
        uri = self.database_path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=15.0)
        try:
            present = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            connection.close()
        missing = sorted(required - present)
        if missing:
            raise sqlite3.DatabaseError(
                "Banco SQLite sem o esquema completo para leitura: " + ", ".join(missing)
            )

    @contextmanager
    def _connection_scope(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            if connection is not self._memory_connection:
                connection.close()

    def close(self) -> None:
        """Fecha a conexão persistente quando o armazenamento é em memória."""
        if self._memory_connection is not None:
            self._memory_connection.close()
            self._memory_connection = None

    def _initialize(self) -> None:
        with self._connection_scope() as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS activity_events (
                        id INTEGER PRIMARY KEY,
                        wallet_address TEXT NOT NULL,
                        signature TEXT NOT NULL,
                        occurred_at TEXT,
                        token_mint TEXT NOT NULL,
                        direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
                        amount TEXT NOT NULL,
                        UNIQUE (wallet_address, signature, token_mint, direction)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_activity_wallet_time
                    ON activity_events (wallet_address, occurred_at DESC)
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS wallet_checkpoints (
                        wallet_address TEXT PRIMARY KEY,
                        signature TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS observed_transactions (
                        wallet_address TEXT NOT NULL,
                        signature TEXT NOT NULL,
                        payload_json TEXT,
                        parse_status TEXT NOT NULL,
                        parser_version TEXT NOT NULL,
                        parse_error TEXT,
                        observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (wallet_address, signature)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_observed_parse_status
                    ON observed_transactions (parse_status, observed_at)
                    """
                )
                # Incremental migration: databases created before normalized
                # ingestion keep their rows and gain nullable metadata columns.
                observed_columns = {
                    row[1] for row in connection.execute(
                        "PRAGMA table_info(observed_transactions)"
                    ).fetchall()
                }
                for column, definition in (
                    ("chain", "TEXT"),
                    ("slot", "INTEGER"),
                    ("occurred_at", "TEXT"),
                ):
                    if column not in observed_columns:
                        connection.execute(
                            f"ALTER TABLE observed_transactions ADD COLUMN {column} {definition}"
                        )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS token_balance_deltas (
                        wallet_address TEXT NOT NULL,
                        signature TEXT NOT NULL,
                        chain TEXT NOT NULL,
                        token_mint TEXT NOT NULL,
                        direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
                        amount TEXT NOT NULL,
                        decimals INTEGER,
                        PRIMARY KEY (wallet_address, signature, token_mint, direction),
                        FOREIGN KEY (wallet_address, signature)
                            REFERENCES observed_transactions(wallet_address, signature)
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS processed_signatures (
                        wallet_address TEXT NOT NULL,
                        signature TEXT NOT NULL,
                        processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (wallet_address, signature)
                    )
                    """
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS swap_observations (
                        operation_id TEXT PRIMARY KEY, chain TEXT NOT NULL,
                        wallet_address TEXT NOT NULL, signature TEXT NOT NULL,
                        input_mint TEXT NOT NULL, output_mint TEXT NOT NULL,
                        input_amount TEXT NOT NULL, output_amount TEXT NOT NULL,
                        observed_at TEXT NOT NULL, parser_version TEXT NOT NULL,
                        FOREIGN KEY(wallet_address, signature)
                            REFERENCES observed_transactions(wallet_address, signature)
                            ON DELETE CASCADE)"""
                )
                connection.execute("""CREATE INDEX IF NOT EXISTS idx_swap_observations_wallet_time
                    ON swap_observations(wallet_address, observed_at DESC)""")
                connection.execute("""CREATE INDEX IF NOT EXISTS idx_swap_observations_signature
                    ON swap_observations(signature)""")
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS swap_classifications (
                        operation_id TEXT PRIMARY KEY,
                        side TEXT NOT NULL CHECK(side IN ('BUY','SELL','UNKNOWN')),
                        confidence TEXT NOT NULL, reason TEXT NOT NULL,
                        FOREIGN KEY(operation_id) REFERENCES swap_observations(operation_id)
                            ON DELETE CASCADE)"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS swap_evidence (
                        operation_id TEXT PRIMARY KEY, program_id TEXT NOT NULL,
                        venue TEXT, instruction_index INTEGER NOT NULL,
                        cpi_path_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
                        FOREIGN KEY(operation_id) REFERENCES swap_observations(operation_id)
                            ON DELETE CASCADE)"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS swap_replay_archive (
                        receipt_id INTEGER PRIMARY KEY,
                        operation_id TEXT NOT NULL UNIQUE,
                        wallet_address TEXT NOT NULL,
                        program_id TEXT NOT NULL,
                        pool_address TEXT,
                        input_mint TEXT NOT NULL,
                        output_mint TEXT NOT NULL,
                        input_amount TEXT NOT NULL,
                        output_amount TEXT NOT NULL,
                        side TEXT NOT NULL CHECK(side IN ('BUY','SELL','UNKNOWN')),
                        confidence TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        available_at TEXT NOT NULL,
                        FOREIGN KEY(operation_id) REFERENCES swap_observations(operation_id)
                            ON DELETE CASCADE
                    )"""
                )
                replay_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(swap_replay_archive)")
                }
                if "pool_address" not in replay_columns:
                    connection.execute("ALTER TABLE swap_replay_archive ADD COLUMN pool_address TEXT")
                connection.execute(
                    """CREATE INDEX IF NOT EXISTS idx_swap_replay_scope
                       ON swap_replay_archive(wallet_address, program_id, receipt_id)"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS swap_reconciliation_attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        attempt_id TEXT NOT NULL,
                        wallet_address TEXT NOT NULL,
                        signature TEXT NOT NULL,
                        operation_id TEXT NOT NULL,
                        instruction_index INTEGER NOT NULL,
                        inner_instruction_index INTEGER,
                        cpi_path_json TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('MATCHED','INCOMPLETE','AMBIGUOUS','UNRESOLVED')),
                        reason TEXT NOT NULL,
                        attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(wallet_address, signature)
                            REFERENCES observed_transactions(wallet_address, signature)
                            ON DELETE CASCADE
                    )"""
                )
                connection.execute(
                    """CREATE INDEX IF NOT EXISTS idx_swap_reconciliation_signature
                       ON swap_reconciliation_attempts(wallet_address, signature, attempted_at, id)"""
                )

                connection.execute(
                    """CREATE TABLE IF NOT EXISTS cpmm_launch_raw (
                           sha256 TEXT PRIMARY KEY,
                           payload BLOB NOT NULL,
                           archived_at TEXT NOT NULL
                       )"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS cpmm_launch_evidence (
                           pool TEXT NOT NULL,
                           identity TEXT NOT NULL,
                           sha256 TEXT NOT NULL REFERENCES cpmm_launch_raw(sha256),
                           PRIMARY KEY(pool, identity, sha256)
                       )"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS cpmm_launch_stream_cursor (
                           source_id TEXT PRIMARY KEY,
                           first_sequence INTEGER NOT NULL CHECK(first_sequence >= 0),
                           last_sequence INTEGER NOT NULL CHECK(last_sequence >= first_sequence),
                           updated_at TEXT NOT NULL
                       )"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS cpmm_launch_stream_delivery (
                           source_id TEXT NOT NULL,
                           sequence INTEGER NOT NULL CHECK(sequence >= 0),
                           sha256 TEXT NOT NULL REFERENCES cpmm_launch_raw(sha256),
                           PRIMARY KEY(source_id, sequence)
                       )"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS cpmm_launch_rpc_cursor (
                           source_id TEXT PRIMARY KEY,
                           signature TEXT NOT NULL,
                           last_sequence INTEGER NOT NULL CHECK(last_sequence >= 0),
                           updated_at TEXT NOT NULL
                       )"""
                )

                connection.execute("""CREATE TABLE IF NOT EXISTS cm33_paper_runs (
                    run_id TEXT PRIMARY KEY, radar TEXT NOT NULL CHECK(radar IN ('launch','smart_money')),
                    metadata TEXT NOT NULL, metadata_sha TEXT NOT NULL,
                    report TEXT NOT NULL, report_sha TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE IF NOT EXISTS cm33_paper_ticks (
                    run_id TEXT NOT NULL REFERENCES cm33_paper_runs(run_id),
                    sequence INTEGER NOT NULL CHECK(sequence>=0), quote_id TEXT NOT NULL,
                    signal_id TEXT, payload TEXT NOT NULL, payload_sha TEXT NOT NULL,
                    PRIMARY KEY(run_id,sequence), UNIQUE(run_id,quote_id),
                    UNIQUE(run_id,signal_id))""")

                connection.execute("""CREATE TABLE IF NOT EXISTS cm34_capital_accounts (
                    account_id TEXT PRIMARY KEY, metadata TEXT NOT NULL, metadata_sha TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE IF NOT EXISTS cm34_capital_journal (
                    account_id TEXT NOT NULL REFERENCES cm34_capital_accounts(account_id),
                    seq INTEGER NOT NULL CHECK(seq>=0), event_id TEXT NOT NULL,
                    payload TEXT NOT NULL, payload_sha TEXT NOT NULL,
                    previous_sha TEXT NOT NULL, chain_sha TEXT NOT NULL,
                    PRIMARY KEY(account_id,seq), UNIQUE(account_id,event_id))""")
                connection.execute("""CREATE TABLE IF NOT EXISTS cm34_capital_runs (
                    account_id TEXT NOT NULL REFERENCES cm34_capital_accounts(account_id),
                    run_id TEXT PRIMARY KEY REFERENCES cm33_paper_runs(run_id),
                    binding TEXT NOT NULL, binding_sha TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE IF NOT EXISTS cm34_operational_journal (
                    seq INTEGER PRIMARY KEY CHECK(seq>=0), event_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL, payload_sha TEXT NOT NULL,
                    previous_sha TEXT NOT NULL, chain_sha TEXT NOT NULL)""")

                connection.execute("""CREATE TABLE IF NOT EXISTS cm35_wallet_profiles (
                    snapshot_id TEXT PRIMARY KEY, cutoff TEXT NOT NULL, policy_sha TEXT NOT NULL,
                    payload TEXT NOT NULL, payload_sha TEXT NOT NULL)""")
                connection.execute("""CREATE INDEX IF NOT EXISTS idx_cm35_wallet_cutoff
                    ON cm35_wallet_profiles(cutoff)""")

                connection.execute("""CREATE TABLE IF NOT EXISTS cm36_supervisor_lease (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), generation INTEGER NOT NULL,
                    owner TEXT NOT NULL, heartbeat REAL NOT NULL, expires REAL NOT NULL,
                    status TEXT NOT NULL, payload_sha TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE IF NOT EXISTS cm36_supervisor_tasks (
                    radar TEXT PRIMARY KEY CHECK(radar IN ('launch','smart_money')),
                    payload TEXT NOT NULL, payload_sha TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE IF NOT EXISTS cm36_decision_journal (
                    radar TEXT NOT NULL, event_id TEXT NOT NULL, event_sha TEXT NOT NULL,
                    payload TEXT NOT NULL, payload_sha TEXT NOT NULL,
                    PRIMARY KEY(radar,event_id,event_sha))""")
                connection.execute("""CREATE TABLE IF NOT EXISTS cm36_supervisor_alerts (
                    id TEXT PRIMARY KEY, radar TEXT NOT NULL, payload TEXT NOT NULL,
                    payload_sha TEXT NOT NULL)""")

    def archive_cpmm_launches(
        self, payloads: list[bytes], *,
        source_id: str | None = None, first_sequence: int | None = None,
    ) -> dict:
        """Archive RAW and identities; optional durable consumer sequence in same commit.

        The sequence is assigned by the upstream consumer, NOT a Solana slot.
        The first seen sequence is a local baseline, not proof of prior coverage.
        """
        from smart_money_radar.data_sources.raydium_cpmm_launch import detect_cpmm_pool_initializations

        if self.read_only:
            raise ValueError("arquivo de lançamentos exige SQLite gravável")
        if (source_id is None) != (first_sequence is None):
            raise ValueError("origem e primeira sequência devem ser informadas juntas")
        if source_id is not None:
            if (not isinstance(source_id, str) or not source_id.strip()
                    or len(source_id) > 256 or "\x00" in source_id):
                raise ValueError("identidade do consumidor inválida")
            if (type(first_sequence) is not int or first_sequence < 0
                    or not payloads or first_sequence + len(payloads) - 1 > 2**63 - 1):
                raise ValueError("intervalo de sequência inválido")
        inputs = []
        frames = []
        candidates = {}
        records = []
        for raw in payloads:
            if not isinstance(raw, bytes):
                raise ValueError("payload RAW deve conter bytes")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("transação do Launch Radar precisa ser um objeto JSON")
            digest = hashlib.sha256(raw).hexdigest()
            frames.append((digest, raw))
            found = detect_cpmm_pool_initializations(payload)
            inputs.append({"sha256": digest, "matched_initializations": len(found)})
            if not found:
                continue
            identities = []
            for observation in found:
                fields = asdict(observation)
                identity = json.dumps(fields, sort_keys=True, separators=(",", ":"))
                identities.append((observation.pool, identity, digest))
                candidates.setdefault(observation.pool, fields)
            records.append((digest, raw, identities))

        with self._connection_scope() as connection:
            with collector_write(connection, getattr(self, "_collector_authority", None), "launch"):
                return self._archive_cpmm_launches_prepared(
                    connection, inputs, frames, candidates, records,
                    source_id=source_id, first_sequence=first_sequence,
                )

    def _archive_cpmm_launches_prepared(
        self, connection: sqlite3.Connection, inputs: list, frames: list,
        candidates: dict, records: list, *,
        source_id: str | None, first_sequence: int | None,
    ) -> dict:
        """Persist prepared evidence in a caller-owned SQLite transaction."""
        new_pools = []
        conflicts = []
        stream_report = None
        if True:
            new_deliveries = []
            replayed_count = 0
            if source_id is not None:
                previous = connection.execute(
                    "SELECT first_sequence, last_sequence FROM cpmm_launch_stream_cursor "
                    "WHERE source_id = ?", (source_id,),
                ).fetchone()
                start = previous[0] if previous else None
                last = previous[1] if previous else None
                for offset, (digest, _) in enumerate(frames):
                    sequence = first_sequence + offset
                    saved = connection.execute(
                        "SELECT sha256 FROM cpmm_launch_stream_delivery "
                        "WHERE source_id = ? AND sequence = ?", (source_id, sequence),
                    ).fetchone()
                    if saved is not None:
                        if saved[0] != digest:
                            raise ValueError("conflito de identidade RAW na sequência já arquivada")
                        if last is None or sequence > last:
                            raise ValueError("cursor de lançamentos inconsistente")
                        replayed_count += 1
                        continue
                    if last is not None and sequence != last + 1:
                        raise ValueError("lacuna ou sequência histórica desconhecida no consumidor")
                    if start is None:
                        start = sequence
                    new_deliveries.append((source_id, sequence, digest))
                    last = sequence
            known = {
                pool for pool in candidates if connection.execute(
                    "SELECT 1 FROM cpmm_launch_evidence WHERE pool = ? LIMIT 1", (pool,)
                ).fetchone()
            }
            archived_at = datetime.now(timezone.utc).isoformat()
            # INSERT OR IGNORE must not conceal a damaged existing RAW row.
            for digest, raw in frames:
                saved = connection.execute(
                    "SELECT payload FROM cpmm_launch_raw WHERE sha256=?", (digest,),
                ).fetchone()
                if saved is not None and bytes(saved[0]) != raw:
                    raise ValueError("conflito de integridade RAW arquivado")
            for digest, raw, identities in records:
                connection.execute(
                    "INSERT OR IGNORE INTO cpmm_launch_raw VALUES (?, ?, ?)",
                    (digest, raw, archived_at),
                )
                connection.executemany(
                    "INSERT OR IGNORE INTO cpmm_launch_evidence VALUES (?, ?, ?)", identities,
                )
            for pool, observation in candidates.items():
                count = connection.execute(
                    "SELECT COUNT(DISTINCT identity) FROM cpmm_launch_evidence WHERE pool = ?", (pool,)
                ).fetchone()[0]
                if count > 1:
                    conflicts.append(pool)
                elif pool not in known:
                    new_pools.append(observation)
            if source_id is not None:
                # Save even non-Initialize frames: the cursor must never claim
                # an examined delivery without its immutable RAW bytes.
                connection.executemany(
                    "INSERT OR IGNORE INTO cpmm_launch_raw VALUES (?, ?, ?)",
                    ((digest, raw, archived_at) for digest, raw in frames),
                )
                connection.executemany(
                    "INSERT INTO cpmm_launch_stream_delivery VALUES (?, ?, ?)", new_deliveries,
                )
                if new_deliveries:
                    connection.execute(
                        """INSERT INTO cpmm_launch_stream_cursor
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT(source_id) DO UPDATE SET
                               last_sequence = excluded.last_sequence,
                               updated_at = excluded.updated_at""",
                        (source_id, start, last, archived_at),
                    )
                stream_report = {
                    "source_id": source_id, "first_sequence": start,
                    "last_sequence": last, "new_deliveries": len(new_deliveries),
                    "replayed_deliveries": replayed_count,
                    "prior_coverage": "UNKNOWN",
                }
        report = {
            "inputs": inputs, "initializations": new_pools, "conflicted_pools": conflicts,
        }
        if stream_report is not None:
            report["stream_cursor"] = stream_report
        return report

    def get_cpmm_launch_rpc_cursor(self, source_id: str) -> dict | None:
        """Fetch durable RPC cursor without altering state."""
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id obrigatório")
        with self._connection_scope() as connection:
            row = connection.execute(
                "SELECT signature, last_sequence FROM cpmm_launch_rpc_cursor "
                "WHERE source_id = ?", (source_id,),
            ).fetchone()
        return None if row is None else {"signature": row[0], "last_sequence": row[1]}

    def archive_cpmm_launch_rpc_batch(
        self, payloads: list[bytes], *, source_id: str, first_sequence: int,
        expected_signature: str | None, latest_signature: str,
        evidence_ids: list[str] | None = None,
    ) -> dict:
        """Archive all raw transactions and move RPC signature cursor atomically."""
        from smart_money_radar.data_sources.raydium_cpmm_launch import detect_cpmm_pool_initializations

        if self.read_only:
            raise ValueError("arquivo de lançamentos exige SQLite gravável")
        if (not isinstance(source_id, str) or not source_id.strip()
                or len(source_id) > 256 or "\x00" in source_id
                or not isinstance(latest_signature, str) or not latest_signature.strip()
                or (expected_signature is not None and
                    (not isinstance(expected_signature, str) or not expected_signature.strip()))):
            raise ValueError("identidade RPC inválida")
        if (type(first_sequence) is not int or first_sequence < 0
                or not isinstance(payloads, list) or not payloads
                or first_sequence + len(payloads) - 1 > 2**63 - 1):
            raise ValueError("intervalo RPC inválido")
        frames = []
        inputs = []
        candidates = {}
        records = []
        signatures = set()
        prior_slot = None
        last_signature = None
        for raw in payloads:
            if not isinstance(raw, bytes):
                raise ValueError("RAW RPC deve conter bytes")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("transação RPC inválida")
            tx = payload.get("result")
            transaction = tx.get("transaction") if isinstance(tx, dict) else None
            sigs = transaction.get("signatures") if isinstance(transaction, dict) else None
            slot = tx.get("slot") if isinstance(tx, dict) else None
            meta = tx.get("meta") if isinstance(tx, dict) else None
            if (not isinstance(sigs, list) or not sigs or not isinstance(sigs[0], str)
                    or not sigs[0] or sigs[0] in signatures or sigs[0] == expected_signature
                    or type(slot) is not int or slot < 0
                    or (prior_slot is not None and slot < prior_slot)
                    or not isinstance(meta, dict) or "err" not in meta):
                raise ValueError("identidade, slot ou metadados RPC inválidos")
            last_signature = sigs[0]
            signatures.add(last_signature)
            prior_slot = slot
            digest = hashlib.sha256(raw).hexdigest()
            found = detect_cpmm_pool_initializations(payload)
            frames.append((digest, raw))
            inputs.append({"sha256": digest, "matched_initializations": len(found)})
            if not found:
                continue
            identities = []
            for observation in found:
                fields = asdict(observation)
                identity = json.dumps(fields, sort_keys=True, separators=(",", ":"))
                identities.append((observation.pool, identity, digest))
                candidates.setdefault(observation.pool, fields)
            records.append((digest, raw, identities))

        if last_signature != latest_signature:
            raise ValueError("checkpoint RPC não corresponde ao último RAW")
        if evidence_ids is not None and (len(evidence_ids)!=len(payloads) or not all(isinstance(e,str) for e in evidence_ids)):
            raise ValueError("incomplete evidence batch")
        with self._connection_scope() as connection:
            with collector_write(connection, getattr(self, "_collector_authority", None), "launch"):
                previous = connection.execute(
                    "SELECT signature, last_sequence FROM cpmm_launch_rpc_cursor "
                    "WHERE source_id = ?", (source_id,),
                ).fetchone()
                if (previous[0] if previous else None) != expected_signature:
                    raise ValueError("checkpoint RPC alterado durante a coleta")
                if first_sequence != (previous[1] + 1 if previous else 0):
                    raise ValueError("sequência RPC descontínua")
                if previous is not None:
                    anchor = connection.execute(
                        """SELECT raw.payload, raw.sha256 FROM cpmm_launch_stream_delivery d
                           JOIN cpmm_launch_raw raw ON raw.sha256=d.sha256
                           WHERE d.source_id=? AND d.sequence=?""", (source_id, previous[1]),
                    ).fetchone()
                    if anchor is None or hashlib.sha256(bytes(anchor[0])).hexdigest() != anchor[1]:
                        raise ValueError("checkpoint RPC sem RAW íntegro")
                    anchor_tx = json.loads(anchor[0])["result"]
                    if (anchor_tx["transaction"]["signatures"][0] != expected_signature
                            or json.loads(payloads[0])["result"]["slot"] < anchor_tx["slot"]):
                        raise ValueError("checkpoint RPC diverge do RAW ou slot anterior")
                report = self._archive_cpmm_launches_prepared(
                    connection, inputs, frames, candidates, records,
                    source_id=source_id, first_sequence=first_sequence,
                )
                for index,raw in enumerate(payloads):
                    tx=json.loads(raw)["result"]
                    sig=tx["transaction"]["signatures"][0]
                    self._cm38_link_in_connection(connection,radar="launch",wallet_address=source_id,
                        signature=sig,evidence_id=evidence_ids[index] if evidence_ids is not None else None,
                        kind="launch_transaction",operation_id=sig,slot=tx["slot"],
                        commitment="finalized",source_id=source_id)
                connection.execute(
                    """INSERT INTO cpmm_launch_rpc_cursor VALUES (?, ?, ?, ?)
                       ON CONFLICT(source_id) DO UPDATE SET
                           signature=excluded.signature,
                           last_sequence=excluded.last_sequence,
                           updated_at=excluded.updated_at""",
                    (source_id, latest_signature, first_sequence + len(payloads) - 1,
                     datetime.now(timezone.utc).isoformat()),
                )
        return report

    def save_events(self, events: list[ActivityEvent]) -> int:
        """Grava eventos e retorna quantos registros novos foram inseridos."""
        rows = [
            (
                event.wallet_address,
                event.signature,
                event.occurred_at.isoformat() if event.occurred_at else None,
                event.token_mint,
                event.direction,
                str(event.amount),
            )
            for event in events
        ]
        if not rows:
            return 0
        with self._connection_scope() as connection:
            with collector_write(connection, getattr(self, "_collector_authority", None), "smart_money"):
                before = connection.total_changes
                connection.executemany(
                    """
                    INSERT OR IGNORE INTO activity_events
                        (wallet_address, signature, occurred_at, token_mint, direction, amount)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                return connection.total_changes - before

    def save_observation(
        self,
        wallet_address: str,
        signature: str,
        transaction: dict | None,
        events: list[ActivityEvent],
        *,
        parse_status: str,
        parser_version: str = "1",
        parse_error: str | None = None,
        normalized_observation: NormalizedObservation | None = None,
        advance_checkpoint: bool = True,
    ) -> int:
        """Persiste payload e contratos normalizados; checkpoint é opcional.

        O payload bruto permite replay quando o parser ganhar cobertura nova.
        Para falhas on-chain, transaction pode ser None e parse_status deve
        identificar explicitamente o resultado conhecido.
        """
        if not wallet_address.strip() or not signature.strip():
            raise ValueError("Carteira e assinatura da observação são obrigatórias.")
        if not parse_status.strip() or not parser_version.strip():
            raise ValueError("Estado de parsing e versão do parser são obrigatórios.")
        if not isinstance(advance_checkpoint, bool):
            raise TypeError("advance_checkpoint deve ser bool")
        if any(event.wallet_address != wallet_address or event.signature != signature for event in events):
            raise ValueError("Todos os eventos devem pertencer à observação informada.")
        if normalized_observation is not None:
            envelope = normalized_observation.transaction
            if (envelope.wallet_address, envelope.signature) != (wallet_address, signature):
                raise ValueError("Envelope normalizado não corresponde à observação informada.")
            if tuple(events) != normalized_observation.activity_events:
                raise ValueError("Eventos legados divergem do resultado normalizado.")
            if transaction is not None and envelope.raw_transaction != transaction:
                raise ValueError("Payload normalizado diverge do payload bruto informado.")
            parse_status = envelope.parse_status
            parser_version = envelope.parser_version
        payload_json = (
            json.dumps(transaction, separators=(",", ":"), sort_keys=True)
            if transaction is not None else None
        )
        rows = [
            (
                event.wallet_address,
                event.signature,
                event.occurred_at.isoformat() if event.occurred_at else None,
                event.token_mint,
                event.direction,
                str(event.amount),
            )
            for event in events
        ]
        with self._connection_scope() as connection:
            with collector_write(connection, getattr(self, "_collector_authority", None), "smart_money"):
                connection.execute(
                    """
                    INSERT INTO observed_transactions
                        (wallet_address, signature, payload_json, parse_status,
                         parser_version, parse_error, chain, slot, occurred_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(wallet_address, signature) DO UPDATE SET
                        payload_json = COALESCE(excluded.payload_json, observed_transactions.payload_json),
                        parse_status = excluded.parse_status,
                        parser_version = excluded.parser_version,
                        parse_error = excluded.parse_error,
                        chain = COALESCE(excluded.chain, observed_transactions.chain),
                        slot = COALESCE(excluded.slot, observed_transactions.slot),
                        occurred_at = COALESCE(excluded.occurred_at, observed_transactions.occurred_at)
                    """,
                    (wallet_address, signature, payload_json, parse_status,
                     parser_version, parse_error,
                     normalized_observation.transaction.chain if normalized_observation else None,
                     normalized_observation.transaction.slot if normalized_observation else None,
                     normalized_observation.transaction.occurred_at.isoformat()
                     if normalized_observation and normalized_observation.transaction.occurred_at else None),
                )
                before = connection.total_changes
                if rows:
                    connection.executemany(
                        """
                        INSERT OR IGNORE INTO activity_events
                            (wallet_address, signature, occurred_at, token_mint, direction, amount)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        rows,
                    )
                if normalized_observation is not None:
                    connection.execute(
                        "DELETE FROM token_balance_deltas WHERE wallet_address = ? AND signature = ?",
                        (wallet_address, signature),
                    )
                    delta_rows = [
                        (delta.wallet_address, delta.signature, delta.chain, delta.token_mint,
                         delta.direction, str(delta.amount), delta.decimals)
                        for delta in normalized_observation.token_deltas
                    ]
                    if delta_rows:
                        connection.executemany(
                            """
                            INSERT INTO token_balance_deltas
                                (wallet_address, signature, chain, token_mint, direction, amount, decimals)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            delta_rows,
                        )
                inserted = connection.total_changes - before
                if advance_checkpoint:
                    self._cm38_link_in_connection(connection,radar="smart_money",
                        wallet_address=wallet_address,signature=signature,
                        evidence_id=None,kind="wallet_transaction",operation_id=signature,
                        commitment="confirmed",source_id="helius-wallet-rpc")
                    self._mark_processed_in_connection(connection, wallet_address, signature)
                return inserted

    @staticmethod
    def _mark_processed_in_connection(connection, wallet_address: str, signature: str) -> None:
        connection.execute(
            """INSERT OR IGNORE INTO processed_signatures (wallet_address, signature)
               VALUES (?, ?)""",
            (wallet_address, signature),
        )
        connection.execute(
            """INSERT INTO wallet_checkpoints (wallet_address, signature)
               VALUES (?, ?)
               ON CONFLICT(wallet_address) DO UPDATE SET
                   signature = excluded.signature, updated_at = CURRENT_TIMESTAMP""",
            (wallet_address, signature),
        )

    @staticmethod
    def _cm38_link_in_connection(connection, *, radar, wallet_address, signature,
                                  evidence_id, kind, operation_id, slot=None, commitment=None,
                                  source_id=None):
        """Verify true RPC RAW and bind economics in the checkpoint transaction.

        Empty evidence is compatible only with previously uncaptured legacy
        observations; never permit an existing captured signature to bypass.
        """
        from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
        from smart_money_radar.storage.collector_authority import AuthorityLost
        exists=connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cm38_rpc_observations'"
        ).fetchone()
        if evidence_id is None:
            if exists and connection.execute(
                "SELECT 1 FROM cm38_rpc_observations WHERE radar=? AND signature=?",
                (radar,signature)
            ).fetchone():
                raise ValueError("captured transaction requires an explicit evidence link")
            return
        if not isinstance(evidence_id,str) or len(evidence_id)!=64 or not exists:
            raise ValueError("missing original RPC evidence")
        row=connection.execute(
            "SELECT metadata,metadata_sha,raw FROM cm38_rpc_observations WHERE evidence_id=?",
            (evidence_id,)
        ).fetchone()
        if row is None: raise ValueError("original RPC evidence missing")
        record=RpcObservationJournal._read(evidence_id,row)
        meta=record["metadata"]
        if meta["radar"]!=radar or meta["signature"]!=signature:
            raise ValueError("RPC source radar or signature mismatch")
        if commitment is not None and meta["commitment_requested"]!=commitment:
            raise ValueError("confirmed/finalized commitment mismatch")
        if source_id is not None and meta["source_id"]!=source_id:
            raise ValueError("RPC source identity mismatch")
        if slot is not None and meta["slot"]!=slot:
            raise ValueError("RPC slot mismatch")
        available=datetime.fromisoformat(meta["available_at"])
        if available.tzinfo is None or available>datetime.now(timezone.utc):
            raise ValueError("future or non-timezoned evidence")
        connection.execute("""CREATE TABLE IF NOT EXISTS cm38_economic_evidence_links (
            radar TEXT NOT NULL, wallet_address TEXT NOT NULL, signature TEXT NOT NULL,
            entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
            linked_at TEXT NOT NULL,
            PRIMARY KEY(radar,wallet_address,signature,entity_type,entity_id),
            FOREIGN KEY(evidence_id) REFERENCES cm38_rpc_observations(evidence_id))""")
        old=connection.execute(
            """SELECT evidence_id FROM cm38_economic_evidence_links WHERE
               radar=? AND wallet_address=? AND signature=? AND entity_type=? AND entity_id=?""",
            (radar,wallet_address,signature,kind,operation_id)
        ).fetchone()
        if old is not None and old[0]!=evidence_id:
            raise ValueError("conflicting RPC evidence for derived economics")
        if old is None:
            connection.execute(
                "INSERT INTO cm38_economic_evidence_links VALUES (?,?,?,?,?,?,?)",
                (radar,wallet_address,signature,kind,operation_id,evidence_id,
                 datetime.now(timezone.utc).isoformat())
            )

    def mark_processed(
        self, wallet_address: str, signature: str, *, replay_bundles: tuple[SwapDomainBundle, ...] = (),
        evidence_id: str | None = None,
    ) -> None:
        """Marca a transação como concluída sem regredir o checkpoint por replay antigo."""
        if not wallet_address.strip() or not signature.strip():
            raise ValueError("Carteira e assinatura do checkpoint são obrigatórias.")
        with self._connection_scope() as connection:
            with collector_write(connection, getattr(self, "_collector_authority", None), "smart_money"):
                parent = connection.execute(
                    """SELECT slot, observed_at FROM observed_transactions
                       WHERE wallet_address = ? AND signature = ?""",
                    (wallet_address, signature),
                ).fetchone()
                if parent is None:
                    raise KeyError("A transação observada deve existir antes de marcar como processada.")

                self._cm38_link_in_connection(connection,radar="smart_money",wallet_address=wallet_address,
                    signature=signature,evidence_id=evidence_id,kind="wallet_transaction",
                    operation_id=signature,slot=parent[0],commitment="confirmed",source_id="helius-wallet-rpc")
                for opid, in connection.execute(
                    "SELECT operation_id FROM swap_observations WHERE wallet_address=? AND signature=?",
                    (wallet_address,signature)):
                    self._cm38_link_in_connection(connection,radar="smart_money",wallet_address=wallet_address,
                        signature=signature,evidence_id=evidence_id,kind="swap_and_classification",
                        operation_id=opid,slot=parent[0],commitment="confirmed",source_id="helius-wallet-rpc")
                for opid, in connection.execute(
                    "SELECT DISTINCT operation_id FROM swap_reconciliation_attempts WHERE wallet_address=? AND signature=?",
                    (wallet_address,signature)):
                    self._cm38_link_in_connection(connection,radar="smart_money",wallet_address=wallet_address,
                        signature=signature,evidence_id=evidence_id,kind="economic_reconciliation",
                        operation_id=opid,slot=parent[0],commitment="confirmed",source_id="helius-wallet-rpc")
                if replay_bundles:
                    available_at = datetime.now(timezone.utc).isoformat()
                    receipts = []
                    for item in replay_bundles:
                        observation = item.observation
                        if (observation.wallet_address, observation.signature) != (wallet_address, signature):
                            raise ValueError("bundle de replay não pertence à transação processada")
                        pools = {
                            record.removeprefix("pool_state:").strip()
                            for record in item.evidence.evidence
                            if record.startswith("pool_state:") and record.removeprefix("pool_state:").strip()
                        }
                        pool_address = next(iter(pools)) if len(pools) == 1 else None
                        self._cm38_link_in_connection(connection,radar="smart_money",wallet_address=wallet_address,
                            signature=signature,evidence_id=evidence_id,kind="replay_opportunity",
                            operation_id=observation.operation_id,slot=parent[0],commitment="confirmed",source_id="helius-wallet-rpc")
                        receipts.append((
                            observation.operation_id, wallet_address, item.evidence.program_id, pool_address,
                            observation.input_mint, observation.output_mint,
                            str(observation.input_amount), str(observation.output_amount),
                            item.classification.side, str(item.classification.confidence),
                            observation.observed_at.isoformat(), available_at,
                        ))
                    connection.executemany(
                        """INSERT INTO swap_replay_archive
                           (operation_id, wallet_address, program_id, pool_address, input_mint, output_mint,
                            input_amount, output_amount, side, confidence, occurred_at, available_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(operation_id) DO NOTHING""",
                        receipts,
                    )

                current = connection.execute(
                    """SELECT observed.slot, observed.observed_at
                       FROM wallet_checkpoints AS checkpoint
                       LEFT JOIN observed_transactions AS observed
                         ON observed.wallet_address = checkpoint.wallet_address
                        AND observed.signature = checkpoint.signature
                       WHERE checkpoint.wallet_address = ?""",
                    (wallet_address,),
                ).fetchone()
                if current is not None:
                    new_slot, new_observed_at = parent
                    current_slot, current_observed_at = current
                    # A recuperação de uma assinatura antiga pode terminar depois
                    # de assinaturas mais novas. Ela deve ser marcada como processada,
                    # mas nunca pode mover o cursor para trás. Em slots iguais não há
                    # índice de transação disponível neste armazenamento; manter o
                    # checkpoint atual é a escolha conservadora.
                    if current_slot is not None and (
                        new_slot is None or new_slot <= current_slot
                    ):
                        connection.execute(
                            """INSERT OR IGNORE INTO processed_signatures
                               (wallet_address, signature) VALUES (?, ?)""",
                            (wallet_address, signature),
                        )
                        return
                    if current_slot is None and current_observed_at is not None and (
                        new_observed_at is None or new_observed_at <= current_observed_at
                    ):
                        connection.execute(
                            """INSERT OR IGNORE INTO processed_signatures
                               (wallet_address, signature) VALUES (?, ?)""",
                            (wallet_address, signature),
                        )
                        return
                self._mark_processed_in_connection(connection, wallet_address, signature)

    def save_swap_bundle(
        self, observation: SwapObservation, classification: SwapClassification,
        evidence: SwapEvidence,
    ) -> bool:
        """Grava os três contratos atomicamente; retorna True se for novo."""
        operation_id = observation.operation_id
        if not (classification.operation_id == evidence.operation_id == operation_id):
            raise ValueError("Os três contratos devem compartilhar o mesmo operation_id.")
        expected_id = build_swap_operation_id(
            observation.chain, observation.signature, evidence.instruction_index, evidence.cpi_path
        )
        if operation_id != expected_id:
            raise ValueError("operation_id não corresponde à identidade determinística da instrução/CPI.")
        if observation.chain.strip().lower() != "solana":
            raise ValueError("Esta versão do EventStore aceita swaps apenas da chain Solana.")
        with self._connection_scope() as connection:
            with collector_write(connection, getattr(self, "_collector_authority", None), "smart_money"):
                parent = connection.execute(
                    """SELECT 1 FROM observed_transactions
                       WHERE wallet_address = ? AND signature = ?""",
                    (observation.wallet_address, observation.signature),
                ).fetchone()
                if parent is None:
                    raise KeyError("A transação observada deve existir antes do swap.")
                previous = connection.execute(
                    "SELECT wallet_address FROM swap_observations WHERE operation_id = ?", (operation_id,)
                ).fetchone()
                if previous is not None and previous[0] != observation.wallet_address:
                    raise ValueError("operation_id já está associado a outra carteira")
                connection.execute(
                    """INSERT INTO swap_observations
                       (operation_id, chain, wallet_address, signature, input_mint, output_mint,
                        input_amount, output_amount, observed_at, parser_version)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(operation_id) DO UPDATE SET
                        chain=excluded.chain, wallet_address=excluded.wallet_address,
                        signature=excluded.signature, input_mint=excluded.input_mint,
                        output_mint=excluded.output_mint, input_amount=excluded.input_amount,
                        output_amount=excluded.output_amount, observed_at=excluded.observed_at,
                        parser_version=excluded.parser_version""",
                    (operation_id, observation.chain, observation.wallet_address,
                     observation.signature, observation.input_mint, observation.output_mint,
                     str(observation.input_amount), str(observation.output_amount),
                     observation.observed_at.isoformat(), observation.parser_version),
                )
                connection.execute(
                    """INSERT INTO swap_classifications(operation_id, side, confidence, reason)
                       VALUES (?, ?, ?, ?) ON CONFLICT(operation_id) DO UPDATE SET
                       side=excluded.side, confidence=excluded.confidence, reason=excluded.reason""",
                    (operation_id, classification.side, str(classification.confidence), classification.reason),
                )
                connection.execute(
                    """INSERT INTO swap_evidence
                       (operation_id, program_id, venue, instruction_index, cpi_path_json, evidence_json)
                       VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(operation_id) DO UPDATE SET
                       program_id=excluded.program_id, venue=excluded.venue,
                       instruction_index=excluded.instruction_index,
                       cpi_path_json=excluded.cpi_path_json, evidence_json=excluded.evidence_json""",
                    (operation_id, evidence.program_id, evidence.venue, evidence.instruction_index,
                     json.dumps(list(evidence.cpi_path), separators=(",", ":")),
                     json.dumps(list(evidence.evidence), separators=(",", ":"))),
                )
                return previous is None

    def list_swap_replay_archive(
        self, *, wallet: str, program: str, base_mint: str, quote_mint: str, pool: str | None = None,
    ) -> list[dict]:
        """Read first-seen swap evidence in durable arrival order."""
        with self._connection_scope() as connection:
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'swap_replay_archive'"
            ).fetchone() is None:
                raise ValueError("banco sem arquivo prospectivo de swaps para paper replay")
            query = """SELECT operation_id, input_mint, input_amount, output_amount, side,
                              confidence, occurred_at, available_at
                       FROM swap_replay_archive
                       WHERE wallet_address = ? AND program_id = ?
                         AND ((input_mint = ? AND output_mint = ?) OR (input_mint = ? AND output_mint = ?))"""
            params = (wallet, program, base_mint, quote_mint, quote_mint, base_mint)
            if pool is not None:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(swap_replay_archive)")}
                if "pool_address" not in columns:
                    raise ValueError("arquivo legado sem proveniência de pool")
                query += " AND pool_address = ?"
                params += (pool,)
            cursor = connection.execute(query + " ORDER BY receipt_id", params)
            columns = tuple(item[0] for item in cursor.description)
            return [dict(zip(columns, row)) for row in cursor]

    def list_wallet_discovery_receipts(self, *, limit: int = 5000) -> list[dict]:
        """Bounded raw-linked receipt snapshot, not a whole-chain wallet scan.

        Return first-publication receipts in stable receipt order. Caller must
        preserve UNKNOWN coverage and must not evaluate a truncated snapshot.
        """
        if type(limit) is not int or not 1 <= limit <= 10001:
            raise ValueError("discovery limit outside allowed bounds")
        with self._connection_scope() as connection:
            rows=connection.execute("""
                SELECT a.operation_id,a.wallet_address,s.signature,a.program_id,a.pool_address,
                       a.input_mint,a.output_mint,a.input_amount,a.output_amount,a.side,a.confidence,
                       a.occurred_at,a.available_at,o.payload_json,o.slot,o.observed_at,o.chain,
                       o.parse_status,s.wallet_address
                FROM swap_replay_archive a
                LEFT JOIN swap_observations s ON s.operation_id=a.operation_id
                LEFT JOIN observed_transactions o ON o.wallet_address=a.wallet_address AND o.signature=s.signature
                ORDER BY a.receipt_id LIMIT ?
            """,(limit,)).fetchall()
        names=("operation_id","wallet","signature","program","pool","input_mint","output_mint",
               "input_amount","output_amount","side","confidence","occurred_at","available_at",
               "payload_json","slot","observed_at","chain","parse_status","observation_wallet")
        return [dict(zip(names,r)) for r in rows]

    def list_wallet_signal_receipts(
        self, *, wallet: str, program: str, base_mint: str, quote_mint: str, pool: str,
    ) -> list[dict]:
        """Read scoped first-publication receipts with their transaction identity."""
        with self._connection_scope() as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(swap_replay_archive)")}
            if "pool_address" not in columns:
                raise ValueError("arquivo de swaps sem proveniência de pool para sinais")
            cursor = connection.execute(
                """SELECT archive.operation_id, swap.signature, archive.input_mint, archive.output_mint,
                          archive.side, archive.confidence, archive.occurred_at, archive.available_at
                   FROM swap_replay_archive AS archive
                   JOIN swap_observations AS swap ON swap.operation_id = archive.operation_id
                                                 AND swap.wallet_address = archive.wallet_address
                   WHERE archive.wallet_address = ? AND archive.program_id = ? AND archive.pool_address = ?
                     AND ((archive.input_mint = ? AND archive.output_mint = ?)
                       OR (archive.input_mint = ? AND archive.output_mint = ?))
                   ORDER BY archive.receipt_id""",
                (wallet, program, pool, base_mint, quote_mint, quote_mint, base_mint),
            )
            names = tuple(item[0] for item in cursor.description)
            return [dict(zip(names, row)) for row in cursor]

    def get_swap_bundle(self, operation_id: str) -> dict | None:
        """Recupera contratos persistidos sem perder precisão decimal."""
        with self._connection_scope() as connection:
            obs = connection.execute(
                """SELECT chain, wallet_address, signature, input_mint, output_mint,
                          input_amount, output_amount, observed_at, parser_version
                   FROM swap_observations WHERE operation_id = ?""", (operation_id,)
            ).fetchone()
            if obs is None:
                return None
            cls = connection.execute(
                "SELECT side, confidence, reason FROM swap_classifications WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            ev = connection.execute(
                """SELECT program_id, venue, instruction_index, cpi_path_json, evidence_json
                   FROM swap_evidence WHERE operation_id = ?""", (operation_id,)
            ).fetchone()
        if cls is None or ev is None:
            raise RuntimeError("Bundle de swap incompleto: classificação ou evidência ausente.")
        return {
            "observation": SwapObservation(
                operation_id=operation_id, chain=obs[0], wallet_address=obs[1], signature=obs[2],
                input_mint=obs[3], output_mint=obs[4], input_amount=Decimal(obs[5]),
                output_amount=Decimal(obs[6]), observed_at=datetime.fromisoformat(obs[7]),
                parser_version=obs[8],
            ),
            "classification": SwapClassification(
                operation_id=operation_id, side=cls[0], confidence=Decimal(cls[1]), reason=cls[2]
            ) if cls else None,
            "evidence": SwapEvidence(
                operation_id=operation_id, program_id=ev[0], venue=ev[1],
                instruction_index=ev[2], cpi_path=tuple(json.loads(ev[3])),
                evidence=tuple(json.loads(ev[4])),
            ) if ev else None,
        }

    def list_smr_archived_event_inputs(self, *, limit: int = 20) -> list[dict]:
        """Read original swap receipts with transaction RAW, not inferred live coverage.

        Returned payload bytes match exactly the JSON text persisted by this
        SQLite store. Local hashes prove integrity only, never provider trust.
        """
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        with self._connection_scope() as connection:
            rows = connection.execute(
                """SELECT archive.operation_id, archive.pool_address,
                          archive.side, archive.available_at,
                          swap.signature, swap.wallet_address,
                          observed.payload_json, observed.slot,
                          observed.observed_at, observed.chain,
                          archive.occurred_at, archive.program_id, archive.input_mint,
                          archive.output_mint, archive.confidence
                   FROM swap_replay_archive AS archive
                   JOIN swap_observations AS swap
                     ON swap.operation_id=archive.operation_id
                    AND swap.wallet_address=archive.wallet_address
                   LEFT JOIN observed_transactions AS observed
                     ON observed.wallet_address=swap.wallet_address
                    AND observed.signature=swap.signature
                   ORDER BY archive.receipt_id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [{
            "operation_id": row[0], "pool": row[1], "side": row[2],
            "available_at": row[3], "signature": row[4], "wallet": row[5],
            "raw_bytes": row[6].encode("utf-8") if row[6] is not None else None,
            "slot": row[7], "observed_at": row[8],
            "chain": row[9], "occurred_at": row[10], "program": row[11],
            "input_mint": row[12], "output_mint": row[13], "confidence": row[14],
        } for row in rows]

    def list_cpmm_launch_archived_event_inputs(self, *, limit: int = 20) -> list[dict]:
        """Join original Launch Radar RAW/detected identities, if its journal exists.

        This is intentionally optional: legacy SMR databases lack Launch tables.
        Missing tables never get created by a read-only dashboard.
        """
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        with self._connection_scope() as connection:
            tables = {r[0] for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name IN ('cpmm_launch_evidence','cpmm_launch_raw')"
            )}
            if tables != {"cpmm_launch_evidence", "cpmm_launch_raw"}:
                return []
            rows = connection.execute(
                """SELECT evidence.pool, evidence.identity, evidence.sha256,
                          raw.payload, raw.archived_at,
                          (SELECT COUNT(DISTINCT e.identity) FROM cpmm_launch_evidence e
                            WHERE e.pool=evidence.pool) AS identity_count
                   FROM cpmm_launch_evidence AS evidence
                   JOIN cpmm_launch_raw AS raw ON raw.sha256=evidence.sha256
                   ORDER BY raw.archived_at DESC, evidence.pool
                   LIMIT ?""", (limit,),
            ).fetchall()
        return [{
            "pool": row[0], "identity_json": row[1], "raw_sha256": row[2],
            "raw_bytes": bytes(row[3]), "archived_at": row[4],
            "pool_identity_conflict": row[5] > 1,
        } for row in rows]

    def get_raw_transaction(self, wallet_address: str, signature: str) -> dict | None:
        """Recupera payload bruto para auditoria e replay do parser."""
        with self._connection_scope() as connection:
            row = connection.execute(
                """SELECT payload_json FROM observed_transactions
                   WHERE wallet_address = ? AND signature = ?""",
                (wallet_address, signature),
            ).fetchone()
        if not row or row[0] is None:
            return None
        payload = json.loads(row[0])
        return payload if isinstance(payload, dict) else None

    def get_observation_metadata(self, wallet_address: str, signature: str) -> dict | None:
        """Retorna estado de parsing/versionamento sem expor o payload inteiro."""
        with self._connection_scope() as connection:
            row = connection.execute(
                """SELECT parse_status, parser_version, parse_error, observed_at, chain, slot, occurred_at
                   FROM observed_transactions
                   WHERE wallet_address = ? AND signature = ?""",
                (wallet_address, signature),
            ).fetchone()
        if row is None:
            return None
        return {
            "parse_status": row[0],
            "parser_version": row[1],
            "parse_error": row[2],
            "observed_at": row[3],
            "chain": row[4],
            "slot": row[5],
            "occurred_at": row[6],
        }

    def reprocess_observation(
        self,
        wallet_address: str,
        signature: str,
        events: list[ActivityEvent],
        *,
        parse_status: str,
        parser_version: str,
        parse_error: str | None = None,
        normalized_observation: NormalizedObservation | None = None,
    ) -> int:
        """Substitui derivados legados/normalizados sem alterar o checkpoint."""
        if not parse_status.strip() or not parser_version.strip():
            raise ValueError("Estado de parsing e versão do parser são obrigatórios.")
        if any(event.wallet_address != wallet_address or event.signature != signature for event in events):
            raise ValueError("Todos os eventos devem pertencer à observação informada.")
        if normalized_observation is not None:
            envelope = normalized_observation.transaction
            if (envelope.wallet_address, envelope.signature) != (wallet_address, signature):
                raise ValueError("Envelope normalizado não corresponde à observação informada.")
            if tuple(events) != normalized_observation.activity_events:
                raise ValueError("Eventos legados divergem do resultado normalizado.")
            parse_status = envelope.parse_status
            parser_version = envelope.parser_version
        rows = [
            (
                event.wallet_address,
                event.signature,
                event.occurred_at.isoformat() if event.occurred_at else None,
                event.token_mint,
                event.direction,
                str(event.amount),
            )
            for event in events
        ]
        with self._connection_scope() as connection:
            with collector_write(connection, getattr(self, "_collector_authority", None), "smart_money"):
                exists = connection.execute(
                    """SELECT 1 FROM observed_transactions
                       WHERE wallet_address = ? AND signature = ? AND payload_json IS NOT NULL""",
                    (wallet_address, signature),
                ).fetchone()
                if not exists:
                    raise KeyError("Observação não encontrada para reprocessamento.")
                connection.execute(
                    "DELETE FROM activity_events WHERE wallet_address = ? AND signature = ?",
                    (wallet_address, signature),
                )
                if rows:
                    connection.executemany(
                        """INSERT INTO activity_events
                           (wallet_address, signature, occurred_at, token_mint, direction, amount)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        rows,
                    )
                connection.execute(
                    """UPDATE observed_transactions
                       SET parse_status = ?, parser_version = ?, parse_error = ?,
                           chain = COALESCE(?, chain), slot = COALESCE(?, slot),
                           occurred_at = COALESCE(?, occurred_at)
                       WHERE wallet_address = ? AND signature = ?""",
                    (parse_status, parser_version, parse_error,
                     normalized_observation.transaction.chain if normalized_observation else None,
                     normalized_observation.transaction.slot if normalized_observation else None,
                     normalized_observation.transaction.occurred_at.isoformat()
                     if normalized_observation and normalized_observation.transaction.occurred_at else None,
                     wallet_address, signature),
                )
                connection.execute(
                    "DELETE FROM token_balance_deltas WHERE wallet_address = ? AND signature = ?",
                    (wallet_address, signature),
                )
                if normalized_observation is not None:
                    delta_rows = [
                        (delta.wallet_address, delta.signature, delta.chain, delta.token_mint,
                         delta.direction, str(delta.amount), delta.decimals)
                        for delta in normalized_observation.token_deltas
                    ]
                    if delta_rows:
                        connection.executemany(
                            """INSERT INTO token_balance_deltas
                               (wallet_address, signature, chain, token_mint, direction, amount, decimals)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            delta_rows,
                        )
                return len(rows)

    def get_token_deltas(
        self, wallet_address: str, signature: str
    ) -> list[TokenBalanceDelta]:
        """Recupera os deltas SPL normalizados persistidos para uma observação."""
        with self._connection_scope() as connection:
            rows = connection.execute(
                """SELECT chain, wallet_address, signature, token_mint, direction, amount, decimals
                   FROM token_balance_deltas
                   WHERE wallet_address = ? AND signature = ?
                   ORDER BY token_mint, direction""",
                (wallet_address, signature),
            ).fetchall()
        return [
            TokenBalanceDelta(
                chain=row[0], wallet_address=row[1], signature=row[2],
                token_mint=row[3], direction=row[4], amount=Decimal(row[5]), decimals=row[6],
            )
            for row in rows
        ]


    def save_swap_reconciliation_attempt(
        self,
        wallet_address: str,
        signature: str,
        records: list[SwapReconciliationRecord],
    ) -> str:
        """Acrescenta resultados por swap sem os confundir com bundles MATCHED."""
        if not wallet_address.strip() or not signature.strip():
            raise ValueError("Carteira e assinatura da reconciliação são obrigatórias.")
        if not records:
            raise ValueError("A tentativa deve conter ao menos um resultado por swap.")
        allowed = {"MATCHED", "INCOMPLETE", "AMBIGUOUS", "UNRESOLVED"}
        rows = []
        for record in records:
            if not isinstance(record, SwapReconciliationRecord):
                raise TypeError("records deve conter SwapReconciliationRecord.")
            if not record.operation_id or not record.reason.strip():
                raise ValueError("Identidade e motivo da reconciliação são obrigatórios.")
            if record.status not in allowed:
                raise ValueError("Status de reconciliação não suportado.")
            if (isinstance(record.instruction_index, bool)
                    or not isinstance(record.instruction_index, int)
                    or record.instruction_index < 0):
                raise ValueError("instruction_index deve ser inteiro não negativo.")
            if record.inner_instruction_index is not None and (
                isinstance(record.inner_instruction_index, bool)
                or not isinstance(record.inner_instruction_index, int)
                or record.inner_instruction_index < 0
            ):
                raise ValueError("inner_instruction_index inválido.")
            if any(isinstance(item, bool) or not isinstance(item, int) or item < 0
                   for item in record.cpi_path):
                raise ValueError("cpi_path deve conter índices inteiros não negativos.")
            expected_operation_id = build_swap_operation_id(
                "solana", signature, record.instruction_index, record.cpi_path
            )
            if record.operation_id != expected_operation_id:
                raise ValueError(
                    "operation_id não corresponde à identidade da instrução/CPI auditada."
                )
            rows.append((
                record.operation_id, record.instruction_index,
                record.inner_instruction_index,
                json.dumps(list(record.cpi_path), separators=(",", ":")),
                record.status, record.reason,
            ))
        attempt_id = uuid.uuid4().hex
        with self._connection_scope() as connection:
            with collector_write(connection, getattr(self, "_collector_authority", None), "smart_money"):
                parent = connection.execute(
                    "SELECT 1 FROM observed_transactions WHERE wallet_address = ? AND signature = ?",
                    (wallet_address, signature),
                ).fetchone()
                if parent is None:
                    raise KeyError("A observação pai deve existir antes da auditoria de reconciliação.")
                connection.executemany(
                    """INSERT INTO swap_reconciliation_attempts
                       (attempt_id, wallet_address, signature, operation_id,
                        instruction_index, inner_instruction_index, cpi_path_json, status, reason)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [(attempt_id, wallet_address, signature, *row) for row in rows],
                )
        return attempt_id

    def get_swap_reconciliation_attempts(
        self, wallet_address: str, signature: str
    ) -> list[dict]:
        """Lista histórico de tentativas por swap, da mais antiga à mais recente."""
        with self._connection_scope() as connection:
            rows = connection.execute(
                """SELECT attempt_id, operation_id, instruction_index,
                          inner_instruction_index, cpi_path_json, status, reason, attempted_at
                   FROM swap_reconciliation_attempts
                   WHERE wallet_address = ? AND signature = ?
                   ORDER BY id ASC""",
                (wallet_address, signature),
            ).fetchall()
        return [{
            "attempt_id": row[0], "operation_id": row[1],
            "instruction_index": row[2], "inner_instruction_index": row[3],
            "cpi_path": tuple(json.loads(row[4])), "status": row[5],
            "reason": row[6], "attempted_at": row[7],
        } for row in rows]

    def get_pending_signatures(
        self, wallet_address: str, *, limit: int = 100
    ) -> list[str]:
        """Lista observações arquivadas que ainda não concluíram o pipeline."""
        if not wallet_address.strip():
            raise ValueError("O endereço da carteira é obrigatório.")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("O limite de pendências deve ser inteiro positivo.")
        with self._connection_scope() as connection:
            rows = connection.execute(
                """SELECT observed.signature
                   FROM observed_transactions AS observed
                   LEFT JOIN processed_signatures AS processed
                     ON processed.wallet_address = observed.wallet_address
                    AND processed.signature = observed.signature
                   WHERE observed.wallet_address = ?
                     AND observed.payload_json IS NOT NULL
                     AND processed.signature IS NULL
                   ORDER BY COALESCE(observed.slot, 0) ASC,
                            observed.observed_at ASC, observed.rowid ASC
                   LIMIT ?""",
                (wallet_address, limit),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def query_swap_reconciliation_attempts(
        self,
        *,
        wallet_address: str | None = None,
        signature: str | None = None,
        operation_id: str | None = None,
        status: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Consulta tentativas auditáveis com filtros opcionais e limite explícito."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("O limite deve ser inteiro positivo.")
        if status is not None and status not in {
            "MATCHED", "INCOMPLETE", "AMBIGUOUS", "UNRESOLVED"
        }:
            raise ValueError("Status de reconciliação não suportado.")
        for name, value in (("wallet_address", wallet_address),
                            ("signature", signature),
                            ("operation_id", operation_id),
                            ("since", since), ("until", until)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} deve ser texto não vazio quando informado.")
        if since is not None and until is not None and since > until:
            raise ValueError("since não pode ser posterior a until.")

        clauses = []
        parameters: list[object] = []
        for column, value in (
            ("wallet_address", wallet_address),
            ("signature", signature),
            ("operation_id", operation_id),
            ("status", status),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        if since is not None:
            clauses.append("attempted_at >= ?")
            parameters.append(since)
        if until is not None:
            clauses.append("attempted_at <= ?")
            parameters.append(until)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.append(limit)
        with self._connection_scope() as connection:
            rows = connection.execute(
                """SELECT wallet_address, signature, attempt_id, operation_id,
                          instruction_index, inner_instruction_index, cpi_path_json,
                          status, reason, attempted_at
                   FROM swap_reconciliation_attempts"""
                + where
                + " ORDER BY id DESC LIMIT ?",
                tuple(parameters),
            ).fetchall()
        return [{
            "wallet_address": row[0], "signature": row[1],
            "attempt_id": row[2], "operation_id": row[3],
            "instruction_index": row[4], "inner_instruction_index": row[5],
            "cpi_path": tuple(json.loads(row[6])), "status": row[7],
            "reason": row[8], "attempted_at": row[9],
        } for row in rows]

    def get_reconciliation_diagnostics(
        self,
        *,
        wallet_address: str | None = None,
        since: str | None = None,
        until: str | None = None,
        top_reasons_limit: int = 10,
    ) -> dict:
        """Resume volume, status, motivos recorrentes e pendências de reconciliação."""
        if isinstance(top_reasons_limit, bool) or not isinstance(top_reasons_limit, int) or top_reasons_limit < 1:
            raise ValueError("top_reasons_limit deve ser inteiro positivo.")
        for name, value in (("wallet_address", wallet_address),
                            ("since", since), ("until", until)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} deve ser texto não vazio quando informado.")
        if since is not None and until is not None and since > until:
            raise ValueError("since não pode ser posterior a until.")

        attempt_clauses = []
        attempt_parameters: list[object] = []
        pending_clauses = ["observed.payload_json IS NOT NULL",
                           "processed.signature IS NULL"]
        pending_parameters: list[object] = []
        if wallet_address is not None:
            attempt_clauses.append("wallet_address = ?")
            attempt_parameters.append(wallet_address)
            pending_clauses.append("observed.wallet_address = ?")
            pending_parameters.append(wallet_address)
        if since is not None:
            attempt_clauses.append("attempted_at >= ?")
            attempt_parameters.append(since)
            pending_clauses.append("observed.observed_at >= ?")
            pending_parameters.append(since)
        if until is not None:
            attempt_clauses.append("attempted_at <= ?")
            attempt_parameters.append(until)
            pending_clauses.append("observed.observed_at <= ?")
            pending_parameters.append(until)
        attempt_where = (
            " WHERE " + " AND ".join(attempt_clauses) if attempt_clauses else ""
        )
        pending_where = " WHERE " + " AND ".join(pending_clauses)

        statuses = {name: 0 for name in (
            "MATCHED", "INCOMPLETE", "AMBIGUOUS", "UNRESOLVED"
        )}
        with self._connection_scope() as connection:
            totals = connection.execute(
                """SELECT COUNT(*), COUNT(DISTINCT operation_id),
                          COUNT(DISTINCT signature)
                   FROM swap_reconciliation_attempts""" + attempt_where,
                tuple(attempt_parameters),
            ).fetchone()
            status_rows = connection.execute(
                """SELECT status, COUNT(*) FROM swap_reconciliation_attempts"""
                + attempt_where + " GROUP BY status",
                tuple(attempt_parameters),
            ).fetchall()
            reason_rows = connection.execute(
                """SELECT reason, COUNT(*) AS occurrences
                   FROM swap_reconciliation_attempts"""
                + attempt_where
                + """ GROUP BY reason
                    ORDER BY occurrences DESC, reason ASC LIMIT ?""",
                tuple(attempt_parameters + [top_reasons_limit]),
            ).fetchall()
            pending_count = connection.execute(
                """SELECT COUNT(*) FROM observed_transactions AS observed
                   LEFT JOIN processed_signatures AS processed
                     ON processed.wallet_address = observed.wallet_address
                    AND processed.signature = observed.signature"""
                + pending_where,
                tuple(pending_parameters),
            ).fetchone()[0]
            pending_rows = connection.execute(
                """SELECT observed.wallet_address, observed.signature,
                          observed.parse_status, observed.observed_at
                   FROM observed_transactions AS observed
                   LEFT JOIN processed_signatures AS processed
                     ON processed.wallet_address = observed.wallet_address
                    AND processed.signature = observed.signature"""
                + pending_where
                + """ ORDER BY COALESCE(observed.slot, 0) ASC,
                             observed.observed_at ASC, observed.rowid ASC LIMIT 100""",
                tuple(pending_parameters),
            ).fetchall()
        statuses.update({str(row[0]): int(row[1]) for row in status_rows})
        return {
            "total_attempts": int(totals[0]),
            "distinct_operations": int(totals[1]),
            "distinct_signatures": int(totals[2]),
            "statuses": statuses,
            "top_reasons": [
                {"reason": str(row[0]), "count": int(row[1])}
                for row in reason_rows
            ],
            "pending_transactions_count": int(pending_count),
            "pending_transactions": [
                {"wallet_address": row[0], "signature": row[1],
                 "parse_status": row[2], "observed_at": row[3]}
                for row in pending_rows
            ],
        }

    def get_checkpoint(self, wallet_address: str) -> str | None:
        """Retorna a última assinatura processada com sucesso para a carteira."""
        with self._connection_scope() as connection:
            row = connection.execute(
                "SELECT signature FROM wallet_checkpoints WHERE wallet_address = ?",
                (wallet_address,),
            ).fetchone()
        return row[0] if row else None

    def has_processed_signature(self, wallet_address: str, signature: str) -> bool:
        """Evita reprocessar notificações WebSocket já cobertas pelo backfill."""
        with self._connection_scope() as connection:
            row = connection.execute(
                "SELECT 1 FROM processed_signatures WHERE wallet_address = ? AND signature = ?",
                (wallet_address, signature),
            ).fetchone()
        return row is not None

    def save_checkpoint(self, wallet_address: str, signature: str) -> None:
        """Legacy signature-only cursor, rejected when captured evidence exists.

        Preserve historical bootstrap/checkpoint semantics without falsely
        creating an observed transaction or declaring evidence authenticated.
        """
        if not wallet_address.strip() or not signature.strip():
            raise ValueError("Carteira e assinatura do checkpoint são obrigatórias.")
        with self._connection_scope() as connection:
            with collector_write(connection, getattr(self, "_collector_authority", None), "smart_money"):
                self._cm38_link_in_connection(
                    connection, radar="smart_money", wallet_address=wallet_address,
                    signature=signature, evidence_id=None, kind="wallet_transaction",
                    operation_id=signature, commitment="confirmed",
                    source_id="helius-wallet-rpc",
                )
                connection.execute(
                    "INSERT OR IGNORE INTO processed_signatures (wallet_address, signature) VALUES (?, ?)",
                    (wallet_address, signature),
                )
                connection.execute(
                    """INSERT INTO wallet_checkpoints(wallet_address,signature) VALUES (?,?)
                       ON CONFLICT(wallet_address) DO UPDATE SET
                       signature=excluded.signature,updated_at=CURRENT_TIMESTAMP""",
                    (wallet_address, signature),
                )


    def integrity_check(self) -> list[str]:
        """Executa a verificação nativa de integridade do SQLite."""
        with self._connection_scope() as connection:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
        return [str(row[0]) for row in rows]

    def storage_stats(self) -> dict[str, int | str]:
        """Retorna contagens e tamanho do banco sem expor payloads."""
        with self._connection_scope() as connection:
            counts = {}
            for table in ("activity_events", "observed_transactions", "token_balance_deltas",
                          "processed_signatures", "wallet_checkpoints",
                          "swap_reconciliation_attempts"):
                counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
            page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        size_bytes = page_count * page_size
        return {**counts, "page_count": page_count, "page_size": page_size, "database_bytes": size_bytes}

    def backup_to(self, destination: Path | str) -> Path:
        """Cria backup consistente por meio da API online-backup do SQLite."""
        target = Path(destination).expanduser()
        if str(self.database_path) != ":memory:" and target.resolve() == self.database_path.resolve():
            raise ValueError("O destino do backup não pode ser o próprio banco de dados.")
        target.parent.mkdir(parents=True, exist_ok=True)
        backup_connection = sqlite3.connect(target, timeout=15.0)
        try:
            with self._connection_scope() as source_connection:
                source_connection.backup(backup_connection)
            result = backup_connection.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise sqlite3.DatabaseError("O backup não passou na verificação de integridade.")
        finally:
            backup_connection.close()
        return target

    def get_events(
        self, *, wallet_address: str | None = None, limit: int = 100
    ) -> list[ActivityEvent]:
        if limit < 1:
            raise ValueError("O limite deve ser maior que zero.")
        query = """
            SELECT wallet_address, signature, occurred_at, token_mint, direction, amount
            FROM activity_events
        """
        parameters: tuple[object, ...]
        if wallet_address is not None:
            query += " WHERE wallet_address = ?"
            parameters = (wallet_address, limit)
        else:
            parameters = (limit,)
        query += " ORDER BY occurred_at DESC, id DESC LIMIT ?"
        with self._connection_scope() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            ActivityEvent(
                wallet_address=row[0],
                signature=row[1],
                occurred_at=datetime.fromisoformat(row[2]) if row[2] else None,
                token_mint=row[3],
                direction=row[4],
                amount=Decimal(row[5]),
            )
            for row in rows
        ]