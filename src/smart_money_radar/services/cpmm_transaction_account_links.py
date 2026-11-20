"""Conservative bindings: observed CPMM transaction evidence vs actual account writes.

The original Solana RPC transaction contains executed instructions and
transaction-boundary token balances, but not Geyser writes or continuous
account state. Do not equate transaction balance deltas to consecutive
pool snapshots. Existing decoders and Geyser update contract are reused.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from hashlib import sha256
import json
from typing import Literal

from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
from smart_money_radar.data_sources.solana_token_balance_deltas import decode_token_account_balance_deltas
from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate

LinkStatus=Literal["OBSERVED_TX_BOUNDARY","PROBABLE_INCOMPLETE","UNKNOWN","CONFLICT"]


@dataclass(frozen=True)
class CpmmAccountLink:
    signature:str
    slot:int
    pool:str
    account:str
    account_role:str
    status:LinkStatus
    transaction_delta_raw:int|None
    account_write_confirmed:bool
    transaction_raw_sha256:str
    evidence_available_at:datetime
    source_id:str
    reason_codes:tuple[str,...]
    verified_write_fingerprint:str|None=None
    executable_quote_proven:bool=False
    operation_authorized:bool=False


@dataclass(frozen=True)
class CpmmTransactionLinks:
    signature:str
    slot:int|None
    status:LinkStatus
    links:tuple[CpmmAccountLink,...]
    reasons:tuple[str,...]
    write_stream_complete:bool=False
    interval_economic_residual_raw:int|None=None
    same_slot_order_proven:bool=False
    independently_finalized:bool=False
    execution_authorized:bool=False


def bind_cpmm_transaction_accounts(
    *, raw:bytes,signature:str,listed_slot:int,pool:str,
    config:str, vault_high:str,vault_wsol:str,
    high_mint:str,wsol_mint:str,
    available_at:datetime,cutoff:datetime,source_id:str,
    account_updates:tuple[NormalizedAccountUpdate,...]=(),
)->CpmmTransactionLinks:
    """Only transaction-boundary deltas can be called observed without writes.

    Updates must arrive through the existing Geyser normalization contract.
    Their txn_signature is a correlation clue, not cryptographic proof.
    """
    if any(not isinstance(s,str) or not s for s in (signature,pool,config,vault_high,vault_wsol,
                                                    high_mint,wsol_mint,source_id)):
        raise ValueError("identidades obrigatórias")
    if len({pool,config,vault_high,vault_wsol})!=4:
        raise ValueError("escopo de contas ambíguo")
    if type(listed_slot) is not int or listed_slot<0:
        raise ValueError("slot inválido")
    if not isinstance(available_at,datetime) or available_at.utcoffset() is None:
        raise ValueError("disponibilidade sem fuso")
    if not isinstance(cutoff,datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff sem fuso")
    if not isinstance(raw,bytes) or not raw:
        return CpmmTransactionLinks(signature,listed_slot,"UNKNOWN",(),
             ("transaction_raw_missing",))
    if available_at>cutoff:
        return CpmmTransactionLinks(signature,listed_slot,"CONFLICT",(),
             ("evidence_after_cutoff",))
    digest=sha256(raw).hexdigest()
    try:
        j=json.loads(raw)
        tx=j.get("result")
        if not isinstance(tx,dict):
            return CpmmTransactionLinks(signature,listed_slot,"UNKNOWN",(),
                ("rpc_transaction_null",))
        if (tx.get("slot")!=listed_slot or
            tx["transaction"]["signatures"][0]!=signature or
            tx["meta"]["err"] is not None):
            return CpmmTransactionLinks(signature,listed_slot,"CONFLICT",(),
                ("transaction_identity_or_failure",))
        decoded=decode_raydium_cpmm_swaps(j)
        matches=[s for s in decoded if s.accounts.pool_state==pool]
        if not matches:
            return CpmmTransactionLinks(signature,listed_slot,"UNKNOWN",(),
                ("cpmm_pool_instruction_absent",))
        for swap in matches:
            a=swap.accounts
            if a.amm_config!=config or {a.input_vault,a.output_vault}!={vault_high,vault_wsol}:
                return CpmmTransactionLinks(signature,listed_slot,"CONFLICT",(),
                    ("cpmm_account_scope_conflict",))
            direction={a.input_vault:a.input_token_mint,a.output_vault:a.output_token_mint}
            if direction.get(vault_high)!=high_mint or direction.get(vault_wsol)!=wsol_mint:
                return CpmmTransactionLinks(signature,listed_slot,"CONFLICT",(),
                    ("cpmm_token_mint_conflict",))
        balances=decode_token_account_balance_deltas(j,include_unchanged=True)
        by_account={x.token_account:x for x in balances}
        accounts=((pool,"POOLSTATE",None),(config,"AMMCONFIG",None),
                  (vault_high,"VAULT_HIGH",high_mint),(vault_wsol,"VAULT_WSOL",wsol_mint))
        links=[]
        for pubkey,role,mint in accounts:
            reasons=set()
            delta=None
            status="PROBABLE_INCOMPLETE"
            if role.startswith("VAULT"):
                bal=by_account.get(pubkey)
                if bal is None:
                    reasons.add("transaction_boundary_balance_absent")
                elif bal.mint!=mint:
                    status="CONFLICT"
                    reasons.add("vault_balance_mint_conflict")
                else:
                    delta=bal.delta_raw
                    status="OBSERVED_TX_BOUNDARY"
                    reasons.add("transaction_boundary_not_instruction_write")
            else:
                reasons.add("no_binary_account_write_in_transaction_rpc")
            matching=[u for u in account_updates if (
                u.txn_signature==signature and u.slot==listed_slot and u.pubkey==pubkey)]
            if matching:
                # An update with merely a caller-supplied signature is not
                # provider-certified; preserve it as a correlation only.
                if len({(u.write_version,u.state_hash) for u in matching})!=len(matching):
                    reasons.add("duplicate_update_claim")
                    status="CONFLICT"
                else:
                    reasons.add("provider_write_provenance_unattested")
            else:
                reasons.add("geyser_account_write_missing")
            links.append(CpmmAccountLink(
                signature=signature,slot=listed_slot,pool=pool,account=pubkey,
                account_role=role,status=status,transaction_delta_raw=delta,
                account_write_confirmed=False,transaction_raw_sha256=digest,
                evidence_available_at=available_at.astimezone(timezone.utc),
                source_id=source_id,reason_codes=tuple(sorted(reasons))))
        overall=("CONFLICT" if any(l.status=="CONFLICT" for l in links)
                 else "OBSERVED_TX_BOUNDARY" if any(l.status=="OBSERVED_TX_BOUNDARY" for l in links)
                 else "PROBABLE_INCOMPLETE")
        return CpmmTransactionLinks(signature,listed_slot,overall,tuple(links),
                                    ("intermediate_account_writes_unobserved",
                                     "snapshot_boundary_not_transaction_state"))
    except (ValueError,TypeError,KeyError,IndexError) as e:
        return CpmmTransactionLinks(signature,listed_slot,"CONFLICT",(),
            ("transaction_decode_conflict",type(e).__name__))
