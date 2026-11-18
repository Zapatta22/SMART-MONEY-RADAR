"""Adaptadores de normalização entre o parser atual e os contratos de domínio."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from smart_money_radar.data_sources.transaction_parser import PARSER_VERSION, SOL_MINT, parse_transaction
from smart_money_radar.domain.models import (
    ActivityEvent,
    ObservedTransaction,
    TokenBalanceDelta,
)


@dataclass(frozen=True)
class NormalizedObservation:
    """Resultado normalizado sem remover compatibilidade com ActivityEvent."""

    transaction: ObservedTransaction
    token_deltas: tuple[TokenBalanceDelta, ...]
    activity_events: tuple[ActivityEvent, ...]


def normalize_transaction(
    raw_transaction: dict[str, Any],
    wallet_address: str,
    signature: str,
    *,
    chain: str = "solana",
    observed_at: datetime | None = None,
) -> NormalizedObservation:
    """Converte uma resposta RPC em envelope e deltas tipados.

    A normalização usa o parser conservador existente. `ActivityEvent` permanece
    disponível para o pipeline legado; `TokenBalanceDelta` contém apenas mints
    SPL, pois SOL nativo é uma transferência de lamports e não um mint SPL.
    """
    if not isinstance(raw_transaction, dict):
        raise TypeError("A transação RPC deve ser um objeto JSON.")
    if not wallet_address.strip() or not signature.strip() or not chain.strip():
        raise ValueError("Chain, carteira e assinatura são obrigatórias.")

    events = tuple(parse_transaction(raw_transaction, wallet_address, signature))
    meta = raw_transaction.get("meta")
    failed = isinstance(meta, dict) and meta.get("err") is not None
    status = "failed_on_chain" if failed else ("parsed" if events else "no_events")
    block_time = raw_transaction.get("blockTime")
    occurred_at = None
    if isinstance(block_time, int) and not isinstance(block_time, bool):
        try:
            occurred_at = datetime.fromtimestamp(block_time, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            occurred_at = None

    envelope = ObservedTransaction(
        chain=chain,
        wallet_address=wallet_address,
        signature=signature,
        observed_at=observed_at or datetime.now(timezone.utc),
        raw_transaction=raw_transaction,
        parser_version=PARSER_VERSION,
        parse_status=status,
        slot=(raw_transaction.get("slot") if isinstance(raw_transaction.get("slot"), int)
              and not isinstance(raw_transaction.get("slot"), bool)
              and raw_transaction.get("slot") >= 0 else None),
        occurred_at=occurred_at,
    )
    decimals_by_mint = _decimals_by_mint(raw_transaction, wallet_address)
    deltas = tuple(
        TokenBalanceDelta(
            chain=chain,
            wallet_address=event.wallet_address,
            signature=event.signature,
            token_mint=event.token_mint,
            direction=event.direction,
            amount=event.amount,
            decimals=decimals_by_mint.get(event.token_mint),
        )
        for event in events
        if event.token_mint != SOL_MINT
    )
    return NormalizedObservation(envelope, deltas, events)


def _decimals_by_mint(raw_transaction: dict[str, Any], wallet_address: str) -> dict[str, int]:
    """Retorna escala SPL apenas quando os lados observados concordam."""
    meta = raw_transaction.get("meta")
    if not isinstance(meta, dict):
        return {}
    values: dict[str, set[int]] = {}
    for field in ("preTokenBalances", "postTokenBalances"):
        entries = meta.get(field)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("owner") != wallet_address:
                continue
            mint = entry.get("mint")
            amount = entry.get("uiTokenAmount")
            decimals = amount.get("decimals") if isinstance(amount, dict) else None
            if (isinstance(mint, str) and mint and isinstance(decimals, int)
                    and not isinstance(decimals, bool) and 0 <= decimals <= 255):
                values.setdefault(mint, set()).add(decimals)
    return {mint: next(iter(scales)) for mint, scales in values.items() if len(scales) == 1}
