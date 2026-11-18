"""Extração conservadora de movimentações a partir de getTransaction."""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from smart_money_radar.domain.models import ActivityEvent

PARSER_VERSION = "1"
SOL_MINT = "SOL"
LAMPORTS_PER_SOL = Decimal("1000000000")


def parse_transaction(
    transaction: dict[str, Any],
    wallet_address: str,
    signature: str,
) -> list[ActivityEvent]:
    """Retorna deltas de tokens e transferências SOL explicitamente decodificadas.

    A função não tenta inferir valores de mercado nem classificar operações.
    Movimentações sem mint, owner ou instrução decodificável são ignoradas.
    """
    meta = transaction.get("meta")
    if not isinstance(meta, dict) or meta.get("err") is not None:
        return []

    occurred_at = _timestamp(transaction.get("blockTime"))
    events: list[ActivityEvent] = []
    pre_balances = meta.get("preTokenBalances")
    post_balances = meta.get("postTokenBalances")
    # Não interpretar um lado ausente como saldo zero: isso criaria deltas
    # artificiais em respostas RPC incompletas ou malformadas.
    if isinstance(pre_balances, list) and isinstance(post_balances, list):
        before = _token_balances(pre_balances, wallet_address)
        after = _token_balances(post_balances, wallet_address)
    else:
        before = {}
        after = {}

    for mint in sorted(before.keys() | after.keys()):
        before_entry = before.get(mint)
        after_entry = after.get(mint)
        # None is an explicit invalid/conflicting scale; a missing key alone
        # represents a token account created or closed during the transaction.
        if (mint in before and before_entry is None) or (mint in after and after_entry is None):
            continue
        if (
            before_entry is not None
            and after_entry is not None
            and before_entry[1] != after_entry[1]
        ):
            continue
        before_amount = before_entry[0] if before_entry is not None else Decimal("0")
        after_amount = after_entry[0] if after_entry is not None else Decimal("0")
        delta = after_amount - before_amount
        if delta == 0:
            continue
        events.append(
            ActivityEvent(
                wallet_address=wallet_address,
                signature=signature,
                occurred_at=occurred_at,
                token_mint=mint,
                direction="in" if delta > 0 else "out",
                amount=abs(delta),
            )
        )

    sol_transfers = _sol_transfers(transaction, wallet_address)
    for direction, amount in sorted(sol_transfers.items()):
        if amount > 0:
            events.append(
                ActivityEvent(
                    wallet_address=wallet_address,
                    signature=signature,
                    occurred_at=occurred_at,
                    token_mint=SOL_MINT,
                    direction=direction,  # type: ignore[arg-type]
                    amount=amount,
                )
            )
    return events


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _token_balances(
    value: Any, wallet_address: str
) -> dict[str, tuple[Decimal, int] | None]:
    raw_balances: dict[str, Decimal] = defaultdict(Decimal)
    decimals_by_mint: dict[str, set[int]] = defaultdict(set)
    invalid_mints: set[str] = set()
    account_index_to_identity: dict[int, tuple[Any, Any] | None] = {}
    if not isinstance(value, list):
        return {}
    for entry in value:
        if not isinstance(entry, dict):
            continue
        owner = entry.get("owner")
        mint = entry.get("mint")
        account_index = entry.get("accountIndex")
        if account_index is not None:
            if (
                isinstance(account_index, bool)
                or not isinstance(account_index, int)
                or account_index < 0
            ):
                if owner == wallet_address and isinstance(mint, str) and mint:
                    invalid_mints.add(mint)
                continue
            identity = (owner, mint)
            if account_index in account_index_to_identity:
                previous_identity = account_index_to_identity[account_index]
                for candidate in (previous_identity, identity):
                    if (
                        candidate is not None
                        and candidate[0] == wallet_address
                        and isinstance(candidate[1], str)
                        and candidate[1]
                    ):
                        invalid_mints.add(candidate[1])
                account_index_to_identity[account_index] = None
            else:
                account_index_to_identity[account_index] = identity
        if owner != wallet_address:
            continue
        if not isinstance(mint, str) or not mint:
            continue
        amount_info = entry.get("uiTokenAmount")
        if not isinstance(amount_info, dict):
            invalid_mints.add(mint)
            continue
        try:
            raw_amount_value = amount_info["amount"]
            if (
                not isinstance(raw_amount_value, str)
                or not raw_amount_value.isascii()
                or not raw_amount_value.isdigit()
            ):
                invalid_mints.add(mint)
                continue
            raw_amount = Decimal(raw_amount_value)
            decimals_value = amount_info["decimals"]
            # JSON-RPC representa decimals SPL como inteiro. Não coagir strings,
            # floats ou booleanos: 6.9 truncado para 6 alteraria o saldo.
            if isinstance(decimals_value, bool) or not isinstance(decimals_value, int):
                invalid_mints.add(mint)
                continue
            decimals = decimals_value
            # O campo decimals do SPL Token é um u8 (0..255).
            if not 0 <= decimals <= 255 or not raw_amount.is_finite() or raw_amount < 0:
                invalid_mints.add(mint)
                continue
            raw_balances[mint] += raw_amount
            decimals_by_mint[mint].add(decimals)
        except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
            invalid_mints.add(mint)
            continue
    # Uma mint deve usar a mesma escala em todas as token accounts.
    result: dict[str, tuple[Decimal, int] | None] = {}
    for mint in invalid_mints:
        result[mint] = None
    for mint, scales in decimals_by_mint.items():
        if mint in invalid_mints or len(scales) != 1:
            result[mint] = None
            continue
        decimals = next(iter(scales))
        result[mint] = (
            raw_balances[mint] / (Decimal(10) ** decimals),
            decimals,
        )
    return result


def _sol_transfers(
    transaction: dict[str, Any], wallet_address: str
) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    message = transaction.get("transaction")
    if not isinstance(message, dict):
        return {}
    message = message.get("message")
    if not isinstance(message, dict):
        return {}

    instructions = message.get("instructions")
    all_instructions = list(instructions) if isinstance(instructions, list) else []
    meta = transaction.get("meta")
    inner = meta.get("innerInstructions") if isinstance(meta, dict) else None
    if isinstance(inner, list):
        for group in inner:
            if isinstance(group, dict) and isinstance(group.get("instructions"), list):
                all_instructions.extend(group["instructions"])

    for instruction in all_instructions:
        if not isinstance(instruction, dict) or instruction.get("program") != "system":
            continue
        parsed = instruction.get("parsed")
        if not isinstance(parsed, dict) or parsed.get("type") not in {
            "transfer",
            "transferWithSeed",
        }:
            continue
        info = parsed.get("info")
        if not isinstance(info, dict):
            continue
        source = info.get("source")
        destination = info.get("destination")
        lamports = info.get("lamports")
        if isinstance(lamports, bool) or not isinstance(lamports, int):
            continue
        try:
            amount = Decimal(lamports) / LAMPORTS_PER_SOL
        except (InvalidOperation, TypeError, ValueError):
            continue
        if not amount.is_finite() or amount <= 0:
            continue
        if source == wallet_address:
            totals["out"] += amount
        if destination == wallet_address:
            totals["in"] += amount
    return dict(totals)