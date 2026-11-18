"""Armazenamento histórico SQLite, com deduplicação local de eventos."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from smart_money_radar.domain.models import (\n    ActivityEvent, SwapClassification, SwapEvidence, SwapObservation, TokenBalanceDelta,\n)
from smart_money_radar.domain.normalization import NormalizedObservation


class SQLiteEventStore:
    """Persiste eventos sem armazenar chaves ou credenciais."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self._memory_connection: sqlite3.Connection | None = None
        if str(self.database_path) == ":memory:":
            # Keep one connection alive: a fresh SQLite :memory: connection is
            # a different database and would lose the schema/data immediately.
            self._memory_connection = sqlite3.connect(":memory:")
        else:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            return self._memory_connection
        connection = sqlite3.connect(self.database_path, timeout=15.0)
        connection.execute("PRAGMA busy_timeout = 15000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

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
                        observed_at TEXT NOT NULL, parser_version TEXT NOT NULL)"""
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
            with connection:
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
    ) -> int:
        """Persiste payload, contratos normalizados, eventos e checkpoint atomicamente.

        O payload bruto permite replay quando o parser ganhar cobertura nova.
        Para falhas on-chain, transaction pode ser None e parse_status deve
        identificar explicitamente o resultado conhecido.
        """
        if not wallet_address.strip() or not signature.strip():
            raise ValueError("Carteira e assinatura da observação são obrigatórias.")
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
            with connection:
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
                connection.execute(
                    """
                    INSERT OR IGNORE INTO processed_signatures (wallet_address, signature)
                    VALUES (?, ?)
                    """,
                    (wallet_address, signature),
                )
                connection.execute(
                    """
                    INSERT INTO wallet_checkpoints (wallet_address, signature)
                    VALUES (?, ?)
                    ON CONFLICT(wallet_address) DO UPDATE SET
                        signature = excluded.signature,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (wallet_address, signature),
                )
                return inserted

    def save_swap_bundle(
        self, observation: SwapObservation, classification: SwapClassification,
        evidence: SwapEvidence,
    ) -> bool:
        """Grava os três contratos atomicamente; retorna True se for novo."""
        operation_id = observation.operation_id
        if not (classification.operation_id == evidence.operation_id == operation_id):
            raise ValueError("Os três contratos devem compartilhar o mesmo operation_id.")
        with self._connection_scope() as connection:
            with connection:
                parent = connection.execute(
                    """SELECT 1 FROM observed_transactions
                       WHERE wallet_address = ? AND signature = ?""",
                    (observation.wallet_address, observation.signature),
                ).fetchone()
                if parent is None:
                    raise KeyError("A transação observada deve existir antes do swap.")
                existed = connection.execute(
                    "SELECT 1 FROM swap_observations WHERE operation_id = ?", (operation_id,)
                ).fetchone() is not None
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
                return not existed

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
            with connection:
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
        """Registra assinatura processada e atualiza o cursor mais recente conhecido."""
        if not wallet_address.strip() or not signature.strip():
            raise ValueError("Carteira e assinatura do checkpoint são obrigatórias.")
        with self._connection_scope() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO processed_signatures (wallet_address, signature)
                    VALUES (?, ?)
                    """,
                    (wallet_address, signature),
                )
                connection.execute(
                    """
                    INSERT INTO wallet_checkpoints (wallet_address, signature)
                    VALUES (?, ?)
                    ON CONFLICT(wallet_address) DO UPDATE SET
                        signature = excluded.signature,
                        updated_at = CURRENT_TIMESTAMP
                    """,
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
                          "processed_signatures", "wallet_checkpoints"):
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