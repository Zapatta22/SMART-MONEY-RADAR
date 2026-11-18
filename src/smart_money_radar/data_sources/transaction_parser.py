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
        before_amount, before_decimals = before.get(mint, (Decimal("0"), None))
        after_amount, after_decimals = after.get(mint, (Decimal("0"), None))
        if (
            before_decimals is not None
            and after_decimals is not None
            and before_decimals != after_decimals
        ):
            # A mint has one immutable decimal scale; reject conflicting RPC metadata.
            continue
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
) -> dict[str, tuple[Decimal, int]]:
    raw_balances: dict[str, Decimal] = defaultdict(Decimal)
    decimals_by_mint: dict[str, set[int]] = defaultdict(set)
    if not isinstance(value, list):
        return {}
    for entry in value:
        if not isinstance(entry, dict) or entry.get("owner") != wallet_address:
            continue
        mint = entry.get("mint")
        amount_info = entry.get("uiTokenAmount")
        if not isinstance(mint, str) or not mint or not isinstance(amount_info, dict):
            continue
        try:
            raw_amount = Decimal(str(amount_info["amount"]))
            decimals_value = amount_info["decimals"]
            # JSON-RPC representa decimals SPL como inteiro. Não coagir strings,
            # floats ou booleanos: 6.9 truncado para 6 alteraria o saldo.
            if isinstance(decimals_value, bool) or not isinstance(decimals_value, int):
                continue
            decimals = decimals_value
            # O campo decimals do SPL Token é um u8 (0..255).
            if not 0 <= decimals <= 255 or not raw_amount.is_finite() or raw_amount < 0:
                continue
            raw_balances[mint] += raw_amount
            decimals_by_mint[mint].add(decimals)
        except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
            continue
    # Uma mint deve usar a mesma escala em todas as token accounts.
    return {
        mint: (
            raw_balances[mint] / (Decimal(10) ** next(iter(scales))),
            next(iter(scales)),
        )
        for mint, scales in decimals_by_mint.items()
        if len(scales) == 1
    }


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