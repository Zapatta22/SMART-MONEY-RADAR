"""Replay-safe read-only projection of SQLite first-publication swap receipts.

This is NOT a finalized swap or observed executable quote. It never promotes
database-local payload bytes into authenticated RPC evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from smart_money_radar.services.market_volume_audit import SwapVolumeEvidence, VolumeAuditResult, audit_swap_volume
from smart_money_radar.storage.event_store import SQLiteEventStore


@dataclass(frozen=True)
class ArchivedMarketSnapshot:
    as_of: datetime
    volume: VolumeAuditResult
    receipts_seen: int
    receipts_in_window: int
    excluded_receipts: tuple[tuple[str, str], ...]
    evidence_ids: tuple[str, ...]
    historical_coverage: Literal["UNKNOWN"] = "UNKNOWN"
    quote_provenance: Literal["NO_EXECUTABLE_QUOTE"] = "NO_EXECUTABLE_QUOTE"
    provider_authenticated: bool = False


def _utc(value: str, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} inválido")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} inválido") from exc
    if dt.utcoffset() is None:
        raise ValueError(f"{label} sem fuso")
    return dt.astimezone(timezone.utc)


def archived_volume_at(
    store: SQLiteEventStore, *, wallets: tuple[str, ...], program: str,
    pool: str, token_mint: str, quote_mint: str, as_of: datetime,
    window: timedelta, min_confidence: Decimal = Decimal("0.80"),
) -> ArchivedMarketSnapshot:
    """Read existing SQLite receipts in a fixed scope without look-ahead.

    The existing receipt table does not contain an independently attested slot,
    RPC finalization proof, RAW provider bytes or market quote. A synthetic
    canonical tuple digest is *only local receipt integrity*, never an RPC hash.
    """
    if not isinstance(store, SQLiteEventStore):
        raise TypeError("SQLiteEventStore obrigatório")
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("as_of requer fuso")
    if not isinstance(wallets, tuple) or not wallets or len(set(wallets)) != len(wallets):
        raise ValueError("carteiras distintas obrigatórias")
    if not all(isinstance(w, str) and w.strip() for w in wallets):
        raise ValueError("carteiras inválidas")
    if not all(isinstance(x, str) and x.strip() for x in (program, pool, token_mint, quote_mint)):
        raise ValueError("identidade de fonte/pool/mints obrigatória")
    if token_mint == quote_mint or not isinstance(window, timedelta) or window <= timedelta(0):
        raise ValueError("escopo ou janela inválidos")
    if not isinstance(min_confidence, Decimal) or not min_confidence.is_finite() or not 0 <= min_confidence <= 1:
        raise ValueError("confiança mínima inválida")
    if store.integrity_check() != ["ok"]:
        raise RuntimeError("SQLite não passou em integrity_check")
    point = as_of.astimezone(timezone.utc)
    seen = 0
    scoped = []
    excluded: list[tuple[str, str]] = []
    collected: set[str] = set()
    for wallet in sorted(wallets):
        rows = store.list_wallet_signal_receipts(
            wallet=wallet, program=program, pool=pool,
            base_mint=token_mint, quote_mint=quote_mint,
        )
        for row in rows:
            seen += 1
            operation_id = row["operation_id"]
            available = _utc(row["available_at"], "available_at")
            occurred = _utc(row["occurred_at"], "occurred_at")
            if occurred > available:
                raise ValueError("recibo com tempo de evento posterior à disponibilidade")
            if available > point:
                excluded.append((operation_id, "not_yet_available"))
                continue
            if occurred < point - window:
                excluded.append((operation_id, "outside_window"))
                continue
            confidence = Decimal(row["confidence"])
            if not confidence.is_finite() or not 0 <= confidence <= 1:
                raise ValueError("confiança inválida no recibo")
            if confidence < min_confidence:
                excluded.append((operation_id, "low_confidence"))
                continue
            signature = row["signature"]
            if not isinstance(signature, str) or not signature.strip():
                raise ValueError("assinatura inválida")
            if operation_id in collected:
                excluded.append((operation_id, "duplicate_operation"))
                continue
            collected.add(operation_id)
            side = "BUY" if row["input_mint"] == quote_mint else "SELL"
            if row["side"] != side:
                excluded.append((operation_id, "direction_conflict"))
                continue
            # The receipt alone does not carry authenticated on-chain slot,
            # RAW provenance or commitment. Do not invent any of them.
            scoped.append((wallet, operation_id, signature, occurred, available, side))
    # One signature can contain multiple independent swap operations; the
    # existing volume audit aggregates by signature, therefore exclude such
    # cases instead of pretending the total is economically complete.
    signatures: dict[str, list[tuple]] = {}
    for record in scoped:
        signatures.setdefault(record[2], []).append(record)
    items: list[SwapVolumeEvidence] = []
    for signature, rows in sorted(signatures.items()):
        if len(rows) != 1:
            excluded.extend((r[1], "signature_multiplicity_ambiguous") for r in rows)
            continue
        wallet, operation_id, sig, occurred, available, side = rows[0]
        # No trustworthy quote amount or RAW RPC bytes in the selected receipt
        # contract. Deliberately do not fabricate a SwapVolumeEvidence object.
        excluded.append((operation_id, "no_authenticated_quote_or_raw"))
    # A volume result with no evidence is explicitly UNKNOWN; none are fabricated.
    audit = audit_swap_volume(
        tuple(items), pool=pool, token_mint=token_mint,
        quote_mint=quote_mint, as_of=point, window=window,
    )
    return ArchivedMarketSnapshot(
        as_of=point, volume=audit, receipts_seen=seen,
        receipts_in_window=len(scoped),
        excluded_receipts=tuple(sorted(excluded)),
        evidence_ids=(),
    )
