"""Raydium CPMM SwapEvent evidence from the ORIGINAL first Solana mainnet RAW.

Anchor discriminator, 170-byte Borsh layout and constant-product integer
rounding follow public raydium-cp-swap states/events.rs, curve/calculator.rs,
curve/constant_product.rs and curve/fees.rs.

Event values are *historical values emitted in a transaction*, NOT external
PoolState/AmmConfig archive or a price available BEFORE this transaction.
The first observation was two days after the block. Always fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from struct import unpack_from
import base64
import json

from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID, RaydiumCpmmSwapBaseInput
from smart_money_radar.services.historical_cpmm_state import reconstruct_tx_vaults

_EVENT_DISCRIMINATOR = sha256(b"event:SwapEvent").digest()[:8]
_EVENT_LENGTH = 170
_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58(raw: bytes) -> str:
    value=int.from_bytes(raw,"big")
    encoded=""
    while value:
        value,rem=divmod(value,58)
        encoded=_ALPHABET[rem]+encoded
    return "1"*(len(raw)-len(raw.lstrip(bytes([0]))))+encoded


@dataclass(frozen=True)
class CpmmSwapEvent:
    pool: str
    input_vault_before_raw: int
    output_vault_before_raw: int
    input_amount_raw: int
    output_amount_raw: int
    input_transfer_fee_raw: int
    output_transfer_fee_raw: int
    base_input: bool
    input_mint: str
    output_mint: str
    trade_fee_raw: int
    creator_fee_raw: int
    creator_fee_on_input: bool


@dataclass(frozen=True)
class ObservedSwapEconomicProof:
    signature: str
    slot: int
    pool: str
    transaction_raw_sha256: str
    event_raw_sha256: str
    observation_available_at: datetime
    instruction_index: int
    event: CpmmSwapEvent
    calculated_gross_output_raw: int
    calculated_net_output_raw: int
    observed_output_raw: int
    difference_raw: int
    status: str = "OBSERVED_EVENT_INTEGER_RECONCILED_UNATTESTED"
    network_provider_independently_authenticated: bool = False
    historical_poolstate_snapshot_verified: bool = False
    historical_ammconfig_snapshot_verified: bool = False
    trade_fee_rate_verified_from_ammconfig: bool = False
    quote_available_before_swap: bool = False
    executable_quote_proven: bool = False
    replay_eligible: bool = False


def decode_cpmm_swap_event(raw: bytes) -> CpmmSwapEvent:
    """Decode exact Anchor SwapEvent bytes and reject ambiguity."""
    if not isinstance(raw,bytes) or len(raw)!=_EVENT_LENGTH:
        raise ValueError("SwapEvent RAW de tamanho incorreto")
    if raw[:8]!=_EVENT_DISCRIMINATOR:
        raise ValueError("discriminador SwapEvent incorreto")
    offset=8
    def pubkey():
        nonlocal offset
        result=_base58(raw[offset:offset+32])
        offset+=32
        return result
    def u64():
        nonlocal offset
        result=unpack_from("<Q",raw,offset)[0]
        offset+=8
        return result
    def boolean():
        nonlocal offset
        val=raw[offset]
        offset+=1
        if val not in (0,1):
            raise ValueError("booleano SwapEvent inválido")
        return bool(val)
    pool=pubkey()
    input_before=u64()
    output_before=u64()
    input_amount=u64()
    output_amount=u64()
    transfer_in=u64()
    transfer_out=u64()
    base_input=boolean()
    mint_in=pubkey()
    mint_out=pubkey()
    trade=u64()
    creator=u64()
    creator_on_input=boolean()
    if offset!=len(raw) or not all((input_before,output_before,input_amount,output_amount)):
        raise ValueError("SwapEvent com campos econômicos incompletos")
    if mint_in==mint_out or trade>input_amount:
        raise ValueError("SwapEvent com mints/taxa inválidos")
    return CpmmSwapEvent(
        pool,input_before,output_before,input_amount,output_amount,
        transfer_in,transfer_out,base_input,mint_in,mint_out,
        trade,creator,creator_on_input,
    )


def reconcile_observed_swap_event(
    *, transaction_raw: bytes, manifest: dict, cutoff: datetime,
) -> ObservedSwapEconomicProof:
    """Reproduce ONE real CPMM swap with integer arithmetic and exact event.

    Underlying vault deltas are from transaction boundaries; event values are
    specific to the swap instruction. Equal numbers must never be interpreted
    as a quote available before event or an independently authenticated RPC.
    """
    state=reconstruct_tx_vaults(original_raw=transaction_raw,
                                manifest=manifest,cutoff=cutoff)
    tx=json.loads(transaction_raw)["result"]
    logs=tx["meta"].get("logMessages")
    if not isinstance(logs,list):
        raise ValueError("logs SwapEvent ausentes")
    # Match logs to the actual CPMM invocation; a free-floating Program data
    # line is not accepted as evidence.
    invoke=f"Program {RAYDIUM_CPMM_PROGRAM_ID} invoke [1]"
    end=f"Program {RAYDIUM_CPMM_PROGRAM_ID} success"
    active=False
    candidates=[]
    for line in logs:
        if line==invoke:
            if active:
                raise ValueError("invocação CPMM aninhada ambígua")
            active=True
        elif line==end:
            if not active:
                raise ValueError("fim CPMM sem início")
            active=False
        elif line.startswith("Program data: "):
            if not active:
                continue
            value=line[len("Program data: "):]
            try:
                encoded=base64.b64decode(value,validate=True)
            except (ValueError,base64.binascii.Error) as exc:
                raise ValueError("evento RPC base64 adulterado") from exc
            if encoded[:8]==_EVENT_DISCRIMINATOR:
                candidates.append(encoded)
    if active or len(candidates)!=1:
        raise ValueError("SwapEvent único e ordenado não demonstrado")
    event_bytes=candidates[0]
    ev=decode_cpmm_swap_event(event_bytes)
    target=manifest["decoded_cpmm_swaps"][0]
    swaps=decode_raydium_cpmm_swaps({"result":tx})
    match=[s for s in swaps if
           s.accounts.pool_state==ev.pool==state.pool and
           s.accounts.input_token_mint==ev.input_mint==state.input_vault.mint and
           s.accounts.output_token_mint==ev.output_mint==state.output_vault.mint and
           s.instruction_index==target["instruction_index"] and
           isinstance(s.instruction,RaydiumCpmmSwapBaseInput)]
    if len(match)!=1 or not ev.base_input:
        raise ValueError("SwapEvent não coincide com instrução CPMM")
    if (ev.input_transfer_fee_raw!=0 or ev.output_transfer_fee_raw!=0
        or ev.creator_fee_on_input or ev.creator_fee_raw>ev.output_vault_before_raw):
        raise ValueError("transferências/taxas exigem caminho econômico específico")
    if (state.input_vault.delta_raw!=ev.input_amount_raw or
        state.output_vault.delta_raw!=-ev.output_amount_raw):
        raise ValueError("deltas de vault e SwapEvent divergem")
    # Per Raydium source: trade fee is deducted from input, constant-product
    # integer output uses floor, creator fee on output is then deducted.
    net_input=ev.input_amount_raw-ev.trade_fee_raw
    gross=(net_input*ev.output_vault_before_raw)//(ev.input_vault_before_raw+net_input)
    net=gross-ev.creator_fee_raw
    if net<=0 or net!=ev.output_amount_raw:
        raise ValueError("reconciliação CPMM econômica divergente")
    return ObservedSwapEconomicProof(
        signature=state.signature,slot=state.slot,pool=state.pool,
        transaction_raw_sha256=state.raw_sha256,
        event_raw_sha256=sha256(event_bytes).hexdigest(),
        observation_available_at=state.available_at,
        instruction_index=target["instruction_index"],event=ev,
        calculated_gross_output_raw=gross,
        calculated_net_output_raw=net,
        observed_output_raw=ev.output_amount_raw,
        difference_raw=net-ev.output_amount_raw,
    )
