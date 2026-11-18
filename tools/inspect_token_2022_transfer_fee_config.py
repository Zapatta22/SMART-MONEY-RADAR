#!/usr/bin/env python3
"""Inspeciona TransferFeeConfig de um mint Token-2022 no estado RPC atual.

A saída deixa explícito que getAccountInfo é um snapshot atual, não um snapshot
histórico do slot da transação.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.request


TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
TRANSFER_FEE_CONFIG_EXTENSION_TYPE = 1
TRANSFER_FEE_CONFIG_LENGTH = 108


def rpc_call(endpoint: str, method: str, params: list) -> dict:
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    }).encode()
    request = urllib.request.Request(
        endpoint, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.loads(response.read().decode())
    if payload.get("error"):
        raise RuntimeError(f"{method}: {payload['error']}")
    return payload["result"]


def _parse_transfer_fee_config(data: bytes) -> dict | None:
    # Token-2022 pads the base Mint (82 bytes) to the 165-byte base account
    # length, stores AccountType at byte 165, then starts TLV at byte 166.
    if len(data) <= 166:
        return None
    offset = 166
    while offset + 4 <= len(data):
        extension_type = int.from_bytes(data[offset:offset + 2], "little")
        extension_length = int.from_bytes(data[offset + 2:offset + 4], "little")
        offset += 4
        if extension_type == 0 and extension_length == 0:
            break
        end = offset + extension_length
        if end > len(data):
            raise ValueError("TLV Token-2022 truncado")
        value = data[offset:end]
        if extension_type == TRANSFER_FEE_CONFIG_EXTENSION_TYPE:
            if extension_length != TRANSFER_FEE_CONFIG_LENGTH:
                raise ValueError(
                    f"TransferFeeConfig length inesperado: {extension_length}"
                )
            withheld_amount = int.from_bytes(value[64:72], "little")
            older = {
                "epoch": int.from_bytes(value[72:80], "little"),
                "maximum_fee": int.from_bytes(value[80:88], "little"),
                "basis_points": int.from_bytes(value[88:90], "little"),
            }
            newer = {
                "epoch": int.from_bytes(value[90:98], "little"),
                "maximum_fee": int.from_bytes(value[98:106], "little"),
                "basis_points": int.from_bytes(value[106:108], "little"),
            }
            return {
                "withheld_amount": withheld_amount,
                "older_transfer_fee": older,
                "newer_transfer_fee": newer,
            }
        offset = end
    return None


def inspect(endpoint: str, mint: str, transaction_slot: int | None) -> dict:
    account = rpc_call(endpoint, "getAccountInfo", [
        mint, {"encoding": "base64", "commitment": "finalized"},
    ])
    value = account.get("value")
    if not isinstance(value, dict):
        raise ValueError("mint não encontrado")
    owner = value.get("owner")
    if owner != TOKEN_2022_PROGRAM_ID:
        raise ValueError(f"mint não pertence ao Token-2022: {owner}")
    encoded = value.get("data")
    if not isinstance(encoded, list) or not encoded:
        raise ValueError("dados base64 do mint ausentes")
    data = base64.b64decode(encoded[0])
    config = _parse_transfer_fee_config(data)
    epoch_info = rpc_call(endpoint, "getEpochInfo", [{"commitment": "finalized"}])
    schedule = rpc_call(endpoint, "getEpochSchedule", [])
    transaction_epoch = None
    if transaction_slot is not None:
        first_normal_slot = schedule["firstNormalSlot"]
        first_normal_epoch = schedule["firstNormalEpoch"]
        slots_per_epoch = schedule["slotsPerEpoch"]
        if transaction_slot >= first_normal_slot:
            transaction_epoch = (
                first_normal_epoch
                + (transaction_slot - first_normal_slot) // slots_per_epoch
            )
    return {
        "mint": mint,
        "owner": owner,
        "account_data_length": len(data),
        "rpc_context_slot": account.get("context", {}).get("slot"),
        "transaction_slot": transaction_slot,
        "transaction_epoch_estimate": transaction_epoch,
        "current_epoch": epoch_info.get("epoch"),
        "snapshot_scope": "current finalized account state; not historical proof at transaction_slot",
        "transfer_fee_config_present": config is not None,
        "transfer_fee_config": config,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mint", required=True)
    parser.add_argument("--transaction-slot", type=int)
    parser.add_argument("--rpc-url", default=os.environ.get(
        "SMR_DAMM_V2_SCAN_RPC_URL",
        os.environ.get("SMR_SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
    ))
    args = parser.parse_args()
    try:
        print(json.dumps(
            inspect(args.rpc_url, args.mint, args.transaction_slot),
            ensure_ascii=False, indent=2,
        ))
        return 0
    except Exception as exc:
        print(json.dumps({
            "mint": args.mint,
            "status": "INSPECTION_ERROR",
            "reason": f"{type(exc).__name__}: {exc}",
        }, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
