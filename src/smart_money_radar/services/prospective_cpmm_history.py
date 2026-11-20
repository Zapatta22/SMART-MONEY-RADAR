"""Audit two real prospective CPMM snapshots without inferring intervening events.

Reuse the four-account decoder, the pinned original Solana swap identity, and
raw bytes from immutable captures. A pair of snapshots does NOT certify
continuous event coverage, an executable quote or historic pre-swap state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,timezone
from hashlib import sha256
import json

from smart_money_radar.services.prospective_cpmm_account_snapshot import (
    ProspectiveCpmmSnapshot,inspect_prospective_cpmm_response,
)
from smart_money_radar.domain.cpmm_binary_state import (
    decode_pool_state,decode_amm_config,
)
from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
import base64


@dataclass(frozen=True)
class CpmmCapture:
    capture_id: str
    manifest: dict
    request_raw: bytes
    response_raw: bytes
    observation: ProspectiveCpmmSnapshot
    account_fee_raw: tuple[int,...]
    decoder_version: str="cpmm-history-1"


@dataclass(frozen=True)
class CpmmHistoryDelta:
    first_capture_id: str
    second_capture_id: str
    pool: str
    from_slot: int | None
    to_slot: int | None
    slot_delta: int | None
    coverage: str
    reason_codes: tuple[str,...]
    poolstate_changed: bool | None
    ammconfig_changed: bool | None
    vault_input_changed: bool | None
    vault_output_changed: bool | None
    vault_input_delta_raw: int | None
    vault_output_delta_raw: int | None
    effective_input_delta_raw: int | None
    effective_output_delta_raw: int | None
    fee_counter_deltas_raw: tuple[int,...] | None
    trade_fee_rate_changed: bool | None
    creator_fee_rate_changed: bool | None
    independently_authenticated: bool=False
    events_between_snapshots_complete: bool=False
    historical_original_swap_state_proven: bool=False
    economic_execution_authorized: bool=False


def _times(manifest: dict) -> tuple[datetime,datetime]:
    try:
        o=datetime.fromisoformat(manifest["observed_at"])
        a=datetime.fromisoformat(manifest["available_at"])
        if o.utcoffset() is None or a.utcoffset() is None or o>a:
            raise ValueError("tempos de observação inválidos")
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError("manifesto sem tempo confiável") from exc
    return o.astimezone(timezone.utc),a.astimezone(timezone.utc)


def capture_from_raw(*,manifest_raw:bytes,request_raw:bytes,response_raw:bytes,
                     original_transaction_raw:bytes,original_manifest:dict,
                     cutoff:datetime,source_id:str) -> CpmmCapture:
    """Reconstruct one real evidence record; validates bytes before decoding."""
    if not all(isinstance(v,bytes) and v for v in (
        manifest_raw,request_raw,response_raw,original_transaction_raw)):
        raise ValueError("evidências RAW obrigatórias")
    if not isinstance(cutoff,datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff com fuso obrigatório")
    if not isinstance(source_id,str) or not source_id.strip():
        raise ValueError("fonte ausente")
    try:
        manifest=json.loads(manifest_raw)
        if not isinstance(manifest,dict):
            raise ValueError("manifesto inválido")
        if sha256(original_transaction_raw).hexdigest()!=original_manifest["raw_sha256"]:
            raise ValueError("RAW transação original adulterado")
        if sha256(request_raw).hexdigest()!=manifest["request_sha256"]:
            raise ValueError("SHA de requisição divergente")
        if sha256(response_raw).hexdigest()!=manifest["response_sha256"]:
            raise ValueError("SHA da resposta divergente")
        occurred,available=_times(manifest)
        if available>cutoff.astimezone(timezone.utc):
            raise ValueError("evidência posterior ao cutoff")
        if (manifest["status"]!="RPC_DECLARED_PROSPECTIVE_ONLY"
            or manifest.get("requests_attempted")!=1
            or manifest["historical_original_swap_state_verified"] is not False
            or manifest["economic_execution_authorized"] is not False
            or manifest["provider_authenticated"] is not False):
            raise ValueError("classificação ou proveniência inválida")
        swaps=decode_raydium_cpmm_swaps(json.loads(original_transaction_raw))
        matching=[x for x in swaps if x.accounts.pool_state==manifest["original_pool"]]
        if len(matching)!=1:
            raise ValueError("escopo original CPMM incompatível")
        acc=matching[0].accounts
        if (manifest["original_slot"]!=original_manifest["slot_observed"]
            or manifest["original_signature"]!=original_manifest["signature_requested"]):
            raise ValueError("identidade de swap original divergente")
        obs=inspect_prospective_cpmm_response(
            request_raw=request_raw,response_raw=response_raw,
            source_id=source_id,endpoint=manifest["endpoint"],
            observed_at=occurred,available_at=available,
            pool=acc.pool_state,amm_config=acc.amm_config,
            input_vault=acc.input_vault,output_vault=acc.output_vault,
            input_mint=acc.input_token_mint,output_mint=acc.output_token_mint,
            authority=acc.authority,
            input_token_program=acc.input_token_program,
            output_token_program=acc.output_token_program,
            original_swap_slot=original_manifest["slot_observed"])
        if (obs.status!="RPC_DECLARED_PROSPECTIVE_ONLY"
            or obs.slot!=manifest["context_slot"]
            or list(obs.account_sha256)!=manifest["account_sha256"]
            or obs.effective_input_raw!=manifest["effective_input_raw_at_collection"]
            or obs.effective_output_raw!=manifest["effective_output_raw_at_collection"]
            or obs.input_vault_raw!=manifest["input_vault_raw_at_collection"]
            or obs.output_vault_raw!=manifest["output_vault_raw_at_collection"]
            or obs.declared_trade_fee_rate!=manifest["trade_fee_rate_at_collection"]
            or obs.declared_creator_fee_rate!=manifest["creator_fee_rate_at_collection"]):
            raise ValueError("manifesto e resposta de contas divergentes")
        data=json.loads(response_raw)["result"]["value"]
        pool=decode_pool_state(base64.b64decode(data[0]["data"][0],validate=True))
        _=decode_amm_config(base64.b64decode(data[1]["data"][0],validate=True))
        # Pool fee counters in token0/token1 order, including all three buckets.
        fee=(pool.protocol_fees_token_0,pool.protocol_fees_token_1,
             pool.fund_fees_token_0,pool.fund_fees_token_1,
             pool.creator_fees_token_0,pool.creator_fees_token_1)
        cap_id=sha256(
            b"SMR-CPMM-CAPTURE-V1\x00"+sha256(request_raw).digest()+
            sha256(response_raw).digest()+manifest["context_slot"].to_bytes(8,"big")
        ).hexdigest()
        return CpmmCapture(cap_id,manifest,request_raw,response_raw,obs,fee)
    except (KeyError,TypeError,IndexError,OverflowError,
            base64.binascii.Error) as exc:
        raise ValueError("captura incompleta ou corrompida") from exc


def compare_captures(first:CpmmCapture,second:CpmmCapture,*,cutoff:datetime)->CpmmHistoryDelta:
    """Report only changes between observations, with an explicit gap."""
    if not isinstance(first,CpmmCapture) or not isinstance(second,CpmmCapture):
        raise TypeError("capturas inválidas")
    if not isinstance(cutoff,datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff inválido")
    reasons=set()
    x,y=first.observation,second.observation
    slot_delta=(y.slot-x.slot) if type(x.slot) is int and type(y.slot) is int else None
    def utc(v):return v.astimezone(timezone.utc)
    if utc(x.available_at)>utc(cutoff) or utc(y.available_at)>utc(cutoff):
        reasons.add("evidence_after_cutoff")
    if (x.pool!=y.pool or x.amm_config!=y.amm_config
        or first.manifest["original_signature"]!=second.manifest["original_signature"]
        or first.manifest["original_slot"]!=second.manifest["original_slot"]
        or first.request_raw!=second.request_raw):
        reasons.add("scope_conflict")
    if x.slot==y.slot:reasons.add("same_slot_no_proven_transition")
    elif slot_delta is None:reasons.add("slot_missing")
    elif slot_delta<0:reasons.add("reversed_slots")
    if utc(x.available_at)>=utc(y.available_at):
        reasons.add("non_increasing_availability")
    if (x.status!="RPC_DECLARED_PROSPECTIVE_ONLY"
        or y.status!="RPC_DECLARED_PROSPECTIVE_ONLY"):
        reasons.add("capture_unverified")
    # Immutable raw binding is rechecked rather than trusting caller-supplied
    # decoded values, preventing a mutated in-memory capture being promoted.
    for c in (first,second):
        if (sha256(c.response_raw).hexdigest()!=c.manifest.get("response_sha256")
            or sha256(c.request_raw).hexdigest()!=c.manifest.get("request_sha256")
            or c.observation.response_sha256!=c.manifest.get("response_sha256")):
            reasons.add("raw_hash_conflict")
    if (first.capture_id==second.capture_id and first.response_raw!=second.response_raw):
        reasons.add("capture_identity_collision")
    conflict=bool(reasons & {"scope_conflict","reversed_slots",
        "evidence_after_cutoff","non_increasing_availability",
        "raw_hash_conflict","capture_identity_collision"})
    valid=not conflict and not reasons & {"slot_missing","capture_unverified","same_slot_no_proven_transition"}
    coverage="CONFLICT" if conflict else "PARTIAL" if valid else "UNKNOWN"
    if valid:
        reasons.add("intervening_account_updates_not_observed")
        reasons.add("rpc_source_not_independently_attested")
        if slot_delta!=1:reasons.add("slot_gap")
    values_valid=valid
    def delta(a,b):return b-a if a is not None and b is not None and values_valid else None
    ah,bh=x.account_sha256,y.account_sha256
    return CpmmHistoryDelta(
        first_capture_id=first.capture_id,second_capture_id=second.capture_id,
        pool=x.pool,from_slot=x.slot,to_slot=y.slot,slot_delta=slot_delta,
        coverage=coverage,reason_codes=tuple(sorted(reasons)),
        poolstate_changed=ah[0]!=bh[0] if values_valid else None,
        ammconfig_changed=ah[1]!=bh[1] if values_valid else None,
        vault_input_changed=ah[2]!=bh[2] if values_valid else None,
        vault_output_changed=ah[3]!=bh[3] if values_valid else None,
        vault_input_delta_raw=delta(x.input_vault_raw,y.input_vault_raw),
        vault_output_delta_raw=delta(x.output_vault_raw,y.output_vault_raw),
        effective_input_delta_raw=delta(x.effective_input_raw,y.effective_input_raw),
        effective_output_delta_raw=delta(x.effective_output_raw,y.effective_output_raw),
        fee_counter_deltas_raw=(
            tuple(b-a for a,b in zip(first.account_fee_raw,second.account_fee_raw))
            if values_valid else None),
        trade_fee_rate_changed=(
            x.declared_trade_fee_rate!=y.declared_trade_fee_rate if values_valid else None),
        creator_fee_rate_changed=(
            x.declared_creator_fee_rate!=y.declared_creator_fee_rate if values_valid else None),
    )
