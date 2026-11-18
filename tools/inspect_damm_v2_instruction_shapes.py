#!/usr/bin/env python3
"""Inspeciona o formato das instruções DAMM v2 em uma transação Mainnet.

Não persiste payloads RAW nem executa ordens. Emite somente índice, discriminator,
comprimento e estado de validação das instruções swap/swap2.
"""
from __future__ import annotations

import argparse
import json
import os

from smart_money_radar.data_sources.damm_v2_analyzer import _account_keys
from smart_money_radar.data_sources.damm_v2_decoder import (
    METEORA_DAMM_V2_PROGRAM_ID,
    SWAP2_DATA_LENGTH,
    SWAP2_DISCRIMINATOR,
    SWAP_DATA_LENGTH,
    SWAP_DISCRIMINATOR,
)
from validate_damm_v2_mainnet import DEFAULT_RPC, fetch_transaction


def _b58decode(value: str) -> bytes:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0
    for char in value:
        number = number * 58 + alphabet.index(char)
    decoded = (
        number.to_bytes((number.bit_length() + 7) // 8, "big")
        if number else b""
    )
    return bytes(len(value) - len(value.lstrip("1"))) + decoded


def _program_id(instruction: dict, keys: list[str]) -> str | None:
    direct = instruction.get("programId")
    if isinstance(direct, str):
        return direct
    index = instruction.get("programIdIndex")
    if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(keys):
        return keys[index]
    return None


def inspect(raw: dict, signature: str) -> dict:
    payload = raw.get("result", raw)
    tx = payload.get("transaction")
    meta = payload.get("meta")
    if not isinstance(tx, dict) or not isinstance(meta, dict):
        raise ValueError("transaction/meta ausentes")
    message = tx.get("message")
    if not isinstance(message, dict):
        raise ValueError("transaction.message ausente")
    keys = _account_keys(message, meta)
    found = []

    def inspect_one(item: object, outer_index: int, inner_index: int | None) -> None:
        if not isinstance(item, dict):
            return
        if _program_id(item, keys) != METEORA_DAMM_V2_PROGRAM_ID:
            return
        encoded = item.get("data")
        if not isinstance(encoded, str):
            return
        data = _b58decode(encoded)
        discriminator = data[:8]
        if discriminator == SWAP_DISCRIMINATOR:
            name, expected = "swap", SWAP_DATA_LENGTH
        elif discriminator == SWAP2_DISCRIMINATOR:
            name, expected = "swap2", SWAP2_DATA_LENGTH
        else:
            return
        found.append({
            "outer_instruction_index": outer_index,
            "inner_instruction_index": inner_index,
            "stack_height": item.get("stackHeight"),
            "instruction": name,
            "data_length": len(data),
            "expected_length": expected,
            "length_status": "VALID" if len(data) == expected else "UNSUPPORTED_LENGTH",
            "discriminator_hex": discriminator.hex(),
        })

    outer = message.get("instructions")
    if not isinstance(outer, list):
        raise ValueError("message.instructions ausente")
    for outer_index, item in enumerate(outer):
        inspect_one(item, outer_index, None)
    groups = meta.get("innerInstructions")
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("instructions"), list):
                continue
            outer_index = group.get("index")
            if not isinstance(outer_index, int) or isinstance(outer_index, bool):
                continue
            for inner_index, item in enumerate(group["instructions"]):
                inspect_one(item, outer_index, inner_index)

    return {
        "signature": signature,
        "slot": payload.get("slot"),
        "transaction_error": meta.get("err"),
        "damm_v2_swap_instruction_count": len(found),
        "instructions": found,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--rpc-url", default=os.environ.get(
        "SMR_DAMM_V2_SCAN_RPC_URL",
        os.environ.get("SMR_SOLANA_RPC_URL", DEFAULT_RPC),
    ))
    args = parser.parse_args()
    if not args.rpc_url.startswith("https://"):
        parser.error("RPC deve usar HTTPS")
    try:
        raw = fetch_transaction(
            args.rpc_url, args.signature,
            max_supported_transaction_version=1,
        )
        report = inspect(raw, args.signature)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "signature": args.signature,
            "status": "INSPECTION_ERROR",
            "reason": f"{type(exc).__name__}: {exc}",
        }, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
