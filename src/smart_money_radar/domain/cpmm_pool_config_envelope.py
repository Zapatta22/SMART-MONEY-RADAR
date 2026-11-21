"""Fail-closed RPC account-envelope checks for Raydium CPMM pool/config.

Checks ownership, slot and RAW payload binding. Does not decode the binary
PoolState/AmmConfig layouts, validate PDAs or prove provider authenticity.
"""
import base64
import hashlib
import json

from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID

# Existing Raydium CPMM vault authority PDA, used by the original launch decoder.
# This constant checks an account role; it does not authenticate the RPC provider.
CPMM_VAULT_AUTHORITY = "GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL"


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
        if (not isinstance(account, dict)
                or account.get("owner") != RAYDIUM_CPMM_PROGRAM_ID
                or account.get("executable") is not False):
            raise ValueError("conta não pertence ao programa CPMM")
        data = account.get("data")
        if (not isinstance(data, list) or len(data) != 2
                or data[1] != "base64" or not isinstance(data[0], str)):
            raise ValueError("dados binários obrigatórios")
        try:
            decoded = base64.b64decode(data[0], validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("base64 inválido") from exc
        if not decoded:
            raise ValueError("conta binária vazia")
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
