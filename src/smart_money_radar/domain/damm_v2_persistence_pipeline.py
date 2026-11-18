"""Persistência fail-closed do pipeline DAMM v2 sem avançar checkpoint.

A coordenação do checkpoint permanece no pipeline multi-venue do monitor:
este adaptador pode persistir bundles e tentativas, mas nunca marca a
transação como processada.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from smart_money_radar.domain.models import build_swap_operation_id
from smart_money_radar.domain.normalization import normalize_transaction
from smart_money_radar.data_sources.damm_v2_transaction_pipeline import (
    process_damm_v2_transaction,
)
from smart_money_radar.storage.event_store import (
    SQLiteEventStore,
    SwapReconciliationRecord,
)


@dataclass(frozen=True)
class DammV2PersistenceResult:
    status: str
    signature: str
    decoded_swaps: int
    reconciled_swaps: int
    unresolved_swaps: int
    saved_bundles: int
    ready_for_next_venue: bool


def _payload(raw_transaction: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_transaction, dict):
        raise TypeError("A transação RPC deve ser um objeto.")
    payload = raw_transaction.get("result", raw_transaction)
    if not isinstance(payload, dict):
        raise ValueError("Payload RPC inválido.")
    return payload


def process_damm_v2_observation(
    store: SQLiteEventStore,
    raw_transaction: dict[str, Any],
    *,
    wallet_address: str,
    signature: str,
    observed_at: datetime | None = None,
) -> DammV2PersistenceResult:
    """Arquiva e persiste DAMM v2; não avança checkpoint em hipótese alguma."""
    if not isinstance(wallet_address, str) or not wallet_address.strip():
        raise ValueError("wallet_address é obrigatório.")
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError("signature é obrigatória.")
    timestamp = observed_at or datetime.now(timezone.utc)
    payload = _payload(raw_transaction)
    meta = payload.get("meta")
    if isinstance(meta, dict) and meta.get("err") is not None:
        return DammV2PersistenceResult(
            "failed_on_chain", signature, 0, 0, 0, 0, True
        )

    transaction = payload.get("transaction")
    signatures = transaction.get("signatures") if isinstance(transaction, dict) else None
    if signatures is not None and (
        not isinstance(signatures, list)
        or any(not isinstance(item, str) or not item for item in signatures)
        or signature not in signatures
    ):
        raise ValueError("A assinatura informada não corresponde ao payload RPC.")

    normalized = normalize_transaction(
        payload, wallet_address, signature, observed_at=timestamp
    )
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

    result = process_damm_v2_transaction(
        payload,
        monitored_wallet=wallet_address,
        signature=signature,
        observed_at=normalized.transaction.occurred_at or normalized.transaction.observed_at,
        parser_version=normalized.transaction.parser_version,
    )

    associations = result.associations
    swap_associations = [
        item for item in associations if item.instruction is not None
    ]
    if result.status == "NO_DAMM_V2_SWAPS":
        return DammV2PersistenceResult(
            "no_damm_v2_swaps", signature, 0, 0, 0, 0, True
        )

    records: list[SwapReconciliationRecord] = []
    for item in swap_associations:
        if item.instruction_index is None:
            continue
        cpi_path = tuple(item.cpi_path or ())
        operation_id = build_swap_operation_id(
            "solana", signature, item.instruction_index, cpi_path
        )
        if result.status == "RECONCILED":
            status = "MATCHED"
            reason = "Swap DAMM v2 reconciliado economicamente e bundle de domínio validado."
        elif item.status == "AMBIGUOUS":
            status = "AMBIGUOUS"
            reason = result.reason
        else:
            status = "INCOMPLETE"
            reason = result.reason
        records.append(SwapReconciliationRecord(
            operation_id=operation_id,
            instruction_index=item.instruction_index,
            inner_instruction_index=item.inner_instruction_index,
            cpi_path=cpi_path,
            status=status,
            reason=reason,
        ))

    if records:
        store.save_swap_reconciliation_attempt(wallet_address, signature, records)

    if result.status != "RECONCILED":
        return DammV2PersistenceResult(
            "pending_reconciliation",
            signature,
            len(swap_associations),
            0,
            len(swap_associations),
            0,
            False,
        )

    saved = 0
    for bundle in result.bundles:
        if store.save_swap_bundle(
            bundle.observation, bundle.classification, bundle.evidence
        ):
            saved += 1
    if len(result.bundles) != len(swap_associations):
        return DammV2PersistenceResult(
            "pending_bundle_persistence",
            signature,
            len(swap_associations),
            len(result.bundles),
            len(swap_associations) - len(result.bundles),
            saved,
            False,
        )
    return DammV2PersistenceResult(
        "reconciled",
        signature,
        len(swap_associations),
        len(result.bundles),
        0,
        saved,
        True,
    )
