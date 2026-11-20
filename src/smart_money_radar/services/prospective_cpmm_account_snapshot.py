"""Conservative point-in-time CPMM accounts snapshot (prospective only).

A single getMultipleAccounts response supplies pool/config and both SPL
vaults in ONE RPC context. The data may be used to study the *present at
collection*, never to retroactively assert the state before a past swap.
Reuses existing Raydium PoolState/AmmConfig binary decoders and identity
checks; owner, PDA, operator and archival provenance remain non-attested.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import base64
import json

from smart_money_radar.domain.cpmm_binary_state import (
    decode_pool_state, decode_amm_config, verify_pool_swap_identity, _pubkey,
)
from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID

SPL_TOKEN_PROGRAM="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


@dataclass(frozen=True)
class ProspectiveCpmmSnapshot:
    status: str
    reasons: tuple[str,...]
    source_id: str
    endpoint: str
    pool: str
    amm_config: str
    slot: int | None
    observed_at: datetime
    available_at: datetime
    response_sha256: str
    account_sha256: tuple[str,...]
    input_vault_raw: int | None
    output_vault_raw: int | None
    effective_input_raw: int | None
    effective_output_raw: int | None
    declared_trade_fee_rate: int | None
    declared_creator_fee_rate: int | None
    pre_swap_state_of_original_tx: bool=False
    provider_independently_authenticated: bool=False
    chronological_instruction_order_proven: bool=False
    executable_quote_proven: bool=False
    operational_authorized: bool=False


def inspect_prospective_cpmm_response(
    *, response_raw: bytes, source_id: str, endpoint: str,
    observed_at: datetime, available_at: datetime,
    pool: str, amm_config: str, input_vault: str,
    output_vault: str, input_mint: str, output_mint: str,
    authority: str, input_token_program: str, output_token_program: str,
    original_swap_slot: int,
) -> ProspectiveCpmmSnapshot:
    """Validate one four-account snapshot, never promote as historical proof."""
    names=(source_id,endpoint,pool,amm_config,input_vault,output_vault,
           input_mint,output_mint,authority,input_token_program,output_token_program)
    if any(not isinstance(x,str) or not x.strip() for x in names):
        raise ValueError("escopo de contas incompleto")
    if len({pool,amm_config,input_vault,output_vault})!=4:
        raise ValueError("identidades repetidas")
    if type(original_swap_slot) is not int or original_swap_slot<0:
        raise ValueError("slot de referência inválido")
    if (not isinstance(observed_at,datetime) or observed_at.utcoffset() is None
        or not isinstance(available_at,datetime) or available_at.utcoffset() is None
        or observed_at>available_at):
        raise ValueError("observação ou disponibilidade inválida")
    if not isinstance(response_raw,bytes) or not response_raw:
        raise ValueError("resposta RAW ausente")
    digest=sha256(response_raw).hexdigest()
    source=source_id
    observed=observed_at.astimezone(timezone.utc)
    available=available_at.astimezone(timezone.utc)
    status="UNKNOWN"
    reasons=set()
    slot=None
    account_hashes=()
    input_raw=output_raw=effective_in=effective_out=None
    trade=creator=None
    try:
        payload=json.loads(response_raw)
        if not isinstance(payload,dict) or "error" in payload:
            raise ValueError("RPC inválido ou com erro")
        result=payload["result"]
        slot=result["context"]["slot"]
        accounts=result["value"]
        if type(slot) is not int or slot<0 or not isinstance(accounts,list) or len(accounts)!=4:
            raise ValueError("resposta sem quatro contas/slot")
        if slot<=original_swap_slot:
            raise ValueError("contexto não posterior ao swap original")
        if any(not isinstance(a,dict) for a in accounts):
            raise ValueError("conta ausente no RPC")
        decoded=[]
        hashes=[]
        for i,a in enumerate(accounts):
            expected_owner=RAYDIUM_CPMM_PROGRAM_ID if i<2 else (
                input_token_program if i==2 else output_token_program)
            if (a.get("owner")!=expected_owner or a.get("executable") is not False):
                raise ValueError("owner/executable incompatível")
            val=a.get("data")
            if (not isinstance(val,list) or len(val)!=2 or val[1]!="base64"
                or not isinstance(val[0],str)):
                raise ValueError("formato da conta incompatível")
            raw=base64.b64decode(val[0],validate=True)
            if not raw:
                raise ValueError("binário da conta vazio")
            decoded.append(raw)
            hashes.append(sha256(raw).hexdigest())
        account_hashes=tuple(hashes)
        state=decode_pool_state(decoded[0])
        config=decode_amm_config(decoded[1])
        verify_pool_swap_identity(
            state,config,amm_config=amm_config,
            input_vault=input_vault,output_vault=output_vault,
            input_mint=input_mint,output_mint=output_mint,
            input_token_program=input_token_program,
            output_token_program=output_token_program)
        if input_token_program!=SPL_TOKEN_PROGRAM or output_token_program!=SPL_TOKEN_PROGRAM:
            raise ValueError("SPL Token-2022 precisa de auditoria própria")
        def vault(raw,mint,program):
            if len(raw)!=165 or raw[108]!=1:
                raise ValueError("layout/estado SPL vault incompatível")
            if _pubkey(raw[:32])!=mint or _pubkey(raw[32:64])!=authority:
                raise ValueError("mint/autoridade vault incompatível")
            return int.from_bytes(raw[64:72],"little")
        input_raw=vault(decoded[2],input_mint,input_token_program)
        output_raw=vault(decoded[3],output_mint,output_token_program)
        if state.token_0_vault==input_vault:
            fees_in=(state.protocol_fees_token_0+state.fund_fees_token_0+
                     state.creator_fees_token_0)
            fees_out=(state.protocol_fees_token_1+state.fund_fees_token_1+
                      state.creator_fees_token_1)
        else:
            fees_in=(state.protocol_fees_token_1+state.fund_fees_token_1+
                     state.creator_fees_token_1)
            fees_out=(state.protocol_fees_token_0+state.fund_fees_token_0+
                      state.creator_fees_token_0)
        if input_raw<=fees_in or output_raw<=fees_out:
            raise ValueError("saldos vault menores que taxas acumuladas")
        effective_in=input_raw-fees_in
        effective_out=output_raw-fees_out
        trade=config.trade_fee_rate
        creator=config.creator_fee_rate
        reasons.add("provider_independent_attestation_missing")
        reasons.add("snapshot_after_original_swap_not_historical")
        reasons.add("instruction_level_order_not_attested")
        status="RPC_DECLARED_PROSPECTIVE_ONLY"
    except (KeyError,TypeError,ValueError,IndexError,OverflowError,
            base64.binascii.Error) as exc:
        reasons.add("incomplete_or_conflicted_snapshot")
        reasons.add(type(exc).__name__)
        status="UNKNOWN"
    return ProspectiveCpmmSnapshot(
        status=status,reasons=tuple(sorted(reasons)),source_id=source,
        endpoint=endpoint,pool=pool,amm_config=amm_config,slot=slot,
        observed_at=observed,available_at=available,response_sha256=digest,
        account_sha256=account_hashes,input_vault_raw=input_raw,
        output_vault_raw=output_raw,effective_input_raw=effective_in,
        effective_output_raw=effective_out,declared_trade_fee_rate=trade,
        declared_creator_fee_rate=creator,
    )
