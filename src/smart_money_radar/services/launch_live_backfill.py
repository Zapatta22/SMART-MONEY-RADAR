"""Read-only Solana CPMM launch recovery using bounded finalized RPC history.

This consumes *explicitly monitored public addresses*, not all Solana launches.
A checkpoint advances only with the matching RAW and on-chain evidence in SQLite.
No live trading or implicit network access.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol

from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.storage.collector_authority import check_collector, await_authorized
from smart_money_radar.services.rpc_capture_bridge import collect_transaction_with_evidence


class SolanaLaunchRPC(Protocol):
    async def get_finalized_signatures_for_address_async(
        self, wallet_address: str, *, limit: int = 100,
        before: str | None = None,
    ) -> list[dict[str, Any]]: ...

    async def get_finalized_transaction_async(self, signature: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class LaunchBackfillResult:
    address: str
    new_deliveries: int
    latest_signature: str | None
    first_run: bool
    coverage: str


class LaunchBackfillGap(RuntimeError):
    """Not enough trustworthy history to advance a launch checkpoint."""


class FinalizedLaunchBackfill:
    """Bounded, stop-on-gap replay. Caller supplies a finalized-only RPC adapter.

    Signature listing is newest-first and page bounded. To avoid consuming an
    incomplete listing as truth, the persisted checkpoint must be found. On
    first run only the newest page may be baselined; prior history is UNKNOWN.
    """

    def __init__(
        self, rpc: SolanaLaunchRPC, store: SQLiteEventStore, *, source_id: str,
        page_size: int = 100, max_pages: int = 10,
    ) -> None:
        if not isinstance(source_id, str) or not source_id.strip() or len(source_id) > 160:
            raise ValueError("source_id inválido")
        if type(page_size) is not int or not 1 <= page_size <= 1000:
            raise ValueError("page_size inválido")
        if type(max_pages) is not int or not 1 <= max_pages <= 100:
            raise ValueError("max_pages inválido")
        self.rpc = rpc
        self.store = store
        self.source_id = source_id
        self.page_size = page_size
        self.max_pages = max_pages

    @staticmethod
    def _address(address: str) -> str:
        if not isinstance(address, str) or not address.strip():
            raise ValueError("endereço público obrigatório")
        return address

    def _source(self, address: str) -> str:
        return f"{self.source_id}:{address}"

    async def synchronize(self, address: str, *, stop_event: asyncio.Event | None = None) -> LaunchBackfillResult:
        check_collector(self.store,"launch")
        address = self._address(address)
        source = self._source(address)
        cursor = self.store.get_cpmm_launch_rpc_cursor(source)
        checkpoint = cursor["signature"] if cursor is not None else None
        collected: list[dict[str, Any]] = []
        previous_page_last = None
        seen = set()
        last_slot = None
        found_checkpoint = False
        before = None
        for page_index in range(self.max_pages):
            if stop_event is not None and stop_event.is_set():
                raise LaunchBackfillGap("coleta interrompida; cursor preservado")
            page = await await_authorized(self.store,"launch",lambda:self.rpc.get_finalized_signatures_for_address_async(
                address, limit=self.page_size, before=before,
            ))
            check_collector(self.store,"launch")
            if not isinstance(page, list) or len(page) > self.page_size:
                raise LaunchBackfillGap("página de assinaturas inválida")
            if not page:
                if checkpoint is not None:
                    raise LaunchBackfillGap("checkpoint não encontrado no histórico retornado")
                break
            signatures = []
            for item in page:
                if (not isinstance(item, dict) or not isinstance(item.get("signature"), str)
                        or not item["signature"] or type(item.get("slot")) is not int
                        or item["slot"] < 0):
                    raise LaunchBackfillGap("identidade incompleta na página de assinaturas")
                if item["signature"] in seen or (last_slot is not None and item["slot"] > last_slot):
                    raise LaunchBackfillGap("paginação sobreposta ou slot regressivo")
                seen.add(item["signature"])
                last_slot = item["slot"]
                signatures.append(item["signature"])
            if len(signatures) != len(set(signatures)):
                raise LaunchBackfillGap("assinaturas duplicadas na mesma página")
            if previous_page_last is not None and signatures[0] == previous_page_last:
                raise LaunchBackfillGap("paginação RPC sobreposta")
            if checkpoint is not None and checkpoint in signatures:
                found_checkpoint = True
                collected.extend(page[:signatures.index(checkpoint)])
                break
            collected.extend(page)
            if checkpoint is None:
                # First-run history policy: bounded first page only.
                break
            if len(page) < self.page_size:
                raise LaunchBackfillGap("checkpoint ausente em página terminal")
            if page_index == self.max_pages - 1:
                raise LaunchBackfillGap("limite de backfill atingido antes do checkpoint")
            previous_page_last = signatures[-1]
            before = previous_page_last
        if checkpoint is not None and not found_checkpoint:
            raise LaunchBackfillGap("checkpoint não comprovado no backfill")
        if not collected:
            return LaunchBackfillResult(address, 0, checkpoint, cursor is None, "UNKNOWN")

        # Fetch every transaction BEFORE any checkpoint update. The archive
        # operation is atomic, including when a transaction fails on-chain.
        raws = []
        for entry in reversed(collected):
            if stop_event is not None and stop_event.is_set():
                raise LaunchBackfillGap("coleta interrompida; cursor preservado")
            sig = entry["signature"]
            check_collector(self.store,"launch")
            transaction = await collect_transaction_with_evidence(self.store,self.rpc,radar="launch",signature=sig,
                source_id=source,commitment="finalized",expected_slot=entry["slot"],
                legacy=lambda:self.rpc.get_finalized_transaction_async(sig))
            check_collector(self.store,"launch")
            if transaction is None or not isinstance(transaction, dict):
                raise LaunchBackfillGap("transação indisponível; cursor preservado")
            tx_body = transaction.get("transaction")
            meta = transaction.get("meta")
            if not isinstance(tx_body, dict) or not isinstance(meta, dict) or "err" not in meta:
                raise LaunchBackfillGap("transação incompleta; cursor preservado")
            if "err" in entry and entry["err"] != meta["err"]:
                raise LaunchBackfillGap("estado de execução divergente")
            signatures = tx_body.get("signatures")
            if not isinstance(signatures, list) or not signatures or signatures[0] != sig:
                raise LaunchBackfillGap("assinatura divergente na transação")
            if transaction.get("slot") != entry["slot"]:
                raise LaunchBackfillGap("slot divergente entre listagem e transação")
            raws.append(json.dumps(
                {"result": transaction}, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8"))

        if stop_event is not None and stop_event.is_set():
            raise LaunchBackfillGap("coleta interrompida; cursor preservado")
        start_sequence = cursor["last_sequence"] + 1 if cursor is not None else 0
        # An existing cursor and an RPC signature are updated in one transaction.
        self.store.archive_cpmm_launch_rpc_batch(
            raws, source_id=source, first_sequence=start_sequence,
            expected_signature=checkpoint,
            latest_signature=collected[0]["signature"],
        )
        return LaunchBackfillResult(address, len(raws), collected[0]["signature"],
                                    cursor is None, "UNKNOWN")
