"""Transaction-scoped evidence bundle for Solana RPC payloads.

The bundle derives its instruction inventory, token transfers and token-account
balance deltas from one and the same raw RPC payload. It is an evidence
container only: it does not classify swaps, reconcile economics or authorize
execution.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

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


def _transaction_identity(
    raw_transaction: dict[str, Any], source_id: str
) -> SolanaTransactionIdentity:
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id ausente ou inválido")

    payload = _rpc_payload(raw_transaction)
    transaction = payload.get("transaction")
    signatures = transaction.get("signatures") if isinstance(transaction, dict) else None
    signature = (
        signatures[0]
        if isinstance(signatures, list)
        and signatures
        and isinstance(signatures[0], str)
        and signatures[0].strip()
        else None
    )
    if signature is None:
        raise ValueError("assinatura da transação ausente ou inválida")

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

    if (
        inventory.transaction_signature != identity.transaction_signature
        or inventory.slot != identity.slot
    ):
        raise ValueError("inventário de instruções diverge da identidade do payload")

    return SolanaTransactionEvidenceBundle(
        identity=identity,
        instruction_inventory=inventory,
        transfers=tuple(transfers),
        balance_deltas=balance_deltas,
    )
