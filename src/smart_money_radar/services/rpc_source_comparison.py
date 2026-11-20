"""Compare immutable Solana RPC sources without confusing corroboration with proof.

Uses existing Raydium CPMM decoder for accounts/program. A null response is
UNKNOWN, not a slot contradiction; endpoint labels are never independent
infrastructure attestation.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Literal

from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps


@dataclass(frozen=True)
class RpcSourceRecord:
    source_id: str
    infrastructure_operator: str | None
    raw: bytes
    claimed_raw_sha256: str
    available_at: datetime
    commitment_requested: Literal["finalized","confirmed","processed"]


@dataclass(frozen=True)
class RpcCorroboration:
    status: Literal["UNKNOWN","CONFLICTED","CORROBORATED_UNATTESTED"]
    source_raw_sha256: tuple[str,str]
    canonical_core_sha256: tuple[str | None,str | None]
    reasons: tuple[str,...]
    identity_equal: bool
    independent_provider_proven: bool=False
    independently_finalized: bool=False
    historic_pool_reserves_verified: bool=False
    executable_quote_verified: bool=False
    operational_authorized: bool=False


def compare_rpc_records(
    first: RpcSourceRecord, second: RpcSourceRecord, *,
    signature: str, slot: int, pool: str, cutoff: datetime,
) -> RpcCorroboration:
    if not isinstance(first,RpcSourceRecord) or not isinstance(second,RpcSourceRecord):
        raise TypeError("origens RPC inválidas")
    if not isinstance(cutoff,datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff sem fuso")
    if any(not isinstance(x,str) or not x.strip() for x in (signature,pool)):
        raise ValueError("escopo inválido")
    if type(slot) is not int or slot<0:
        raise ValueError("slot inválido")
    reasons=set()
    conflicts=set()
    values=[]
    hashes=[]
    core_hashes=[]
    for index,source in enumerate((first,second)):
        if not isinstance(source.source_id,str) or not source.source_id.strip():
            raise ValueError("identidade de origem inválida")
        if (not isinstance(source.available_at,datetime) or
            source.available_at.utcoffset() is None or
            source.available_at.astimezone(timezone.utc)>cutoff.astimezone(timezone.utc)):
            conflicts.add("source_unavailable_at_cutoff")
        if source.commitment_requested!="finalized":
            reasons.add("finalized_not_requested")
        if not isinstance(source.raw,bytes) or not source.raw:
            reasons.add("source_raw_missing")
            values.append(None)
            hashes.append("")
            core_hashes.append(None)
            continue
        digest=sha256(source.raw).hexdigest()
        hashes.append(digest)
        if digest!=source.claimed_raw_sha256:
            conflicts.add("source_raw_sha_mismatch")
            values.append(None)
            core_hashes.append(None)
            continue
        try:
            envelope=json.loads(source.raw)
            result=envelope.get("result") if isinstance(envelope,dict) else None
        except (ValueError,TypeError,UnicodeDecodeError):
            conflicts.add("source_json_invalid")
            values.append(None)
            core_hashes.append(None)
            continue
        if not isinstance(envelope,dict):
            conflicts.add("source_json_invalid")
            values.append(None)
            core_hashes.append(None)
            continue
        if "error" in envelope:
            reasons.add("source_rpc_error")
            values.append(None)
            core_hashes.append(None)
            continue
        if result is None:
            reasons.add("source_transaction_not_available")
            values.append(None)
            core_hashes.append(None)
            continue
        if not isinstance(result,dict):
            conflicts.add("source_result_invalid")
            values.append(None)
            core_hashes.append(None)
            continue
        try:
            target_sig=result["transaction"]["signatures"][0]
            target_slot=result["slot"]
            fee=result["meta"]["fee"]
            err=result["meta"]["err"]
            swaps=decode_raydium_cpmm_swaps(envelope)
        except (KeyError,TypeError,IndexError,ValueError):
            conflicts.add("source_transaction_invalid")
            values.append(None)
            core_hashes.append(None)
            continue
        if target_sig!=signature or target_slot!=slot or err is not None:
            conflicts.add("signature_slot_or_success_conflict")
        if not any(s.accounts.pool_state==pool for s in swaps):
            conflicts.add("raydium_pool_not_present")
        values.append((target_sig,target_slot,fee,tuple(sorted((
            s.accounts.pool_state,s.accounts.amm_config,
            s.accounts.input_vault,s.accounts.output_vault,
            s.accounts.input_token_mint,s.accounts.output_token_mint
        ) for s in swaps))))
        core={k:result.get(k) for k in ("slot","blockTime","transaction","meta")}
        core_hashes.append(sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest())
    if first.source_id==second.source_id:
        reasons.add("source_identity_not_distinct")
    if (first.infrastructure_operator is None or second.infrastructure_operator is None):
        reasons.add("infrastructure_ownership_unknown")
    elif first.infrastructure_operator==second.infrastructure_operator:
        reasons.add("shared_rpc_infrastructure")
    if len(values)==2 and all(x is not None for x in values):
        if values[0]!=values[1]:
            conflicts.add("economic_or_identity_fields_divergent")
        if core_hashes[0]!=core_hashes[1]:
            # Differences in RPC encoding are not necessarily a consensus
            # conflict, but still prevent unqualified canonical equivalence.
            reasons.add("canonical_json_core_differs")
    reasons.update(conflicts)
    if conflicts:
        status="CONFLICTED"
    elif any(x is None for x in values) or reasons & {
        "source_identity_not_distinct","shared_rpc_infrastructure",
        "infrastructure_ownership_unknown","finalized_not_requested",
        "canonical_json_core_differs",
    }:
        status="UNKNOWN"
    else:
        status="CORROBORATED_UNATTESTED"
        reasons.add("provider_independence_not_cryptographically_proven")
    return RpcCorroboration(
        status=status,source_raw_sha256=tuple(hashes),
        canonical_core_sha256=tuple(core_hashes),
        reasons=tuple(sorted(reasons)),identity_equal=(
            len(values)==2 and values[0] is not None and values[0]==values[1]),
    )
