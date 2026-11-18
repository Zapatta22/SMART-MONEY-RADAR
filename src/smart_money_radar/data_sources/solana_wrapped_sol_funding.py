"""Evidence for top-level native SOL funding of a wrapped-SOL token account.

This decoder is intentionally narrow: it recognizes a SystemProgram::Transfer
followed by SPL Token::SyncNative before a DAMM v2 swap. It does not infer
funding from balances alone.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Sequence

from smart_money_radar.data_sources.solana_token_transfer_decoder import SolanaTokenTransfer

SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
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
    if not isinstance(raw_transaction, dict):
        raise TypeError("raw_transaction deve ser um objeto")
    if not isinstance(token_account, str) or not token_account:
        raise ValueError("token_account inválida")
    if not isinstance(source_wallet, str) or not source_wallet:
        raise ValueError("source_wallet inválida")
    if (
        isinstance(amount_raw, bool)
        or not isinstance(amount_raw, int)
        or not 0 <= amount_raw <= (1 << 64) - 1
    ):
        raise ValueError("amount_raw deve ser inteiro unsigned 64-bit")
    if (
        isinstance(before_instruction_index, bool)
        or not isinstance(before_instruction_index, int)
        or before_instruction_index < 0
    ):
        raise ValueError("before_instruction_index deve ser inteiro não negativo")
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



@dataclass(frozen=True)
class WrappedSolLifecycleEvidence:
    """Evidence for a wrapped-SOL ATA created and closed inside one transaction."""

    token_account: str
    owner_wallet: str
    create_indices: tuple[int, ...]
    system_transfer_indices: tuple[int, ...]
    sync_native_indices: tuple[int, ...]
    token_transfer_indices: tuple[tuple[int, int | None], ...]
    close_account_indices: tuple[int, ...]
    funding_amount_raw: int
    cycle_balances_before_close: tuple[int, ...]
    lamports_delta_raw: int


def decode_wrapped_sol_account_lifecycle(
    raw_transaction: dict,
    *,
    token_account: str,
    owner_wallet: str,
    all_transfers: Sequence[SolanaTokenTransfer],
    claimed_transfers: set[SolanaTokenTransfer],
) -> WrappedSolLifecycleEvidence | None:
    """Reconstruct fully closed ATA lifecycles, including create/fund/swap/close cycles.

    This path is deliberately limited to associated token accounts owned by
    owner_wallet, classic SPL wSOL transfers, top-level SystemProgram funding,
    SyncNative, and TokenProgram CloseAccount returning to owner_wallet.
    """
    if not isinstance(raw_transaction, dict):
        raise TypeError("raw_transaction deve ser um objeto")
    if not isinstance(token_account, str) or not token_account:
        raise ValueError("token_account inválida")
    if not isinstance(owner_wallet, str) or not owner_wallet:
        raise ValueError("owner_wallet inválida")
    if not isinstance(all_transfers, Sequence) or isinstance(all_transfers, (str, bytes)):
        raise TypeError("all_transfers deve ser uma sequência")
    if not isinstance(claimed_transfers, set):
        raise TypeError("claimed_transfers deve ser um set")
    payload = raw_transaction.get("result", raw_transaction)
    if not isinstance(payload, dict):
        raise ValueError("payload RPC inválido")
    transaction = payload.get("transaction")
    meta = payload.get("meta")
    if not isinstance(transaction, dict) or not isinstance(meta, dict):
        raise ValueError("transaction/meta ausentes")
    if meta.get("err", "missing") is not None:
        raise ValueError("transação não comprovadamente executada")
    message = transaction.get("message")
    if not isinstance(message, dict):
        raise ValueError("transaction.message ausente")
    instructions = message.get("instructions")
    if not isinstance(instructions, list):
        raise ValueError("message.instructions inválido")
    keys = _keys(message, meta)

    creates: list[int] = []
    closes: list[int] = []
    syncs: list[int] = []
    funding: list[tuple[int, int]] = []
    for index, instruction in enumerate(instructions):
        if not isinstance(instruction, dict):
            continue
        program = _program(instruction, keys)
        accounts = instruction.get("accounts")
        if not isinstance(accounts, list):
            continue
        resolved = [_resolve(value, keys) for value in accounts]
        encoded = instruction.get("data")
        data = _decode_base58(encoded) if isinstance(encoded, str) and encoded else b""

        if program == ASSOCIATED_TOKEN_PROGRAM_ID and token_account in resolved:
            if (
                len(data) != 1 or data[0] not in (0, 1) or len(resolved) < 6
                or resolved[1] != token_account
                or resolved[2] != owner_wallet
                or resolved[3] != NATIVE_MINT
            ):
                raise ValueError("criação ATA wSOL não corresponde à carteira/conta esperada")
            creates.append(index)
        elif program == SYSTEM_PROGRAM_ID and len(data) == 12:
            if int.from_bytes(data[:4], "little") == 2 and token_account in resolved:
                if (
                    len(resolved) != 2 or resolved[0] != owner_wallet
                    or resolved[1] != token_account
                ):
                    raise ValueError("funding SystemProgram da ATA wSOL tem origem/destino inesperado")
                amount = int.from_bytes(data[4:], "little")
                if amount <= 0:
                    raise ValueError("funding SystemProgram da ATA wSOL deve ser positivo")
                funding.append((index, amount))
        elif program == SPL_TOKEN_PROGRAM_ID:
            if data == b"\x11" and token_account in resolved:
                if len(resolved) != 1:
                    raise ValueError("SyncNative da ATA wSOL possui contas inesperadas")
                syncs.append(index)
            elif data == b"\x09" and resolved and resolved[0] == token_account:
                if (
                    len(resolved) != 3 or resolved[1] != owner_wallet
                    or resolved[2] != owner_wallet
                ):
                    raise ValueError("CloseAccount wSOL não devolve à carteira proprietária")
                closes.append(index)

    if not creates and not closes:
        return None
    if not creates or len(creates) != len(closes):
        raise ValueError("lifecycle wSOL possui criação/fechamento incompleto")
    if any(create >= close for create, close in zip(creates, closes)):
        raise ValueError("ordem de criação/fechamento ATA wSOL inválida")
    if any(closes[i] >= creates[i + 1] for i in range(len(closes) - 1)):
        raise ValueError("lifecycle ATA wSOL sobreposto ou sem recriação explícita")

    related_transfers = [
        transfer for transfer in all_transfers
        if transfer.source_account == token_account
        or transfer.destination_account == token_account
    ]
    if any(transfer not in claimed_transfers for transfer in related_transfers):
        raise ValueError("lifecycle wSOL contém transferência SPL não atribuída")
    if any(
        transfer.mint != NATIVE_MINT
        or transfer.program_id != SPL_TOKEN_PROGRAM_ID
        or transfer.execution_status != "EXECUTED"
        or transfer.cpi_path_valid is not True
        or isinstance(transfer.amount_raw, bool)
        or not isinstance(transfer.amount_raw, int)
        or not 0 < transfer.amount_raw <= (1 << 64) - 1
        for transfer in related_transfers
    ):
        raise ValueError("transferência do lifecycle wSOL inválida ou não suportada")

    all_event_indices = (
        [index for index, _ in funding] + syncs
        + [transfer.instruction_index for transfer in related_transfers]
    )
    for event_index in all_event_indices:
        if not any(create < event_index < close for create, close in zip(creates, closes)):
            raise ValueError("evento wSOL fora de um ciclo ATA criado e fechado")

    cycle_balances: list[int] = []
    total_funding = 0
    used_syncs: list[int] = []
    used_funding_indices: list[int] = []
    used_transfer_indices: list[tuple[int, int | None]] = []
    for create, close in zip(creates, closes):
        cycle_funding = [(index, amount) for index, amount in funding if create < index < close]
        cycle_syncs = [index for index in syncs if create < index < close]
        cycle_transfers = [
            transfer for transfer in related_transfers
            if create < transfer.instruction_index < close
        ]
        cycle_transfers.sort(key=lambda item: (
            item.instruction_index,
            -1 if item.inner_instruction_index is None else item.inner_instruction_index,
        ))
        if not cycle_transfers:
            raise ValueError("ciclo ATA wSOL fechado sem transferência SPL atribuída")
        funded_amount = sum(amount for _, amount in cycle_funding)
        if cycle_funding:
            if len(cycle_syncs) != 1:
                raise ValueError("ciclo wSOL financiado exige exatamente um SyncNative")
            sync_index = cycle_syncs[0]
            if (
                any(index >= sync_index for index, _ in cycle_funding)
                or any(transfer.instruction_index <= sync_index for transfer in cycle_transfers)
            ):
                raise ValueError("ordem funding/SyncNative/transferência SPL inválida")
            used_syncs.append(sync_index)
        elif cycle_syncs:
            raise ValueError("SyncNative encontrado em ciclo sem funding nativo")
        balance = funded_amount
        for transfer in cycle_transfers:
            if transfer.source_account == token_account:
                balance -= transfer.amount_raw
            elif transfer.destination_account == token_account:
                balance += transfer.amount_raw
            else:
                raise ValueError("transferência lifecycle wSOL não toca a conta esperada")
            if balance < 0:
                raise ValueError("saldo wSOL negativo antes do CloseAccount")
        cycle_balances.append(balance)
        total_funding += funded_amount
        used_funding_indices.extend(index for index, _ in cycle_funding)
        used_transfer_indices.extend(
            (transfer.instruction_index, transfer.inner_instruction_index)
            for transfer in cycle_transfers
        )

    if len(used_funding_indices) != len(funding) or len(used_syncs) != len(syncs):
        raise ValueError("há funding/SyncNative wSOL fora dos ciclos reconhecidos")
    if len(used_transfer_indices) != len(related_transfers):
        raise ValueError("há transferências wSOL fora dos ciclos reconhecidos")

    account_index = keys.index(token_account) if token_account in keys else None
    pre = meta.get("preBalances")
    post = meta.get("postBalances")
    if (
        account_index is None or not isinstance(pre, list) or not isinstance(post, list)
        or account_index >= len(pre) or account_index >= len(post)
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (pre[account_index], post[account_index])
        )
    ):
        raise ValueError("lamport snapshots ausentes para ATA wSOL encerrada")
    lamports_delta = post[account_index] - pre[account_index]
    if pre[account_index] != 0 or post[account_index] != 0 or lamports_delta != 0:
        raise ValueError("ATA wSOL lifecycle exige conta ausente antes e depois da transação")

    return WrappedSolLifecycleEvidence(
        token_account=token_account,
        owner_wallet=owner_wallet,
        create_indices=tuple(creates),
        system_transfer_indices=tuple(used_funding_indices),
        sync_native_indices=tuple(used_syncs),
        token_transfer_indices=tuple(used_transfer_indices),
        close_account_indices=tuple(closes),
        funding_amount_raw=total_funding,
        cycle_balances_before_close=tuple(cycle_balances),
        lamports_delta_raw=lamports_delta,
    )
