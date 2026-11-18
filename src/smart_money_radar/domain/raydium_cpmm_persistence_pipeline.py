"""Orquestra a reconstrução CPMM e a persistência SQLite sem perder checkpoints.

Este adaptador não envia transações e não decide entradas financeiras. Ele apenas
arquiva transações observadas, reconcilia swaps Raydium CPMM e persiste evidências.
"""
from dataclasses import dataclass, replace
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
from smart_money_radar.domain.models import build_swap_operation_id
from smart_money_radar.domain.normalization import normalize_transaction
from smart_money_radar.domain.swap_bundle_builder import (
    SwapDomainBundle,
    build_swap_domain_bundles,
)
from smart_money_radar.storage.event_store import (
    SQLiteEventStore,
    SwapReconciliationRecord,
)


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
    advance_checkpoint: bool = True,
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
    if not isinstance(advance_checkpoint, bool):
        raise TypeError("advance_checkpoint deve ser bool.")
    timestamp = observed_at or datetime.now(timezone.utc)
    payload = _rpc_payload(raw_transaction)
    transaction = payload.get("transaction")
    signatures = transaction.get("signatures") if isinstance(transaction, dict) else None
    if (
        not isinstance(signatures, list)
        or not signatures
        or any(not isinstance(item, str) or not item for item in signatures)
        or len(set(signatures)) != len(signatures)
        or signatures[0] != signature
    ):
        raise ValueError(
            "A assinatura informada deve corresponder à primeira assinatura única do payload RPC."
        )

    try:
        normalized = normalize_transaction(
            payload, wallet_address, signature, observed_at=timestamp
        )
    except Exception as exc:
        # Guarda o payload bruto para replay, mas não avança o cursor.
        store.save_observation(
            wallet_address, signature, payload, [],
            parse_status="parse_error", parser_version="1",
            parse_error=type(exc).__name__,
            advance_checkpoint=False,
        )
        raise

    store.save_observation(
        wallet_address,
        signature,
        payload,
        list(normalized.activity_events),
        parse_status=normalized.transaction.parse_status,
        parser_version=normalized.transaction.parser_version,
        normalized_observation=normalized,
        advance_checkpoint=False,
    )

    meta = payload.get("meta")
    if isinstance(meta, dict) and meta.get("err") is not None:
        store.mark_processed(wallet_address, signature, advance_checkpoint=advance_checkpoint)
        return RaydiumCpmmPipelineResult(
            "failed_on_chain", signature, 0, 0, 0, 0, True
        )

    try:
        swaps = decode_raydium_cpmm_swaps(payload)
        if not swaps:
            store.mark_processed(wallet_address, signature, advance_checkpoint=advance_checkpoint)
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
        swap_keys = [
            (
                swap.instruction_index,
                swap.inner_instruction_index,
                tuple(swap.cpi_path),
            )
            for swap in swaps
        ]
        reconciliation_keys = [
            (
                item.swap.instruction_index,
                item.swap.inner_instruction_index,
                tuple(item.swap.cpi_path),
            )
            for item in reconciliations
        ]
        # Equal cardinality is insufficient: duplicate reconciliation records
        # could otherwise hide a different decoded swap with no result.
        reconciliation_identity_mismatch = (
            len(set(swap_keys)) != len(swap_keys)
            or len(set(reconciliation_keys)) != len(reconciliation_keys)
            or set(reconciliation_keys) != set(swap_keys)
        )

        # Persist every decoded swap's outcome independently from positive bundles.
        # A missing reconciler result is explicit UNRESOLVED evidence, never a pass.
        reconciled_keys = set()
        audit_records: list[SwapReconciliationRecord] = []
        for item in reconciliations:
            swap = item.swap
            key = (
                swap.instruction_index,
                swap.inner_instruction_index,
                tuple(swap.cpi_path),
            )
            reconciled_keys.add(key)
            audit_records.append(SwapReconciliationRecord(
                operation_id=build_swap_operation_id(
                    "solana", signature, swap.instruction_index, tuple(swap.cpi_path)
                ),
                instruction_index=swap.instruction_index,
                inner_instruction_index=swap.inner_instruction_index,
                cpi_path=tuple(swap.cpi_path),
                status=item.status,
                reason=item.reason,
            ))
        for swap in swaps:
            key = (
                swap.instruction_index,
                swap.inner_instruction_index,
                tuple(swap.cpi_path),
            )
            if key in reconciled_keys:
                continue
            audit_records.append(SwapReconciliationRecord(
                operation_id=build_swap_operation_id(
                    "solana", signature, swap.instruction_index, tuple(swap.cpi_path)
                ),
                instruction_index=swap.instruction_index,
                inner_instruction_index=swap.inner_instruction_index,
                cpi_path=tuple(swap.cpi_path),
                status="UNRESOLVED",
                reason="O reconciliador não retornou resultado para este swap decodificado.",
            ))
        store.save_swap_reconciliation_attempt(
            wallet_address, signature, audit_records
        )
        reconciliation_count_mismatch = (
            len(reconciliations) != len(swaps)
            or reconciliation_identity_mismatch
        )

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
        expected_bundle_ids = {
            build_swap_operation_id(
                "solana", signature, item.swap.instruction_index,
                tuple(item.swap.cpi_path),
            )
            for item in matched
        }
        actual_bundle_ids = [
            bundle.observation.operation_id for bundle in bundles
        ]
        bundle_identity_mismatch = (
            len(actual_bundle_ids) != len(set(actual_bundle_ids))
            or set(actual_bundle_ids) != expected_bundle_ids
            or any(
                bundle.observation.chain != "solana"
                or bundle.observation.wallet_address != wallet_address
                or bundle.observation.signature != signature
                or bundle.classification.operation_id != bundle.observation.operation_id
                or bundle.evidence.operation_id != bundle.observation.operation_id
                for bundle in bundles
            )
        )
        unresolved = max(
            0,
            len(swaps) - len(matched),
            len(reconciliations) - len(matched),
            1 if reconciliation_identity_mismatch else 0,
            1 if bundle_identity_mismatch else 0,
        )
        saved = 0
        for bundle in bundles:
            if store.save_swap_bundle(
                bundle.observation, bundle.classification, bundle.evidence
            ):
                saved += 1

        # Fail closed: if a decoder result was not represented by a bundle,
        # or any reconciliation was unresolved, leave the observation replayable.
        if (
            unresolved
            or reconciliation_count_mismatch
            or bundle_identity_mismatch
            or len(bundles) != len(matched)
        ):
            return RaydiumCpmmPipelineResult(
                "pending_reconciliation",
                signature,
                len(swaps),
                len(matched),
                unresolved + max(0, len(matched) - len(bundles)),
                saved,
                False,
            )

        store.mark_processed(wallet_address, signature, advance_checkpoint=advance_checkpoint)
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
        failed_transaction = replace(
            normalized.transaction, parse_status="parse_error"
        )
        failed_normalized = replace(
            normalized, transaction=failed_transaction
        )
        store.reprocess_observation(
            wallet_address,
            signature,
            list(normalized.activity_events),
            parse_status="parse_error",
            parser_version=normalized.transaction.parser_version,
            parse_error=type(exc).__name__,
            normalized_observation=failed_normalized,
        )
        raise
