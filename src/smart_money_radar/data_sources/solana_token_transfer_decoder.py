"""Decodificação de transferências SPL Token e Token-2022 em transações Solana.

A saída é evidência de instrução, não uma observação econômica de swap.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


SPL_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
TOKEN_PROGRAM_IDS = {SPL_TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID}
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


@dataclass(frozen=True)
class SolanaTokenTransfer:
    program_id: str
    program_name: str
    instruction_type: str
    instruction_index: int
    inner_instruction_index: int | None
    stack_height: int | None
    cpi_path: tuple[int, ...]
    source_account: str
    destination_account: str
    authority: str | None
    mint: str | None
    amount_raw: int
    decimals: int | None
    execution_status: str
    source_format: str
    cpi_path_valid: bool = True
    fee_amount_raw: int | None = None


def _decode_base58(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("data base58 ausente ou inválida")
    number = 0
    try:
        for char in value:
            number = number * 58 + ALPHABET.index(char)
    except ValueError as exc:
        raise ValueError("data contém caractere base58 inválido") from exc
    body = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return b"\x00" * (len(value) - len(value.lstrip("1"))) + body


def _account_keys(message: Mapping[str, Any], meta: Mapping[str, Any] | None) -> list[str]:
    raw = message.get("accountKeys")
    if not isinstance(raw, list):
        raise ValueError("message.accountKeys ausente ou inválido")
    parsed_keys = any(isinstance(item, dict) for item in raw)
    keys = []
    for item in raw:
        key = item.get("pubkey") if isinstance(item, dict) else item
        if not isinstance(key, str) or not key:
            raise ValueError("accountKeys contém chave inválida")
        keys.append(key)

    # jsonParsed já expõe as chaves resolvidas; encoding json usa loadedAddresses.
    if not parsed_keys and meta is not None:
        loaded = meta.get("loadedAddresses") or {}
        if not isinstance(loaded, dict):
            raise ValueError("meta.loadedAddresses inválido")
        for field in ("writable", "readonly"):
            values = loaded.get(field, [])
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise ValueError(f"loadedAddresses.{field} inválido")
            keys.extend(values)
    return keys


def _resolve_key(value: Any, keys: list[str], field: str) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < len(keys):
        raise ValueError(f"{field} inválido")
    return keys[value]


def _resolve_program_id(item: Mapping[str, Any], keys: list[str]) -> str | None:
    program_id = item.get("programId")
    if isinstance(program_id, str) and program_id:
        return program_id
    index = item.get("programIdIndex")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(keys):
        return None
    return keys[index]


def _cpi_paths(instructions: list[Any]) -> list[tuple[tuple[int, ...], int | None]]:
    """Deriva caminhos somente quando a hierarquia imediata é demonstrável."""
    stack_paths: dict[int, tuple[int, ...]] = {1: ()}
    sibling_counts: dict[tuple[tuple[int, ...], int], int] = {}
    result = []
    for position, item in enumerate(instructions):
        height = item.get("stackHeight") if isinstance(item, dict) else None
        if isinstance(height, bool) or not isinstance(height, int) or height < 2:
            stack_paths = {1: ()}
            result.append(((position,), None))
            continue
        parent = stack_paths.get(height - 1)
        if parent is None:
            stack_paths = {1: ()}
            result.append(((position,), height))
            continue
        for known in tuple(stack_paths):
            if known >= height:
                del stack_paths[known]
        counter_key = (parent, height)
        sibling = sibling_counts.get(counter_key, 0)
        sibling_counts[counter_key] = sibling + 1
        path = parent + (sibling,)
        stack_paths[height] = path
        result.append((path, height))
    return result


def _strict_cpi_path_validity(instructions: list[Any]) -> list[bool]:
    """Marca inválida toda hierarquia após stackHeight ausente/inconsistente."""
    stack_paths: dict[int, tuple[int, ...]] = {1: ()}
    valid = True
    results: list[bool] = []
    for item in instructions:
        height = item.get("stackHeight") if isinstance(item, dict) else None
        if (
            not valid
            or isinstance(height, bool)
            or not isinstance(height, int)
            or height < 2
        ):
            valid = False
            stack_paths.clear()
            results.append(False)
            continue
        parent = stack_paths.get(height - 1)
        if parent is None:
            valid = False
            stack_paths.clear()
            results.append(False)
            continue
        for known in tuple(stack_paths):
            if known >= height:
                del stack_paths[known]
        stack_paths[height] = parent + (0,)
        results.append(True)
    return results


def _raw_transfer(
    item: Mapping[str, Any], keys: list[str], program_id: str
) -> tuple[str, str, str | None, str | None, int, int | None, str, int | None] | None:
    encoded = item.get("data")
    if not isinstance(encoded, str) or not encoded:
        return None
    data = _decode_base58(encoded)
    if not data:
        return None
    opcode = data[0]
    if opcode not in (3, 12, 26):
        return None
    if opcode == 26:
        # TokenInstruction::TransferFeeExtension + TransferCheckedWithFee.
        # Other transfer-fee extension instructions are outside this decoder.
        if program_id != TOKEN_2022_PROGRAM_ID or len(data) < 2 or data[1] != 1:
            return None
        if len(data) != 19:
            raise ValueError("TransferCheckedWithFee exige 19 bytes")
        accounts = item.get("accounts")
        if not isinstance(accounts, list):
            raise ValueError("instrução token sem lista de contas")
        if len(accounts) < 4:
            raise ValueError("TransferCheckedWithFee exige pelo menos 4 contas")
        resolved = [_resolve_key(value, keys, "índice de conta") for value in accounts]
        amount = int.from_bytes(data[2:10], "little")
        decimals = data[10]
        fee_amount = int.from_bytes(data[11:19], "little")
        return (
            resolved[0], resolved[2], resolved[3], resolved[1],
            amount, decimals, "TRANSFER_CHECKED_WITH_FEE", fee_amount,
        )

    accounts = item.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("instrução token sem lista de contas")
    resolved = [_resolve_key(value, keys, "índice de conta") for value in accounts]
    if opcode == 3:
        if len(data) != 9 or len(resolved) < 3:
            raise ValueError("Transfer exige 9 bytes e pelo menos 3 contas")
        amount = int.from_bytes(data[1:9], "little")
        return resolved[0], resolved[1], resolved[2], None, amount, None, "TRANSFER", None
    if len(data) != 10 or len(resolved) < 4:
        raise ValueError("TransferChecked exige 10 bytes e pelo menos 4 contas")
    amount = int.from_bytes(data[1:9], "little")
    return (
        resolved[0], resolved[2], resolved[3], resolved[1],
        amount, data[9], "TRANSFER_CHECKED", None,
    )

def _parsed_transfer(
    parsed: Mapping[str, Any],
) -> tuple[str, str, str | None, str | None, int, int | None, str, int | None] | None:
    kind = parsed.get("type")
    info = parsed.get("info")
    if not isinstance(kind, str) or not isinstance(info, dict):
        return None
    normalized = kind.lower().replace("_", "")
    if normalized not in {"transfer", "transferchecked", "transfercheckedwithfee"}:
        return None

    source = info.get("source")
    destination = info.get("destination")
    authority = info.get("authority")
    mint = info.get("mint")
    token_amount = info.get("tokenAmount")
    fee_amount = None
    if normalized in {"transferchecked", "transfercheckedwithfee"}:
        if not isinstance(token_amount, dict):
            return None
        raw_amount = token_amount.get("amount")
        decimals = token_amount.get("decimals")
        if normalized == "transfercheckedwithfee":
            raw_fee = info.get("feeAmount", info.get("fee"))
            if isinstance(raw_fee, bool) or not isinstance(raw_fee, (str, int)):
                return None
            try:
                fee_amount = int(raw_fee)
            except (TypeError, ValueError):
                return None
            if fee_amount < 0:
                return None
    else:
        raw_amount = info.get("amount")
        decimals = None
    if not isinstance(source, str) or not source or not isinstance(destination, str) or not destination:
        return None
    if isinstance(raw_amount, bool) or not isinstance(raw_amount, (str, int)):
        return None
    try:
        amount = int(raw_amount)
    except (TypeError, ValueError):
        return None
    if amount < 0:
        return None
    if decimals is not None and (
        isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 255
    ):
        return None
    if authority is not None and not isinstance(authority, str):
        return None
    if mint is not None and not isinstance(mint, str):
        return None
    if normalized == "transfercheckedwithfee":
        instruction_type = "TRANSFER_CHECKED_WITH_FEE"
    else:
        instruction_type = "TRANSFER_CHECKED" if normalized == "transferchecked" else "TRANSFER"
    return source, destination, authority, mint, amount, decimals, instruction_type, fee_amount

def _decode_one(
    item: Mapping[str, Any],
    keys: list[str],
    outer_index: int,
    inner_index: int | None,
    stack_height: int | None,
    cpi_path: tuple[int, ...],
    execution_status: str,
    cpi_path_valid: bool = True,
) -> SolanaTokenTransfer | None:
    program_id = _resolve_program_id(item, keys)
    if program_id not in TOKEN_PROGRAM_IDS:
        return None

    parsed = item.get("parsed")
    values = _parsed_transfer(parsed) if isinstance(parsed, dict) else None
    source_format = "jsonParsed"
    if values is None:
        values = _raw_transfer(item, keys, program_id)
        source_format = "compiled"
    if values is None:
        return None
    if values[6] == "TRANSFER_CHECKED_WITH_FEE" and program_id != TOKEN_2022_PROGRAM_ID:
        return None

    source, destination, authority, mint, amount, decimals, instruction_type, fee_amount = values
    return SolanaTokenTransfer(
        program_id=program_id,
        program_name="SPL Token" if program_id == SPL_TOKEN_PROGRAM_ID else "Token-2022",
        instruction_type=instruction_type,
        instruction_index=outer_index,
        inner_instruction_index=inner_index,
        stack_height=stack_height,
        cpi_path=cpi_path,
        source_account=source,
        destination_account=destination,
        authority=authority,
        mint=mint,
        amount_raw=amount,
        decimals=decimals,
        execution_status=execution_status,
        source_format=source_format,
        cpi_path_valid=cpi_path_valid,
        fee_amount_raw=fee_amount,
    )


def decode_solana_token_transfers(
    raw_transaction: dict[str, Any],
) -> list[SolanaTokenTransfer]:
    """Decodifica Transfer, TransferChecked e TransferCheckedWithFee.

    Outras instruções de extensão Token-2022 permanecem fora do escopo.
    """
    if not isinstance(raw_transaction, dict):
        raise TypeError("transação precisa ser um objeto")
    payload = raw_transaction.get("result", raw_transaction)
    if not isinstance(payload, dict):
        raise ValueError("payload RPC inválido")
    tx = payload.get("transaction")
    if not isinstance(tx, dict):
        return []
    message = tx.get("message")
    if not isinstance(message, dict):
        return []
    meta = payload.get("meta")
    if meta is not None and not isinstance(meta, dict):
        raise ValueError("meta inválido")
    keys = _account_keys(message, meta)
    status = "UNKNOWN" if meta is None or "err" not in meta else (
        "FAILED" if meta.get("err") is not None else "EXECUTED"
    )

    outer = message.get("instructions", [])
    if not isinstance(outer, list):
        raise ValueError("message.instructions inválido")
    results = []
    for outer_index, item in enumerate(outer):
        if not isinstance(item, dict):
            continue
        decoded = _decode_one(item, keys, outer_index, None, 1, (), status)
        if decoded is not None:
            results.append(decoded)

    groups = meta.get("innerInstructions") if isinstance(meta, dict) else None
    if groups is None:
        groups = []
    if not isinstance(groups, list):
        raise ValueError("meta.innerInstructions inválido")
    seen = set()
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("grupo innerInstructions inválido")
        outer_index = group.get("index")
        nested = group.get("instructions")
        if (
            isinstance(outer_index, bool)
            or not isinstance(outer_index, int)
            or not 0 <= outer_index < len(outer)
            or not isinstance(nested, list)
            or outer_index in seen
        ):
            raise ValueError("grupo innerInstructions inconsistente")
        seen.add(outer_index)
        paths = _cpi_paths(nested)
        path_validity = _strict_cpi_path_validity(nested)
        for inner_index, (item, path_info, path_valid) in enumerate(
            zip(nested, paths, path_validity)
        ):
            if not isinstance(item, dict):
                continue
            path, height = path_info
            decoded = _decode_one(
                item, keys, outer_index, inner_index, height, path, status,
                cpi_path_valid=path_valid,
            )
            if decoded is not None:
                results.append(decoded)
    return results
