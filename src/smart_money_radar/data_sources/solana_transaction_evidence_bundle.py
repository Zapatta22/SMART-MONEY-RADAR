"""Transaction-scoped evidence bundle for Solana RPC payloads.

The bundle derives its instruction inventory, token transfers and token-account
balance deltas from one and the same raw RPC payload. It is an evidence
container only: it does not classify swaps, reconcile economics or authorize
execution.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from smart_money_radar.data_sources.damm_v2_accounts import decode_damm_v2_swap_accounts
from smart_money_radar.data_sources.damm_v2_economic_reconciliation import (
    DammV2EconomicReconciliation,
    DammV2MintFeeConfigSnapshot,
    reconcile_damm_v2_economic_batch,
)
from smart_money_radar.data_sources.damm_v2_analyzer import (
    DammV2SwapEventAssociation,
    analyze_damm_v2_swap_events,
)
from smart_money_radar.data_sources.damm_v2_decoder import METEORA_DAMM_V2_PROGRAM_ID
from smart_money_radar.data_sources.damm_v2_transfer_analyzer import (
    DammV2SwapTransferContext,
    DammV2TransferEvidence,
    analyze_damm_v2_transfer_evidence,
)
from smart_money_radar.data_sources.solana_token_balance_delta_decoder import (
    SolanaTokenBalanceDeltaResult,
    decode_solana_token_account_balance_deltas,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SolanaInstructionInventory,
    SolanaTokenTransfer,
    decode_solana_instruction_inventory,
    decode_solana_token_transfers,
)


_BUNDLE_FACTORY_TOKEN = object()


@dataclass(frozen=True)
class SolanaTransactionIdentity:
    transaction_signature: str
    slot: int
    source_id: str
    payload_sha256: str


@dataclass(frozen=True)
class SolanaTransactionEvidenceBundle:
    """Immutable decoder outputs bound to one canonicalized RPC payload."""

    identity: SolanaTransactionIdentity
    instruction_inventory: SolanaInstructionInventory
    transfers: tuple[SolanaTokenTransfer, ...]
    balance_deltas: SolanaTokenBalanceDeltaResult
    damm_v2_associations: tuple[DammV2SwapEventAssociation, ...] = ()
    damm_v2_contexts: tuple[DammV2SwapTransferContext, ...] = ()
    damm_v2_transfer_evidence: tuple[DammV2TransferEvidence, ...] = ()
    damm_v2_issues: tuple[str, ...] = ()
    _factory_token: object = field(default=None, repr=False, compare=False)
    _factory_snapshot: tuple[Any, ...] | None = field(default=None, repr=False, compare=False)

    @property
    def damm_v2_complete(self) -> bool:
        """Whether all detected DAMM v2 swaps have matched, attributable evidence."""
        return (
            not self.damm_v2_issues
            and len(self.damm_v2_contexts) == len(self.damm_v2_associations)
            and len(self.damm_v2_transfer_evidence) == len(self.damm_v2_contexts)
            and all(item.status == "ATTRIBUTED" for item in self.damm_v2_transfer_evidence)
        )

    @property
    def structurally_complete(self) -> bool:
        """Whether required transaction identity and decoder evidence are complete."""
        return (
            self.instruction_inventory.complete
            and self.balance_deltas.complete
            and self.instruction_inventory.transaction_signature
            == self.identity.transaction_signature
            and self.instruction_inventory.slot == self.identity.slot
        )


def _rpc_payload(raw_transaction: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_transaction, dict):
        raise TypeError("transação RPC precisa ser um objeto")
    payload = raw_transaction.get("result", raw_transaction)
    if not isinstance(payload, dict):
        raise ValueError("payload RPC inválido")
    return payload


def _is_valid_signature(value: Any) -> bool:
    """Validate a Solana transaction signature as a 64-byte Base58 value."""
    if not isinstance(value, str) or not value:
        return False
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0
    try:
        for character in value:
            number = number * 58 + alphabet.index(character)
    except ValueError:
        return False
    decoded_length = (number.bit_length() + 7) // 8
    leading_zero_bytes = len(value) - len(value.lstrip("1"))
    return decoded_length + leading_zero_bytes == 64


def _transaction_identity(
    raw_transaction: dict[str, Any], source_id: str
) -> SolanaTransactionIdentity:
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id ausente ou inválido")

    payload = _rpc_payload(raw_transaction)
    transaction = payload.get("transaction")
    signatures = transaction.get("signatures") if isinstance(transaction, dict) else None
    signature = signatures[0] if isinstance(signatures, list) and signatures else None
    if not _is_valid_signature(signature):
        raise ValueError("assinatura Solana ausente ou inválida (Base58 de 64 bytes)")

    slot = payload.get("slot")
    if isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot <= (1 << 64) - 1:
        raise ValueError("slot da transação ausente ou inválido")

    try:
        canonical_payload = json.dumps(
            raw_transaction,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("payload RPC não pode ser canonicalizado como JSON") from exc

    return SolanaTransactionIdentity(
        transaction_signature=signature,
        slot=slot,
        source_id=source_id.strip(),
        payload_sha256=hashlib.sha256(canonical_payload).hexdigest(),
    )


def build_solana_transaction_evidence_bundle(
    raw_transaction: dict[str, Any],
    *,
    source_id: str,
) -> SolanaTransactionEvidenceBundle:
    """Build all transaction-scoped decoder evidence from one RPC payload.

    Components are deliberately decoded inside this factory rather than
    accepted as independent caller-provided lists/results. This prevents the
    factory from silently combining evidence decoded from different payloads.
    Incomplete decoder results are preserved and make the bundle ineligible;
    they are never upgraded to complete by this layer.
    """
    identity = _transaction_identity(raw_transaction, source_id)
    inventory = decode_solana_instruction_inventory(raw_transaction)
    transfers = decode_solana_token_transfers(raw_transaction)
    balance_deltas = decode_solana_token_account_balance_deltas(raw_transaction)
    associations = tuple(analyze_damm_v2_swap_events(raw_transaction))

    contexts = []
    damm_issues = []
    for index, association in enumerate(associations):
        if association.status != "MATCHED":
            damm_issues.append(
                f"associação DAMM v2 {index} não resolvida: {association.status}"
            )
            continue
        if (
            association.event is None
            or association.instruction is None
            or association.resolved_accounts is None
        ):
            damm_issues.append(
                f"associação DAMM v2 {index} sem evento/instrução/contas resolvidas"
            )
            continue
        try:
            accounts = decode_damm_v2_swap_accounts(
                {
                    "programId": METEORA_DAMM_V2_PROGRAM_ID,
                    "accounts": list(association.resolved_accounts),
                },
                [],
                association.event,
            )
        except (TypeError, ValueError) as exc:
            damm_issues.append(
                f"contas DAMM v2 {index} inválidas: {exc}"
            )
            continue
        contexts.append(DammV2SwapTransferContext(association, accounts))

    transfer_evidence = (
        analyze_damm_v2_transfer_evidence(contexts, transfers)
        if not damm_issues and contexts
        else []
    )

    if (
        inventory.transaction_signature != identity.transaction_signature
        or inventory.slot != identity.slot
    ):
        raise ValueError("inventário de instruções diverge da identidade do payload")

    bundle = SolanaTransactionEvidenceBundle(
        identity=identity,
        instruction_inventory=inventory,
        transfers=tuple(transfers),
        balance_deltas=balance_deltas,
        damm_v2_associations=associations,
        damm_v2_contexts=tuple(contexts),
        damm_v2_transfer_evidence=tuple(transfer_evidence),
        damm_v2_issues=tuple(damm_issues),
        _factory_token=_BUNDLE_FACTORY_TOKEN,
    )
    object.__setattr__(
        bundle,
        "_factory_snapshot",
        (
            bundle.identity,
            bundle.instruction_inventory,
            bundle.transfers,
            bundle.balance_deltas,
            bundle.damm_v2_associations,
            bundle.damm_v2_contexts,
            bundle.damm_v2_transfer_evidence,
            bundle.damm_v2_issues,
        ),
    )
    return bundle


def reconcile_solana_transaction_damm_v2_bundle(
    bundle: SolanaTransactionEvidenceBundle,
    *,
    monitored_wallet: str,
    mint_fee_snapshots: tuple[DammV2MintFeeConfigSnapshot, ...] = (),
    transaction_epoch: int | None = None,
    transaction_order: int | None = None,
) -> DammV2EconomicReconciliation:
    """Reconcile DAMM v2 only from evidence derived inside one validated bundle.

    The caller cannot supply independent contexts, transfers or balance
    deltas. Transaction signature and slot are taken from the bundle identity.
    Historical mint snapshots retain their own provenance and must still pass
    the economic reconciler's ordering and applicability checks.
    """
    if (
        not isinstance(bundle, SolanaTransactionEvidenceBundle)
        or bundle._factory_token is not _BUNDLE_FACTORY_TOKEN
    ):
        raise TypeError("bundle deve ser criado pela factory validada de evidências Solana")
    snapshot = bundle._factory_snapshot
    current_evidence = (
        bundle.identity,
        bundle.instruction_inventory,
        bundle.transfers,
        bundle.balance_deltas,
        bundle.damm_v2_associations,
        bundle.damm_v2_contexts,
        bundle.damm_v2_transfer_evidence,
        bundle.damm_v2_issues,
    )
    if (
        not isinstance(snapshot, tuple)
        or len(snapshot) != len(current_evidence)
        or any(current is not sealed for current, sealed in zip(current_evidence, snapshot))
    ):
        raise ValueError("bundle foi alterado após a construção pela factory")

    operation_count = len(bundle.damm_v2_associations)
    if not bundle.damm_v2_associations:
        return DammV2EconomicReconciliation(
            "INCOMPLETE", 0, (), "nenhuma associação DAMM v2 encontrada no bundle"
        )
    if not bundle.structurally_complete:
        return DammV2EconomicReconciliation(
            "INCOMPLETE", operation_count, (),
            "bundle estruturalmente incompleto; reconciliação bloqueada",
        )
    if bundle.damm_v2_issues:
        return DammV2EconomicReconciliation(
            "INCOMPLETE", operation_count, (),
            "; ".join(bundle.damm_v2_issues),
        )
    if (
        len(bundle.damm_v2_contexts) != operation_count
        or len(bundle.damm_v2_transfer_evidence) != operation_count
    ):
        return DammV2EconomicReconciliation(
            "INCOMPLETE", operation_count, (),
            "contexts/evidence não cobrem todas as associações DAMM v2",
        )
    unresolved = [
        item.status for item in bundle.damm_v2_transfer_evidence
        if item.status != "ATTRIBUTED"
    ]
    if unresolved:
        return DammV2EconomicReconciliation(
            "INCOMPLETE", operation_count, (),
            "transfer evidence não atribuída: " + ", ".join(unresolved),
        )

    return reconcile_damm_v2_economic_batch(
        bundle.damm_v2_contexts,
        bundle.damm_v2_transfer_evidence,
        bundle.balance_deltas,
        bundle.transfers,
        monitored_wallet=monitored_wallet,
        mint_fee_snapshots=mint_fee_snapshots,
        transaction_epoch=transaction_epoch,
        transaction_slot=bundle.identity.slot,
        transaction_order=transaction_order,
        transaction_signature=bundle.identity.transaction_signature,
    )
