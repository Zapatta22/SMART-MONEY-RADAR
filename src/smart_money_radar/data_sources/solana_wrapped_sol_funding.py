"""Evidence for top-level native SOL funding of a wrapped-SOL token account.

This decoder is intentionally narrow: it recognizes a SystemProgram::Transfer
followed by SPL Token::SyncNative before a DAMM v2 swap. It does not infer
funding from balances alone.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"
SPL_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
NATIVE_MINT = "So11111111111111111111111111111111111111112"
_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


@dataclass(frozen=True)
class WrappedSolFundingEvidence:
    token_account: str
    source_wallet: str
    amount_raw: int
    system_transfer_index: int
    sync_native_index: int
    lamports_delta_raw: int
    system_transfer_indices: tuple[int, ...] = ()


def _decode_base58(value: Any) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("instruction data Base58 ausente")
    number = 0
    try:
        for char in value:
            number = number * 58 + _BASE58.index(char)
    except ValueError as exc:
        raise ValueError("instruction data Base58 inválida") from exc
    body = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return b"\x00" * (len(value) - len(value.lstrip("1"))) + body


def _keys(message: dict, meta: dict) -> list[str]:
    raw = message.get("accountKeys")
    if not isinstance(raw, list):
        raise ValueError("message.accountKeys inválido")
    parsed = any(isinstance(item, dict) for item in raw)
    if parsed and not all(isinstance(item, dict) for item in raw):
        raise ValueError("message.accountKeys mistura formatos")
    result = []
    for item in raw:
        key = item.get("pubkey") if isinstance(item, dict) else item
        if not isinstance(key, str) or not key:
            raise ValueError("account key inválida")
        result.append(key)
    if not parsed:
        loaded = meta.get("loadedAddresses") or {}
        if not isinstance(loaded, dict):
            raise ValueError("loadedAddresses inválido")
        for field in ("writable", "readonly"):
            values = loaded.get(field, [])
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise ValueError(f"loadedAddresses.{field} inválido")
            result.extend(values)
    return result


def _resolve(value: Any, keys: list[str]) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < len(keys):
        raise ValueError("índice de conta de instrução inválido")
    return keys[value]


def _program(instruction: dict, keys: list[str]) -> str | None:
    direct = instruction.get("programId")
    if isinstance(direct, str) and direct:
        return direct
    index = instruction.get("programIdIndex")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(keys):
        return None
    return keys[index]


def decode_wrapped_sol_funding(
    raw_transaction: dict,
    *,
    token_account: str,
    source_wallet: str,
    amount_raw: int,
    before_instruction_index: int,
) -> WrappedSolFundingEvidence | None:
    """Find and validate one exact top-level SOL transfer + SyncNative pair."""
    payload = raw_transaction.get("result", raw_transaction)
    if not isinstance(payload, dict):
        raise ValueError("payload RPC inválido")
    transaction = payload.get("transaction")
    meta = payload.get("meta")
    if not isinstance(transaction, dict) or not isinstance(meta, dict):
        raise ValueError("transaction/meta ausentes")
    message = transaction.get("message")
    if not isinstance(message, dict):
        raise ValueError("transaction.message ausente")
    instructions = message.get("instructions")
    if not isinstance(instructions, list):
        raise ValueError("message.instructions inválido")
    keys = _keys(message, meta)

    transfers = []
    syncs = []
    for index, instruction in enumerate(instructions):
        if not isinstance(instruction, dict):
            continue
        program = _program(instruction, keys)
        accounts = instruction.get("accounts")
        if not isinstance(accounts, list):
            continue
        resolved = [_resolve(value, keys) for value in accounts]
        data = _decode_base58(instruction.get("data")) if instruction.get("data") else b""
        if program == SYSTEM_PROGRAM_ID and len(data) == 12:
            opcode = int.from_bytes(data[:4], "little")
            if opcode == 2 and len(resolved) == 2:
                amount = int.from_bytes(data[4:], "little")
                if token_account in resolved:
                    transfers.append((index, resolved[0], resolved[1], amount))
        if program == SPL_TOKEN_PROGRAM_ID and data == b"\x11":
            if len(resolved) == 1 and resolved[0] == token_account:
                syncs.append(index)

    related = [
        item for item in transfers
        if item[1] == source_wallet and item[2] == token_account
    ]
    if not related:
        if transfers:
            raise ValueError("há SystemProgram transfer envolvendo a conta wSOL sem origem/destino esperado")
        return None
    if len(related) != len(transfers):
        raise ValueError("funding wSOL possui transferências SystemProgram ambíguas")
    transfer_indices = tuple(item[0] for item in related)
    funded_amount = sum(item[3] for item in related)
    if funded_amount != amount_raw:
        raise ValueError("funding SOL agregado diverge do valor bruto total das transferências wSOL")
    if len(syncs) != 1:
        raise ValueError("SyncNative não foi identificado univocamente para a conta wSOL")
    sync_index = syncs[0]
    if not all(index < sync_index for index in transfer_indices) or not sync_index < before_instruction_index:
        raise ValueError("ordem SystemProgram transfer/SyncNative/swap inválida")
    transfer_index = transfer_indices[0]

    account_index = keys.index(token_account)
    pre = meta.get("preBalances")
    post = meta.get("postBalances")
    if (
        not isinstance(pre, list) or not isinstance(post, list)
        or account_index >= len(pre) or account_index >= len(post)
        or any(isinstance(value, bool) or not isinstance(value, int) or value < 0
               for value in (pre[account_index], post[account_index]))
    ):
        raise ValueError("lamport snapshots ausentes para a conta wSOL")
    lamports_delta = post[account_index] - pre[account_index]
    if lamports_delta != 0:
        raise ValueError("delta de lamports da conta wSOL não fecha em zero")
    return WrappedSolFundingEvidence(
        token_account=token_account,
        source_wallet=source_wallet,
        amount_raw=funded_amount,
        system_transfer_index=transfer_index,
        sync_native_index=sync_index,
        lamports_delta_raw=lamports_delta,
        system_transfer_indices=transfer_indices,
    )
