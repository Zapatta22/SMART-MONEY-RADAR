"""Adjacent observed CPMM transaction-boundary token-vault evidence.

This is NOT Geyser state, not PoolState writes, not a verified event stream.
Comparing exact account-level post and pre token balances may demonstrate
a local numeric match between two transactions with distinct slots; it does
not establish the absence of intermediate account writes or trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Literal

from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
from smart_money_radar.data_sources.solana_token_balance_deltas import decode_token_account_balance_deltas

Status = Literal["OBSERVED_BOUNDARY_MATCH","PARTIAL","UNKNOWN","CONFLICT"]


@dataclass(frozen=True)
class VaultBoundaryComparison:
    vault: str
    mint: str
    previous_post_raw: int | None
    next_pre_raw: int | None
    status: Status
    reasons: tuple[str,...]


@dataclass(frozen=True)
class TransactionBoundaryBridge:
    previous_signature: str
    next_signature: str
    previous_slot: int
    next_slot: int
    previous_raw_sha256: str
    next_raw_sha256: str
    pool: str
    status: Status
    vaults: tuple[VaultBoundaryComparison,...]
    reasons: tuple[str,...]
    state_write_proven: bool=False
    provider_independently_authenticated: bool=False
    intervening_writes_excluded: bool=False
    interval_coverage_complete: bool=False
    economic_execution_authorized: bool=False


def compare_cpmm_transaction_boundaries(
    *, previous_raw: bytes, next_raw: bytes,
    previous_signature: str, next_signature: str,
    previous_slot: int, next_slot: int,
    pool: str, vault_mints: dict[str,str],
    previous_available_at: datetime, next_available_at: datetime,
    cutoff: datetime,
) -> TransactionBoundaryBridge:
    if not isinstance(cutoff,datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff com fuso obrigatório")
    for t in (previous_available_at,next_available_at):
        if not isinstance(t,datetime) or t.utcoffset() is None:
            raise ValueError("disponibilidade inválida")
    if len(vault_mints)!=2 or any(not k or not v for k,v in vault_mints.items()):
        raise ValueError("dois vaults com mint obrigatórios")
    if any(not isinstance(x,bytes) or not x for x in (previous_raw,next_raw)):
        raise ValueError("RAW de transação obrigatório")
    if previous_slot>=next_slot:
        return TransactionBoundaryBridge(previous_signature,next_signature,
            previous_slot,next_slot,sha256(previous_raw).hexdigest(),
            sha256(next_raw).hexdigest(),pool,"UNKNOWN",(),
            ("order_within_same_slot_not_proven" if previous_slot==next_slot else "reversed_slots",))
    if (previous_available_at.astimezone(timezone.utc)>cutoff.astimezone(timezone.utc) or
        next_available_at.astimezone(timezone.utc)>cutoff.astimezone(timezone.utc)):
        return TransactionBoundaryBridge(previous_signature,next_signature,
            previous_slot,next_slot,sha256(previous_raw).hexdigest(),
            sha256(next_raw).hexdigest(),pool,"CONFLICT",(),("evidence_after_cutoff",))
    try:
        a,b=json.loads(previous_raw),json.loads(next_raw)
        for payload,signature,slot in ((a,previous_signature,previous_slot),(b,next_signature,next_slot)):
            tx=payload["result"]
            if (tx["transaction"]["signatures"][0]!=signature or
                tx["slot"]!=slot or tx["meta"]["err"] is not None):
                raise ValueError("signature_or_slot_mismatch")
            swaps=decode_raydium_cpmm_swaps(payload)
            if not any(s.accounts.pool_state==pool and
                       set(vault_mints)=={s.accounts.input_vault,s.accounts.output_vault}
                       for s in swaps):
                raise ValueError("wrong_cpmm_pool_or_vault")
        ab=decode_token_account_balance_deltas(a,include_unchanged=True)
        bb=decode_token_account_balance_deltas(b,include_unchanged=True)
        before={x.token_account:x for x in ab}
        after={x.token_account:x for x in bb}
        pairs=[]
        for vault,mint in sorted(vault_mints.items()):
            x,y=before.get(vault),after.get(vault)
            if x is None or y is None:
                pairs.append(VaultBoundaryComparison(vault,mint,None,None,"UNKNOWN",
                               ("balance_boundary_missing",)))
            elif x.mint!=mint or y.mint!=mint:
                pairs.append(VaultBoundaryComparison(vault,mint,x.post_amount_raw,y.pre_amount_raw,
                             "CONFLICT",("mint_conflict",)))
            elif x.post_amount_raw!=y.pre_amount_raw:
                pairs.append(VaultBoundaryComparison(vault,mint,x.post_amount_raw,y.pre_amount_raw,
                             "PARTIAL",("intermediate_vault_change_or_unobserved_transaction",)))
            else:
                pairs.append(VaultBoundaryComparison(vault,mint,x.post_amount_raw,y.pre_amount_raw,
                             "OBSERVED_BOUNDARY_MATCH",("matching_transaction_boundaries_not_write_stream",)))
        overall=("CONFLICT" if any(z.status=="CONFLICT" for z in pairs)
                 else "OBSERVED_BOUNDARY_MATCH" if all(z.status=="OBSERVED_BOUNDARY_MATCH" for z in pairs)
                 else "PARTIAL")
        reasons=("intermediate_account_writes_not_excluded",
                 "transaction_boundary_not_geyser_write",
                 "history_coverage_partial")
        return TransactionBoundaryBridge(
            previous_signature,next_signature,previous_slot,next_slot,
            sha256(previous_raw).hexdigest(),sha256(next_raw).hexdigest(),
            pool,overall,tuple(pairs),reasons)
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        return TransactionBoundaryBridge(previous_signature,next_signature,previous_slot,next_slot,
             sha256(previous_raw).hexdigest(),sha256(next_raw).hexdigest(),
             pool,"CONFLICT",(),("raw_or_scope_conflict",type(exc).__name__))
