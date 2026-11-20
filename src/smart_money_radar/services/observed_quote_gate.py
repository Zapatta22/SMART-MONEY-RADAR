"""Point-in-time *claimed observed* quote validation for strict offline replay.

A JSON record and its digest cannot authenticate a quote provider. This guard
refuses economic reports unless separate trust attestation is provided. It
never synthesizes a price, observed timestamp, fee or liquidity.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256

from smart_money_radar.domain.paper_replay import ReplayTick


@dataclass(frozen=True)
class ObservedQuoteEvidence:
    quote_id: str
    source_id: str
    pool: str
    slot: int
    market_at: datetime
    observed_at: datetime
    available_at: datetime
    bid: Decimal
    ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    volume: Decimal
    fee_bps: Decimal | None
    max_slippage_bps: Decimal | None
    raw_payload: bytes
    raw_sha256: str
    observed_claimed: bool
    provider_attested: bool = False
    depth_attested: bool = False


@dataclass(frozen=True)
class QuoteGateResult:
    status: str
    reasons: tuple[str, ...]
    quote_id: str
    source_id: str
    pool: str
    slot: int
    available_at: datetime
    tick: ReplayTick | None
    economics_supported: bool = False


def assess_observed_quote(
    quote: ObservedQuoteEvidence, *, pool: str, cutoff: datetime,
    min_liquidity: Decimal, proposed_notional: Decimal,
) -> QuoteGateResult:
    if not isinstance(quote, ObservedQuoteEvidence):
        raise TypeError("contrato da cotação inválido")
    if not isinstance(cutoff, datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff sem timezone")
    if not isinstance(min_liquidity, Decimal) or not min_liquidity.is_finite() or min_liquidity <= 0:
        raise ValueError("liquidez mínima inválida")
    if not isinstance(proposed_notional, Decimal) or not proposed_notional.is_finite() or proposed_notional <= 0:
        raise ValueError("notional inválido")
    if any(not isinstance(v, str) or not v.strip() for v in (quote.quote_id, quote.source_id, quote.pool, quote.raw_sha256)):
        raise ValueError("identificação de cotação inválida")
    if quote.pool != pool:
        raise ValueError("pool de cotação divergente")
    if type(quote.slot) is not int or quote.slot < 0:
        raise ValueError("slot da cotação inválido")
    for item in (quote.market_at, quote.observed_at, quote.available_at):
        if not isinstance(item, datetime) or item.utcoffset() is None:
            raise ValueError("timestamp de cotação inválido")
    if quote.market_at > quote.observed_at or quote.observed_at > quote.available_at:
        raise ValueError("ordem temporal da cotação inválida")
    if quote.available_at > cutoff:
        raise ValueError("cotação indisponível no cutoff")
    if not isinstance(quote.raw_payload, bytes) or not quote.raw_payload:
        raise ValueError("RAW de cotação ausente")
    if sha256(quote.raw_payload).hexdigest() != quote.raw_sha256:
        raise ValueError("hash da cotação inválido")
    for name in ("bid", "ask", "bid_size", "ask_size", "volume"):
        val = getattr(quote, name)
        if not isinstance(val, Decimal) or not val.is_finite() or val < 0:
            raise ValueError(f"{name} inválido")
    if quote.bid <= 0 or quote.ask <= 0 or quote.bid > quote.ask:
        raise ValueError("bid/ask incoerente")
    if type(quote.observed_claimed) is not bool or type(quote.provider_attested) is not bool or type(quote.depth_attested) is not bool:
        raise ValueError("flags de atestação inválidas")
    for value in (quote.fee_bps, quote.max_slippage_bps):
        if value is not None and (not isinstance(value, Decimal) or not value.is_finite()
                                  or not Decimal(0) <= value < Decimal(10000)):
            raise ValueError("taxa/slippage inválidos")
    reasons = set()
    if not quote.observed_claimed:
        reasons.add("indicative_or_model_quote")
    if not quote.provider_attested:
        reasons.add("provider_not_attested")
    if not quote.depth_attested:
        reasons.add("depth_not_attested")
    if quote.fee_bps is None:
        reasons.add("fee_unknown")
    if quote.max_slippage_bps is None:
        reasons.add("slippage_unknown")
    if quote.ask_size * quote.ask < proposed_notional or quote.bid_size * quote.bid < min_liquidity:
        reasons.add("insufficient_market_depth")
    if quote.volume <= 0:
        reasons.add("volume_unknown")
    if reasons:
        return QuoteGateResult(
            status="UNKNOWN" if "insufficient_market_depth" not in reasons else "REJECTED",
            reasons=tuple(sorted(reasons)), quote_id=quote.quote_id,
            source_id=quote.source_id, pool=quote.pool, slot=quote.slot,
            available_at=quote.available_at.astimezone(timezone.utc),
            tick=None,
        )
    tick = ReplayTick(
        at=quote.available_at, market_at=quote.market_at,
        price=(quote.bid + quote.ask) / 2, volume=quote.volume,
        bid=quote.bid, ask=quote.ask, bid_size=quote.bid_size,
        ask_size=quote.ask_size, quote_id=quote.quote_id,
        signal="NONE", entry_allowed=False,
    )
    return QuoteGateResult(
        status="CANDIDATE_PAPER_ONLY", reasons=(),
        quote_id=quote.quote_id, source_id=quote.source_id,
        pool=quote.pool, slot=quote.slot,
        available_at=quote.available_at.astimezone(timezone.utc),
        tick=tick, economics_supported=False,
    )
