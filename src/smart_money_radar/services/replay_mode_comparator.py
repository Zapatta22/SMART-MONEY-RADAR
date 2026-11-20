"""Compare two existing paper modes on identical, strictly gated observations.

No trade execution. Existing paper engine owns costs/slippage; this adapter
does not manufacture quotes from SQLite swap receipts.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from smart_money_radar.domain.paper_replay import (
    PaperConfig, ReplayTick, replay_paper, compare_paper_reports,
)


@dataclass(frozen=True)
class ReplayModeComparison:
    immediate: object
    confirmed: object
    comparison: dict
    observations: int
    rejected_evidence: int
    missing_prices: int
    comparison_status: str


def compare_gated_replay_modes(
    ticks: tuple[ReplayTick, ...], *, config: PaperConfig,
    cutoffs: tuple[datetime, ...],
    eligible: tuple[bool, ...], observed_quotes: tuple[bool, ...],
) -> ReplayModeComparison:
    """Never use future data or invented observed quotes in a paper comparison.

    Inputs represent already validated historical market envelopes. To preserve
    temporal honesty, any missing/ambiguous price excludes that tick from both
    modes. This is an exploratory comparator, not the strict quote+risk replay.
    """
    n = len(ticks)
    if not all(isinstance(x, tuple) for x in (ticks, cutoffs, eligible, observed_quotes)):
        raise TypeError("tuplas obrigatórias")
    if n != len(cutoffs) or n != len(eligible) or n != len(observed_quotes):
        raise ValueError("dimensões de replay divergentes")
    if not isinstance(config, PaperConfig):
        raise TypeError("PaperConfig obrigatório")
    observations = []
    excluded = missing = 0
    previous = None
    for tick, cutoff, allowed, quote_verified in zip(ticks, cutoffs, eligible, observed_quotes):
        if not isinstance(tick, ReplayTick) or not isinstance(cutoff, datetime) or cutoff.utcoffset() is None:
            raise ValueError("observação ou cutoff inválido")
        if type(allowed) is not bool or type(quote_verified) is not bool:
            raise ValueError("flags de replay inválidas")
        point = cutoff.astimezone(timezone.utc)
        if previous is not None and point <= previous:
            raise ValueError("histórico fora de ordem")
        previous = point
        if tick.at > point:
            raise ValueError("cotação indisponível no cutoff")
        if not quote_verified:
            missing += 1
            # No invented price may become a fill/valuation observation.
            continue
        if tick.at != point:
            # No temporal stitching: availability must coincide with tick.at.
            raise ValueError("quote_id e cutoff temporal não correspondem")
        observations.append(
            ReplayTick(
                at=tick.at, price=tick.price, volume=tick.volume,
                signal=tick.signal, entry_allowed=allowed and tick.entry_allowed,
                halted=tick.halted, market_at=tick.market_at,
                bid=tick.bid, ask=tick.ask, bid_size=tick.bid_size,
                ask_size=tick.ask_size, quote_id=tick.quote_id,
            )
        )
        if not allowed and tick.signal == "BUY":
            excluded += 1
    # The original engine receives the *same* immutable observations/config.
    immediate = replay_paper(observations, config=config, mode="immediate")
    confirmed = replay_paper(observations, config=config, mode="confirmed")
    return ReplayModeComparison(
        immediate=immediate, confirmed=confirmed,
        comparison=compare_paper_reports(immediate, confirmed),
        observations=len(observations), rejected_evidence=excluded,
        missing_prices=missing,
        comparison_status="PAPER_MODEL_ONLY_NOT_PROVEN_MARKET",
    )
