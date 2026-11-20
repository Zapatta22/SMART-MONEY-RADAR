"""Fail-closed RPC account-envelope checks for Raydium CPMM pool/config.

Supports the legacy two-account envelope check and a bounded four-account
snapshot tied to the archived request, pool layout and mainnet authority.
Structural checks do not authenticate the RPC provider.
"""
import base64
import hashlib
import json
from dataclasses import dataclass

from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID


from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID,
    _decode_base58,
)
from smart_money_radar.domain.cpmm_binary_state import (
    AmmConfigFields,
    PoolStateFields,
    _pubkey,
    _u64,
    decode_amm_config,
    decode_pool_state,
)

# find_program_address([b"vault_and_lp_mint_auth_seed"], RAYDIUM_CPMM_PROGRAM_ID)
CPMM_VAULT_AUTHORITY = "GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL"
CPMM_VAULT_AUTH_BUMP = 253
_MAX_ARCHIVED_RPC_BYTES = 64 * 1024
_MAX_U64 = (1 << 64) - 1


@dataclass(frozen=True)
class CpmmSameSlotState:
    """Structurally checked pool accounts, with no provider authenticity claim."""

    slot: int
    pool_address: str
    request_sha256: str
    response_sha256: str
    pool: PoolStateFields
    configuration: AmmConfigFields
    reserve_0_raw: int
    reserve_1_raw: int


def _decode_owned_account(account: dict, program: str) -> bytes:
    if (not isinstance(account, dict) or account.get("owner") != program
            or account.get("executable") is not False):
        raise ValueError("proprietário de programa da conta diverge")
    data = account.get("data")
    if (not isinstance(data, list) or len(data) != 2
            or data[1] != "base64" or not isinstance(data[0], str)):
        raise ValueError("dados binários obrigatórios")
    try:
        decoded = base64.b64decode(data[0], validate=True)
    except ValueError as exc:
        raise ValueError("base64 inválido") from exc
    if not decoded:
        raise ValueError("conta binária vazia")
    return decoded


def _read_archived_rpc(raw: bytes) -> dict:
    def unique_fields(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("campo RPC duplicado")
            value[key] = item
        return value

    if not isinstance(raw, bytes) or not 0 < len(raw) <= _MAX_ARCHIVED_RPC_BYTES:
        raise ValueError("tamanho do arquivo RPC inválido")
    value = json.loads(raw, object_pairs_hook=unique_fields)
    if not isinstance(value, dict) or value.get("jsonrpc") != "2.0" or "error" in value:
        raise ValueError("envelope JSON-RPC inválido")
    return value


def _effective_vault(account: dict, mint: str, reserved: tuple[int, int, int]) -> int:
    data = _decode_owned_account(account, SPL_TOKEN_PROGRAM_ID)
    if (len(data) != 165 or data[108] != 1 or _pubkey(data[:32]) != mint
            or _pubkey(data[32:64]) != CPMM_VAULT_AUTHORITY):
        raise ValueError("mint ou autoridade do vault SPL diverge")
    spendable = _u64(data, 64) - sum(reserved)
    if spendable <= 0:
        raise ValueError("vault sem reserva efetiva disponível")
    return spendable


def validate_finalized_cpmm_snapshot(
    *, raw_request: bytes, raw_response: bytes, expected_slot: int,
    expected_pool: str, block_time: int,
) -> CpmmSameSlotState:
    """Check a same-request snapshot against a caller-selected pool and slot.

    The request and response are archival inputs; matching IDs and owner fields
    do not authenticate an RPC provider. The caller supplies the corresponding
    block time. Only legacy SPL pools with creator fees disabled are supported.
    """
    if type(expected_slot) is not int or not 0 <= expected_slot <= _MAX_U64:
        raise ValueError("slot esperado inválido")
    if type(block_time) is not int or not 0 <= block_time <= _MAX_U64:
        raise ValueError("horário do bloco inválido")
    request, response = _read_archived_rpc(raw_request), _read_archived_rpc(raw_response)
    rpc_id = request.get("id")
    if ((type(rpc_id) is not int and (not isinstance(rpc_id, str) or not rpc_id.strip()))
            or type(response.get("id")) is not type(rpc_id) or response["id"] != rpc_id):
        raise ValueError("identificador JSON-RPC diverge")
    params = request.get("params")
    if (request.get("method") != "getMultipleAccounts" or not isinstance(params, list)
            or len(params) != 2 or not isinstance(params[1], dict)
            or params[1].get("commitment") != "finalized" or params[1].get("encoding") != "base64"
            or "dataSlice" in params[1]):
        raise ValueError("requisição exige getMultipleAccounts finalizado e base64 integral")
    addresses = params[0]
    if (not isinstance(addresses, list) or len(addresses) != 4 or addresses[0] != expected_pool
            or any(not isinstance(key, str) or not 32 <= len(key) <= 44
                   or len(_decode_base58(key)) != 32 for key in addresses)
            or len(set(addresses)) != 4):
        raise ValueError("endereços do snapshot CPMM inválidos")
    try:
        result = response["result"]
        slot = result["context"]["slot"]
        accounts = result["value"]
    except (KeyError, TypeError) as exc:
        raise ValueError("resposta do snapshot CPMM incompleta") from exc
    if type(slot) is not int or slot != expected_slot or not isinstance(accounts, list) or len(accounts) != 4:
        raise ValueError("slot ou quantidade de contas do snapshot diverge")
    pool = decode_pool_state(_decode_owned_account(accounts[0], RAYDIUM_CPMM_PROGRAM_ID))
    configuration = decode_amm_config(_decode_owned_account(accounts[1], RAYDIUM_CPMM_PROGRAM_ID))
    if addresses[1:] != [pool.amm_config, pool.token_0_vault, pool.token_1_vault]:
        raise ValueError("ordem ou vínculo dos vaults e configuração CPMM diverge")
    if (pool.auth_bump != CPMM_VAULT_AUTH_BUMP or pool.status & 4 or block_time < pool.open_time
            or pool.enable_creator_fee or pool.token_0_program != SPL_TOKEN_PROGRAM_ID
            or pool.token_1_program != SPL_TOKEN_PROGRAM_ID or pool.token_0_mint == pool.token_1_mint
            or configuration.trade_fee_rate >= 1_000_000):
        raise ValueError("estado ou modelo de taxas CPMM fora do escopo")
    reserve_0 = _effective_vault(accounts[2], pool.token_0_mint, (
        pool.protocol_fees_token_0, pool.fund_fees_token_0, pool.creator_fees_token_0,
    ))
    reserve_1 = _effective_vault(accounts[3], pool.token_1_mint, (
        pool.protocol_fees_token_1, pool.fund_fees_token_1, pool.creator_fees_token_1,
    ))
    return CpmmSameSlotState(
        slot, expected_pool, hashlib.sha256(raw_request).hexdigest(),
        hashlib.sha256(raw_response).hexdigest(), pool, configuration, reserve_0, reserve_1,
    )


def validate_pool_config_rpc_envelope(*, raw_payload: bytes, expected_slot: int,
                                      expected_pool: str, expected_config: str):
    """Validate getMultipleAccounts([pool_state, amm_config], encoding=base64).

    Account order must match the request; expected addresses must come from
    separately reconciled CPMM swap accounts. No executable quote is produced.
    """
    if not isinstance(raw_payload, bytes) or not raw_payload:
        raise ValueError("payload RAW obrigatório")
    if type(expected_slot) is not int or expected_slot < 0:
        raise ValueError("slot inválido")
    if (not isinstance(expected_pool, str) or not expected_pool.strip()
            or not isinstance(expected_config, str) or not expected_config.strip()
            or expected_pool == expected_config):
        raise ValueError("identidade pool/config inválida")
    try:
        response = json.loads(raw_payload)
        if not isinstance(response, dict) or "error" in response:
            raise ValueError("RPC com erro")
        result = response["result"]
        slot = result["context"]["slot"]
        accounts = result["value"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("envelope RPC inválido") from exc
    if type(slot) is not int or slot != expected_slot:
        raise ValueError("slot divergente")
    if not isinstance(accounts, list) or len(accounts) != 2:
        raise ValueError("pool/config ausentes")
    hashes = []
    for account in accounts:
        decoded = _decode_owned_account(account, RAYDIUM_CPMM_PROGRAM_ID)
        hashes.append(hashlib.sha256(decoded).hexdigest())
    return {
        "slot": slot,
        "pool": expected_pool,
        "config": expected_config,
        "rpc_raw_sha256": hashlib.sha256(raw_payload).hexdigest(),
        "pool_data_sha256": hashes[0],
        "config_data_sha256": hashes[1],
        "verification": "PROGRAM_OWNER_AND_RAW_HASH_ONLY_LAYOUT_UNVERIFIED",
    }
