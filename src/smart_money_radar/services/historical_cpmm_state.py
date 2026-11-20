"""Conservative reconstruction of a CPMM swap's vault balance deltas.

Actual token pre/post balances are evidence for the individual transaction.
They are NOT effective CPMM reserves: PoolState fee counters, AmmConfig,
vault authority, competing writes and pre-swap availability remain unproved.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Literal

from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps


@dataclass(frozen=True)
class HistoricalVaultBalance:
    address: str
    mint: str
    owner: str
    token_program: str
    decimals: int
    pre_raw: int
    post_raw: int
    delta_raw: int


@dataclass(frozen=True)
class HistoricalCpmmState:
    signature: str
    slot: int
    pool: str
    amm_config: str
    program_id: str
    source_id: str
    observed_at: datetime
    available_at: datetime
    raw_sha256: str
    input_vault: HistoricalVaultBalance
    output_vault: HistoricalVaultBalance
    solana_network_fee_lamports: int
    reserve_effective_in: None = None
    reserve_effective_out: None = None
    cpmm_trade_fee_rate: None = None
    pre_swap_poolstate_verified: bool = False
    pre_swap_ammconfig_verified: bool = False
    token_vault_authority_verified: bool = False
    economic_replay_eligible: bool = False
    status: Literal["PARTIAL_HISTORICAL_TX_ONLY"] = "PARTIAL_HISTORICAL_TX_ONLY"
    reasons: tuple[str, ...] = (
        "historical_poolstate_missing", "historical_ammconfig_missing",
        "effective_reserves_unknown", "cpmm_fees_unknown",
        "vault_authority_not_attested", "independent_rpc_finality_not_proven",
        "pre_decision_availability_not_proven",
    )


def _stamp(value: str, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} inválido")
    try:
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} inválido") from exc
    if dt.utcoffset() is None:
        raise ValueError(f"{label} sem fuso")
    return dt.astimezone(timezone.utc)


def reconstruct_tx_vaults(
    *, original_raw: bytes, manifest: dict, cutoff: datetime,
) -> HistoricalCpmmState:
    """Bind historical account balances in one real observed transaction.

    A later replay cannot use an earlier `blockTime` as the first-available
    timestamp: it can only use the recorded collection availability.
    """
    if not isinstance(original_raw,bytes) or not original_raw:
        raise ValueError("RAW original obrigatório")
    if not isinstance(manifest,dict):
        raise ValueError("manifesto inválido")
    if not isinstance(cutoff,datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff sem fuso")
    available=_stamp(manifest.get("available_at"),"available_at")
    observed=_stamp(manifest.get("observed_at"),"observed_at")
    if observed>available or available>cutoff.astimezone(timezone.utc):
        raise ValueError("evidência indisponível no cutoff histórico")
    actual_hash=sha256(original_raw).hexdigest()
    if actual_hash!=manifest.get("raw_sha256"):
        raise ValueError("SHA-256 RAW divergente")
    try:
        raw=json.loads(original_raw)
        tx=raw["result"]
        signature=tx["transaction"]["signatures"][0]
        slot=tx["slot"]
        meta=tx["meta"]
        message=tx["transaction"]["message"]
        fee=meta["fee"]
        event_time=datetime.fromtimestamp(tx["blockTime"],tz=timezone.utc)
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
        raise ValueError("transação original incompleta") from exc
    if (signature!=manifest.get("signature_requested") or
        type(slot) is not int or slot!=manifest.get("slot_observed")):
        raise ValueError("identidade de assinatura ou slot diverge")
    if event_time>observed:
        raise ValueError("evento posterior à observação")
    if type(fee) is not int or fee<0 or meta.get("err") is not None:
        raise ValueError("taxa rede ou resultado da transação inválido")
    expected=manifest["decoded_cpmm_swaps"]
    if not isinstance(expected,list) or len(expected)!=1:
        raise ValueError("swap esperado ambíguo")
    target=expected[0]
    swaps=decode_raydium_cpmm_swaps(raw)
    matched=[x for x in swaps if
             x.accounts.pool_state==target["pool"] and
             x.accounts.amm_config==target["amm_config"] and
             x.accounts.input_vault==target["input_vault"] and
             x.accounts.output_vault==target["output_vault"] and
             x.accounts.input_token_mint==target["input_mint"] and
             x.accounts.output_token_mint==target["output_mint"]]
    if len(matched)!=1:
        raise ValueError("identidade CPMM pool/vault/config não corresponde")
    keys=message["accountKeys"]
    if not isinstance(keys,list) or len(set(keys))!=len(keys):
        raise ValueError("accountKeys inválidos ou repetidos")
    def balances(phase):
        key="preTokenBalances" if phase=="pre" else "postTokenBalances"
        items=meta.get(key)
        if not isinstance(items,list):
            raise ValueError("saldos históricos ausentes")
        out={}
        for row in items:
            idx=row["accountIndex"]
            if type(idx) is not int or idx in out or not 0<=idx<len(keys):
                raise ValueError("índice histórico inválido/duplicado")
            quantity=row["uiTokenAmount"]
            value=quantity["amount"]
            decimals=quantity["decimals"]
            if (not isinstance(value,str) or not value.isascii() or
                not value.isdecimal() or type(decimals) is not int or
                not 0<=decimals<=18):
                raise ValueError("quantidade histórica inválida")
            out[idx]=(int(value),decimals,row.get("mint"),row.get("owner"),
                      row.get("programId"))
        return out
    pre,post=balances("pre"),balances("post")
    def vault(address,mint):
        if address not in keys:
            raise ValueError("vault ausente nas contas da transação")
        index=keys.index(address)
        if index not in pre or index not in post:
            raise ValueError("saldo pré/pós do vault incompleto")
        a,z=pre[index],post[index]
        if a[1:]!=z[1:] or a[2]!=mint or not a[3] or not a[4]:
            raise ValueError("mint/owner/decimals do vault inconsistentes")
        return HistoricalVaultBalance(
            address=address,mint=mint,owner=a[3],token_program=a[4],
            decimals=a[1],pre_raw=a[0],post_raw=z[0],
            delta_raw=z[0]-a[0],
        )
    vin=vault(target["input_vault"],target["input_mint"])
    vout=vault(target["output_vault"],target["output_mint"])
    return HistoricalCpmmState(
        signature=signature,slot=slot,pool=target["pool"],
        amm_config=target["amm_config"],program_id=target["program_id"],
        source_id=manifest.get("rpc_source","UNKNOWN"),
        observed_at=observed,available_at=available,raw_sha256=actual_hash,
        input_vault=vin,output_vault=vout,solana_network_fee_lamports=fee,
    )


@dataclass(frozen=True)
class HistoricalAccountWitness:
    account_id: str
    role: Literal["POOL_STATE","AMM_CONFIG","INPUT_VAULT","OUTPUT_VAULT"]
    slot: int
    available_at: datetime
    source_id: str
    raw_bytes: bytes
    sha256_hex: str
    provenance: Literal["UNKNOWN","RPC_DECLARED","INDEPENDENTLY_ATTESTED"]
    pre_swap_order_proven: bool


@dataclass(frozen=True)
class HistoricalCompleteness:
    status: Literal["UNKNOWN","CONFLICTED","LOCALLY_CONSISTENT_UNATTESTED"]
    missing: tuple[str,...]
    reasons: tuple[str,...]
    economic_replay_eligible: bool=False


def inspect_historical_witnesses(
    state: HistoricalCpmmState,
    witnesses: tuple[HistoricalAccountWitness,...],
    *, cutoff: datetime,
) -> HistoricalCompleteness:
    """Inventory account witnesses; never promote mere caller flags to proof.

    The protocol will require independently verified pre-swap account version
    order and owner/PDA binary validations before any actual reserve quote.
    """
    if not isinstance(state,HistoricalCpmmState):
        raise TypeError("histórico da transação inválido")
    if not isinstance(witnesses,tuple):
        raise TypeError("witnesses devem ser tupla")
    if not isinstance(cutoff,datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff sem fuso")
    needed={
        "POOL_STATE":state.pool,
        "AMM_CONFIG":state.amm_config,
        "INPUT_VAULT":state.input_vault.address,
        "OUTPUT_VAULT":state.output_vault.address,
    }
    used=set()
    conflicts=set()
    reasons={"provider_independent_attestation_not_implemented",
             "historical_account_binary_and_ownership_not_reconciled"}
    point=cutoff.astimezone(timezone.utc)
    for w in witnesses:
        if not isinstance(w,HistoricalAccountWitness):
            raise TypeError("histórico de conta inválido")
        if w.role not in needed or w.role in used:
            conflicts.add("role_invalid_or_duplicated")
            continue
        used.add(w.role)
        if w.account_id!=needed[w.role]:
            conflicts.add("account_identity_mismatch")
        if type(w.slot) is not int or w.slot<0 or w.slot>state.slot:
            conflicts.add("historical_slot_after_swap")
        if (not isinstance(w.available_at,datetime)
            or w.available_at.utcoffset() is None
            or w.available_at>point):
            conflicts.add("historical_data_after_cutoff")
        if not isinstance(w.raw_bytes,bytes) or not w.raw_bytes or sha256(w.raw_bytes).hexdigest()!=w.sha256_hex:
            conflicts.add("historical_raw_hash_mismatch")
        if not w.pre_swap_order_proven:
            reasons.add("pre_swap_order_unproven")
        # A field labelled INDEPENDENTLY_ATTESTED has no verifier here.
        if w.provenance!="INDEPENDENTLY_ATTESTED":
            reasons.add("account_provider_not_authenticated")
        else:
            reasons.add("external_attestation_not_cryptographically_checked")
    missing=tuple(sorted(set(needed)-used))
    if missing:
        reasons.add("historical_accounts_missing")
    status=("CONFLICTED" if conflicts else "UNKNOWN" if missing else
            "LOCALLY_CONSISTENT_UNATTESTED")
    return HistoricalCompleteness(
        status=status,missing=missing,reasons=tuple(sorted(reasons|conflicts)),
    )
