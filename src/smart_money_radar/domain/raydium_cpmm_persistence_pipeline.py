"""Orquestra a reconstrução CPMM e a persistência SQLite sem perder checkpoints.

Este adaptador não envia transações e não decide entradas financeiras. Ele apenas
arquiva transações observadas, reconcilia swaps Raydium CPMM e persiste evidências.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
from smart_money_radar.data_sources.raydium_cpmm_transfer_reconciliation import (
    RaydiumCpmmSwapReconciliation,
    reconcile_raydium_cpmm_swaps,
)
from smart_money_radar.data_sources.solana_token_balance_deltas import (
    decode_token_account_balance_deltas,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    decode_solana_token_transfers,
)
from smart_money_radar.domain.normalization import normalize_transaction
from smart_money_radar.domain.swap_bundle_builder import (
    SwapDomainBundle,
    build_swap_domain_bundles,
)
from smart_money_radar.storage.event_store import SQLiteEventStore


@dataclass(frozen=True)
class RaydiumCpmmPipelineResult:
    """Resultado de processamento; pending significa que o checkpoint não avançou."""

    status: str
    signature: str
    decoded_swaps: int
    matched_swaps: int
    unresolved_swaps: int
    saved_bundles: int
    checkpoint_advanced: bool


def _rpc_payload(raw_transaction: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_transaction, dict):
        raise TypeError("A transação RPC deve ser um objeto.")
    payload = raw_transaction.get("result", raw_transaction)
    if not isinstance(payload, dict):
        raise ValueError("O resultado RPC não contém um payload de transação válido.")
    return payload


def process_raydium_cpmm_observation(
    store: SQLiteEventStore,
    raw_transaction: dict[str, Any],
    *,
    wallet_address: str,
    signature: str,
    reference_mints: tuple[str, ...] | list[str] = (),
    observed_at: datetime | None = None,
) -> RaydiumCpmmPipelineResult:
    """Arquiva, reconcilia e persiste uma transação Solana observada.

    O checkpoint só avança quando:
    - a transação falhou on-chain ou não contém swaps CPMM; ou
    - todos os swaps CPMM decodificados foram reconciliados como MATCHED e
      todos os bundles foram persistidos.

    Se qualquer swap ficar INCOMPLETE/AMBIGUOUS, os bundles MATCHED são mantidos
    (gravação idempotente) e a transação permanece pendente para replay/auditoria.
    """
    if not isinstance(wallet_address, str) or not wallet_address.strip():
        raise ValueError("wallet_address é obrigatório.")
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError("signature é obrigatória.")
    if not isinstance(reference_mints, (tuple, list)):
        raise TypeError("reference_mints deve ser uma lista ou tupla.")
    timestamp = observed_at or datetime.now(timezone.utc)
    payload = _rpc_payload(raw_transaction)

    try:
        normalized = normalize_transaction(
            payload, wallet_address, signature, observed_at=timestamp
        )
    except Exception as exc:
        # Guarda o payload bruto para replay, mas não avança o cursor.
        store.save_observation(
            wallet_address, signature, payload, [],
            parse_status="parse_error", parser_version="1",
            parse_error=f"{type(exc).__name__}: {exc}",
            advance_checkpoint=False,
        )
        raise

    store.save_observation(
        wallet_address,
        signature,
        payload,
        list(normalized.activity_events),
        normalized_observation=normalized,
        advance_checkpoint=False,
    )

    meta = payload.get("meta")
    if isinstance(meta, dict) and meta.get("err") is not None:
        store.mark_processed(wallet_address, signature)
        return RaydiumCpmmPipelineResult(
            "failed_on_chain", signature, 0, 0, 0, 0, True
        )

    try:
        swaps = decode_raydium_cpmm_swaps(payload)
        if not swaps:
            store.mark_processed(wallet_address, signature)
            return RaydiumCpmmPipelineResult(
                "no_cpmm_swaps", signature, 0, 0, 0, 0, True
            )

        transfers = decode_solana_token_transfers(payload)
        deltas = decode_token_account_balance_deltas(
            payload, include_unchanged=True
        )
        reconciliations = reconcile_raydium_cpmm_swaps(
            swaps, transfers, deltas, monitored_wallet=wallet_address
        )
        matched = [
            item for item in reconciliations if item.status == "MATCHED"
        ]
        unresolved = len(reconciliations) - len(matched)

        bundles: list[SwapDomainBundle] = build_swap_domain_bundles(
            matched,
            chain="solana",
            signature=signature,
            monitored_wallet=wallet_address,
            observed_at=normalized.transaction.occurred_at
            or normalized.transaction.observed_at,
            parser_version=normalized.transaction.parser_version,
            reference_mints=reference_mints,
        )
        saved = 0
        for bundle in bundles:
            if store.save_swap_bundle(
                bundle.observation, bundle.classification, bundle.evidence
            ):
                saved += 1

        # Fail closed: if a decoder result was not represented by a bundle,
        # or any reconciliation was unresolved, leave the observation replayable.
        if unresolved or len(bundles) != len(matched):
            return RaydiumCpmmPipelineResult(
                "pending_reconciliation",
                signature,
                len(swaps),
                len(matched),
                unresolved + max(0, len(matched) - len(bundles)),
                saved,
                False,
            )

        store.mark_processed(wallet_address, signature)
        return RaydiumCpmmPipelineResult(
            "processed",
            signature,
            len(swaps),
            len(matched),
            0,
            saved,
            True,
        )
    except Exception as exc:
        # Preserve an explicit parse/reconstruction error and keep checkpoint
        # untouched. The raw payload remains available for replay.
        store.reprocess_observation(
            wallet_address,
            signature,
            list(normalized.activity_events),
            parse_status="parse_error",
            parser_version=normalized.transaction.parser_version,
            parse_error=f"{type(exc).__name__}: {exc}",
            normalized_observation=normalized,
        )
        raise
