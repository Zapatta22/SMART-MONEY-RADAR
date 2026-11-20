"""Bounded, read-only verification of Solana getTransaction RPC evidence.

Reuses the repository's base58 signature validator and JSON-RPC shape.
This is an offline-verifiable response adapter, not a cryptographic proof of
provider independence or a claim that 'finalized' is externally authenticated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Literal

from smart_money_radar.data_sources.rpc_fixture_collector import _is_solana_signature

VerificationStatus = Literal["UNKNOWN", "CONFLICTED", "RPC_CONSISTENT_UNATTESTED"]


@dataclass(frozen=True)
class RpcTransactionEvidence:
    signature: str
    slot: int | None
    pool: str | None
    source_id: str
    endpoint_host: str
    observed_at: datetime
    available_at: datetime
    raw_sha256: str
    raw_payload: bytes
    commitment_requested: str
    status: VerificationStatus
    reasons: tuple[str, ...]
    provider_authenticated: bool = False
    independently_finalized: bool = False


def verify_transaction_rpc_response(
    *, raw_payload: bytes, signature: str, source_id: str,
    endpoint_host: str, observed_at: datetime, available_at: datetime,
    expected_slot: int | None = None, expected_pool: str | None = None,
    requested_commitment: str = "finalized",
) -> RpcTransactionEvidence:
    if not _is_solana_signature(signature):
        raise ValueError("assinatura Solana Base58 inválida")
    if not isinstance(raw_payload, bytes) or not raw_payload:
        raise ValueError("RAW RPC ausente")
    if any(not isinstance(x,str) or not x.strip() for x in (source_id, endpoint_host)):
        raise ValueError("origem RPC inválida")
    if any(not isinstance(t, datetime) or t.utcoffset() is None for t in (observed_at, available_at)):
        raise ValueError("timestamps RPC devem possuir fuso")
    if observed_at > available_at:
        raise ValueError("disponibilidade anterior à observação")
    if expected_slot is not None and (type(expected_slot) is not int or expected_slot < 0):
        raise ValueError("slot esperado inválido")
    if expected_pool is not None and (not isinstance(expected_pool, str) or not expected_pool.strip()):
        raise ValueError("pool esperado inválido")
    if requested_commitment not in ("finalized", "confirmed", "processed"):
        raise ValueError("compromisso RPC inválido")
    try:
        response=json.loads(raw_payload)
    except (ValueError,UnicodeDecodeError) as exc:
        raise ValueError("RAW RPC JSON inválido") from exc
    if not isinstance(response,dict) or response.get("jsonrpc") not in ("2.0",None):
        raise ValueError("estrutura RPC inválida")
    reasons=set()
    conflicts=set()
    if "error" in response:
        reasons.add("rpc_error_not_absence_of_risk")
    transaction=response.get("result")
    slot=None
    pool=None
    if transaction is None:
        reasons.add("transaction_not_found_or_unavailable")
    elif not isinstance(transaction,dict):
        conflicts.add("transaction_result_invalid")
    else:
        slot=transaction.get("slot")
        if type(slot) is not int or slot < 0:
            conflicts.add("transaction_slot_invalid")
            slot=None
        elif expected_slot is not None and expected_slot != slot:
            conflicts.add("transaction_slot_conflict")
        embedded=transaction.get("transaction")
        signatures=embedded.get("signatures") if isinstance(embedded,dict) else None
        if not isinstance(signatures,list) or not signatures or signatures[0] != signature:
            conflicts.add("transaction_signature_conflict")
        meta=transaction.get("meta")
        if not isinstance(meta,dict) or "err" not in meta:
            reasons.add("transaction_meta_unknown")
        elif meta["err"] is not None:
            conflicts.add("transaction_failed_on_chain")
        message=embedded.get("message") if isinstance(embedded,dict) else None
        instructions=message.get("instructions") if isinstance(message,dict) else None
        if expected_pool is not None:
            # JSON encoding may require decoding compiled indices and loaded
            # addresses. The pool cannot be certified by its mere appearance.
            if not isinstance(instructions,list):
                reasons.add("pool_instruction_unresolved")
            else:
                # Only parsed instruction accounts can establish candidate pool
                # participation, never owner/PDA correctness.
                found=any(isinstance(ins,dict) and expected_pool in ins.get("accounts",())
                          for ins in instructions if isinstance(ins.get("accounts"),list))
                if found:
                    pool=expected_pool
                else:
                    reasons.add("pool_instruction_unresolved")
    if requested_commitment != "finalized":
        reasons.add("finalized_not_requested")
    # getTransaction(commitment=finalized) returns transactions filtered by
    # claimed commitment, but cannot independently attest the responding node.
    reasons.add("provider_independent_attestation_missing")
    reasons.add("finalization_independent_attestation_missing")
    reasons.update(conflicts)
    status:VerificationStatus=(
        "CONFLICTED" if conflicts else
        "UNKNOWN" if transaction is None or reasons-{
            "provider_independent_attestation_missing",
            "finalization_independent_attestation_missing",
        } else "RPC_CONSISTENT_UNATTESTED"
    )
    return RpcTransactionEvidence(
        signature=signature,slot=slot,pool=pool,source_id=source_id,
        endpoint_host=endpoint_host,observed_at=observed_at.astimezone(timezone.utc),
        available_at=available_at.astimezone(timezone.utc),
        raw_sha256=sha256(raw_payload).hexdigest(),raw_payload=raw_payload,
        commitment_requested=requested_commitment,status=status,
        reasons=tuple(sorted(reasons)),
    )


def reconcile_rpc_sources(
    evidences: tuple[RpcTransactionEvidence, ...],
) -> tuple[str, tuple[str,...]]:
    """Compare two independently labelled sources without trusting either."""
    if not isinstance(evidences,tuple) or not evidences:
        return "UNKNOWN", ("no_rpc_evidence",)
    if any(not isinstance(x,RpcTransactionEvidence) for x in evidences):
        raise TypeError("evidências RPC inválidas")
    reasons=set()
    signatures={x.signature for x in evidences}
    slots={x.slot for x in evidences if x.slot is not None}
    sources={x.source_id for x in evidences}
    if len(signatures)!=1:
        reasons.add("contradictory_signatures")
    if len(slots)>1:
        reasons.add("contradictory_slots")
    if any(x.status=="CONFLICTED" for x in evidences):
        reasons.add("invalid_rpc_evidence")
    if reasons:
        return "CONFLICTED",tuple(sorted(reasons))
    if len(evidences)<2 or len(sources)<2:
        return "UNKNOWN",("independent_rpc_source_missing",)
    if any(x.status!="RPC_CONSISTENT_UNATTESTED" for x in evidences):
        return "UNKNOWN",("incomplete_rpc_source",)
    return "CROSS_SOURCE_CONSISTENT_UNATTESTED",(
        "source_independence_not_cryptographically_verified",)
