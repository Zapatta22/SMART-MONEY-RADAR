"""Decodificação estrutural de swaps CPMM em payloads getTransaction.

Escopo: instruções externas do message.instructions. CPI/innerInstructions e
reconstrução de valores efetivos permanecem fora deste módulo.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from smart_money_radar.data_sources.raydium_cpmm_accounts import (
    RaydiumCpmmAccounts,
    decode_raydium_cpmm_accounts,
)
from smart_money_radar.data_sources.raydium_cpmm_decoder import (
    RAYDIUM_CPMM_PROGRAM_ID,
    RaydiumCpmmSwapInstruction,
    decode_raydium_cpmm_instruction,
)


ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


@dataclass(frozen=True)
class RaydiumCpmmDecodedSwap:
    instruction_index: int
    instruction: RaydiumCpmmSwapInstruction
    accounts: RaydiumCpmmAccounts


def _decode_base58(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("data da instrução deve ser uma string base58 não vazia")

    number = 0
    try:
        for char in value:
            number = number * 58 + ALPHABET.index(char)
    except ValueError as exc:
        raise ValueError(
            "data da instrução contém caractere base58 inválido"
        ) from exc

    decoded = number.to_bytes((number.bit_length() + 7) // 8, "big")
    leading_zeros = len(value) - len(value.lstrip("1"))
    return b"\x00" * leading_zeros + decoded


def _account_keys(
    message: Mapping[str, Any],
    meta: Mapping[str, Any],
) -> list[str]:
    raw_keys = message.get("accountKeys")
    if not isinstance(raw_keys, list):
        raise ValueError("message.accountKeys ausente ou inválido")

    keys = []
    for item in raw_keys:
        key = item.get("pubkey") if isinstance(item, dict) else item
        if not isinstance(key, str) or not key:
            raise ValueError("accountKeys contém chave inválida")
        keys.append(key)

    loaded = meta.get("loadedAddresses", {})
    if not isinstance(loaded, dict):
        raise ValueError("meta.loadedAddresses inválido")

    for category in ("writable", "readonly"):
        values = loaded.get(category, [])
        if not isinstance(values, list):
            raise ValueError(f"loadedAddresses.{category} inválido")
        if any(not isinstance(key, str) or not key for key in values):
            raise ValueError(
                f"loadedAddresses.{category} contém chave inválida"
            )
        keys.extend(values)

    return keys


def decode_raydium_cpmm_swaps(
    transaction: dict[str, Any],
) -> list[RaydiumCpmmDecodedSwap]:
    """Decodifica swaps CPMM externos; não classifica BUY/SELL nem CPI."""

    if not isinstance(transaction, dict):
        raise TypeError("transaction deve ser dict")

    payload = transaction.get("result", transaction)
    if not isinstance(payload, dict):
        raise ValueError("payload da transação inválido")

    meta = payload.get("meta")
    tx = payload.get("transaction")
    if not isinstance(meta, dict) or not isinstance(tx, dict):
        return []
    if meta.get("err") is not None:
        return []

    message = tx.get("message")
    if not isinstance(message, dict):
        return []

    keys = _account_keys(message, meta)
    instructions = message.get("instructions", [])
    if not isinstance(instructions, list):
        raise ValueError("message.instructions inválido")

    results = []
    for index, item in enumerate(instructions):
        if not isinstance(item, dict):
            continue

        program_id = item.get("programId")
        if program_id is None:
            program_index = item.get("programIdIndex")
            if (
                isinstance(program_index, bool)
                or not isinstance(program_index, int)
                or not 0 <= program_index < len(keys)
            ):
                continue
            program_id = keys[program_index]

        if program_id != RAYDIUM_CPMM_PROGRAM_ID:
            continue

        raw_data = _decode_base58(item.get("data"))
        decoded_instruction = decode_raydium_cpmm_instruction(
            program_id,
            raw_data,
        )
        if decoded_instruction is None:
            continue

        account_indexes = item.get("accounts")
        if not isinstance(account_indexes, list):
            raise ValueError(
                "instrução CPMM sem lista de índices de contas"
            )

        resolved_accounts = []
        for account_index in account_indexes:
            if (
                isinstance(account_index, bool)
                or not isinstance(account_index, int)
                or not 0 <= account_index < len(keys)
            ):
                raise ValueError(
                    "instrução CPMM contém índice de conta inválido"
                )
            resolved_accounts.append(keys[account_index])

        accounts = decode_raydium_cpmm_accounts(resolved_accounts)
        results.append(
            RaydiumCpmmDecodedSwap(
                instruction_index=index,
                instruction=decoded_instruction,
                accounts=accounts,
            )
        )

    return results
