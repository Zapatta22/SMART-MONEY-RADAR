"""Decodificação estrutural de swaps Raydium CPMM em getTransaction.

Inclui instruções externas e CPIs registradas em meta.innerInstructions.
Não reconstrói quantidades efetivas, não classifica BUY/SELL e não persiste dados.
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
    cpi_path: tuple[int, ...] = ()
    stack_height: int | None = None
    inner_instruction_index: int | None = None


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

    # jsonParsed já inclui endereços resolvidos no accountKeys e omite
    # loadedAddresses. No encoding json, os endereços ALT vêm em meta.
    loaded = meta.get("loadedAddresses", {})
    if loaded is None:
        loaded = {}
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


def _resolve_program_id(item: Mapping[str, Any], keys: list[str]) -> str | None:
    program_id = item.get("programId")
    if isinstance(program_id, str) and program_id:
        return program_id

    program_index = item.get("programIdIndex")
    if (
        isinstance(program_index, bool)
        or not isinstance(program_index, int)
        or not 0 <= program_index < len(keys)
    ):
        return None
    return keys[program_index]


def _resolve_accounts(item: Mapping[str, Any], keys: list[str]) -> list[str]:
    account_indexes = item.get("accounts")
    if not isinstance(account_indexes, list):
        raise ValueError("instrução CPMM sem lista de contas")

    resolved = []
    for account_index in account_indexes:
        if isinstance(account_index, str):
            if not account_index:
                raise ValueError("instrução CPMM contém endereço de conta vazio")
            resolved.append(account_index)
            continue

        if (
            isinstance(account_index, bool)
            or not isinstance(account_index, int)
            or not 0 <= account_index < len(keys)
        ):
            raise ValueError("instrução CPMM contém índice de conta inválido")
        resolved.append(keys[account_index])
    return resolved


def _inner_cpi_paths(
    instructions: list[Any],
) -> list[tuple[tuple[int, ...], int | None]]:
    """Deriva caminhos pai/filho quando stackHeight está disponível.

    Sem stackHeight, usa o índice linear como caminho conservador, sem afirmar
    uma hierarquia que o payload RPC não forneceu.
    """
    stack_paths: dict[int, tuple[int, ...]] = {1: ()}
    sibling_counts: dict[tuple[tuple[int, ...], int], int] = {}
    result = []

    for position, item in enumerate(instructions):
        height = item.get("stackHeight") if isinstance(item, dict) else None
        if (
            isinstance(height, bool)
            or not isinstance(height, int)
            or height < 2
        ):
            # A partir de um item sem stackHeight, não reutiliza uma pilha
            # anterior que pode já não corresponder ao contexto de execução.
            stack_paths = {1: ()}
            result.append(((position,), None))
            continue

        parent_path = stack_paths.get(height - 1)
        if parent_path is None:
            # Sem o pai imediato, não há base suficiente para afirmar a
            # hierarquia deste CPI nem dos descendentes seguintes.
            stack_paths = {1: ()}
            result.append(((position,), height))
            continue

        for known_height in tuple(stack_paths):
            if known_height >= height:
                del stack_paths[known_height]

        counter_key = (parent_path, height)
        sibling_index = sibling_counts.get(counter_key, 0)
        sibling_counts[counter_key] = sibling_index + 1
        path = parent_path + (sibling_index,)
        stack_paths[height] = path
        result.append((path, height))

    return result


def _decode_one(
    item: Mapping[str, Any],
    keys: list[str],
    instruction_index: int,
    cpi_path: tuple[int, ...],
    stack_height: int | None,
    inner_instruction_index: int | None,
) -> RaydiumCpmmDecodedSwap | None:
    program_id = _resolve_program_id(item, keys)
    if program_id != RAYDIUM_CPMM_PROGRAM_ID:
        return None

    encoded_data = item.get("data")
    # Fully parsed instructions may omit raw data. They are not guessed.
    if not isinstance(encoded_data, str) or not encoded_data:
        return None

    decoded = decode_raydium_cpmm_instruction(
        program_id,
        _decode_base58(encoded_data),
    )
    if decoded is None:
        return None

    accounts = decode_raydium_cpmm_accounts(_resolve_accounts(item, keys))
    return RaydiumCpmmDecodedSwap(
        instruction_index=instruction_index,
        instruction=decoded,
        accounts=accounts,
        cpi_path=cpi_path,
        stack_height=stack_height,
        inner_instruction_index=inner_instruction_index,
    )


def decode_raydium_cpmm_swaps(
    transaction: dict[str, Any],
) -> list[RaydiumCpmmDecodedSwap]:
    """Decodifica swaps CPMM externos e CPI; não faz reconstrução econômica."""

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
    outer = message.get("instructions", [])
    if not isinstance(outer, list):
        raise ValueError("message.instructions inválido")

    inner_groups = meta.get("innerInstructions")
    if inner_groups is None:
        inner_groups = []
    if not isinstance(inner_groups, list):
        raise ValueError("meta.innerInstructions inválido")

    groups_by_outer_index: dict[int, list[Any]] = {}
    for group in inner_groups:
        if not isinstance(group, dict):
            raise ValueError("grupo de innerInstructions inválido")
        outer_index = group.get("index")
        nested = group.get("instructions")
        if (
            isinstance(outer_index, bool)
            or not isinstance(outer_index, int)
            or not 0 <= outer_index < len(outer)
            or not isinstance(nested, list)
            or outer_index in groups_by_outer_index
        ):
            raise ValueError("grupo de innerInstructions inconsistente")
        groups_by_outer_index[outer_index] = nested

    results = []
    for outer_index, item in enumerate(outer):
        if isinstance(item, dict):
            decoded_outer = _decode_one(item, keys, outer_index, (), 1, None)
            if decoded_outer is not None:
                results.append(decoded_outer)

        nested = groups_by_outer_index.get(outer_index, [])
        paths = _inner_cpi_paths(nested)
        for inner_index, (inner_item, path_info) in enumerate(zip(nested, paths)):
            if not isinstance(inner_item, dict):
                continue
            cpi_path, stack_height = path_info
            decoded_inner = _decode_one(
                inner_item,
                keys,
                outer_index,
                cpi_path,
                stack_height,
                inner_index,
            )
            if decoded_inner is not None:
                results.append(decoded_inner)

    return results
