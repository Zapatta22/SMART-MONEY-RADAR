"""Offline replay joins archived first-publication receipts to existing market gate.

Nothing here creates executable quotes or bypasses safety. The market archive
does not establish finalized source, so default replay remains UNKNOWN.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smart_money_radar.services.sqlite_market_history import ArchivedMarketSnapshot, archived_volume_at
from smart_money_radar.services.market_opportunity_bridge import MarketOpportunityAudit, classify_with_market_evidence
from smart_money_radar.services.market_safety_liquidity import LiquiditySnapshot, TokenSafetySnapshot
from smart_money_radar.services.opportunity_classifier import OpportunityEvidence
from smart_money_radar.services.wallet_consensus import WalletConsensusReport
from smart_money_radar.storage.event_store import SQLiteEventStore


@dataclass(frozen=True)
class HistoricalOpportunityFrame:
    cutoff: datetime
    archived_market: ArchivedMarketSnapshot
    assessment: MarketOpportunityAudit
    gaps: tuple[str, ...]
    operational_authorized: bool = False


def reconstruct_opportunity_at(
    store: SQLiteEventStore, *, wallets: tuple[str, ...],
    program: str, pool: str, token_mint: str, quote_mint: str,
    cutoff: datetime, window: timedelta, consensus: WalletConsensusReport,
    base: OpportunityEvidence, token_safety: TokenSafetySnapshot | None = None,
    liquidity: LiquiditySnapshot | None = None,
    min_liquidity_quote: Decimal = Decimal("100"),
    max_concentration_fraction: Decimal = Decimal("0.40"),
) -> HistoricalOpportunityFrame:
    """Use one historical cutoff for receipt filtering and classification."""
    if base.as_of != cutoff:
        raise ValueError("base.as_of deve coincidir com cutoff sem deslocamento temporal")
    if (base.pool, base.token_mint, base.chain) != (pool, token_mint, "solana"):
        raise ValueError("contrato de mercado divergente")
    market = archived_volume_at(
        store, wallets=wallets, program=program, pool=pool,
        token_mint=token_mint, quote_mint=quote_mint,
        as_of=cutoff, window=window,
    )
    # The SQLite receipt has no separately verified market quote / RPC finality
    # provenance. Never use its BUY side or amount to promote evidence.
    # Inputs from independent stores require their own temporal validation.
    audit = classify_with_market_evidence(
        base=replace(base, source_status="UNKNOWN", history_coverage="UNKNOWN"),
        consensus=consensus, safety=token_safety, liquidity=liquidity,
        swaps=(), quote_mint=quote_mint,
        min_liquidity_quote=min_liquidity_quote,
        max_concentration_fraction=max_concentration_fraction,
        volume_window=window,
    )
    gaps = set(market.volume.reasons)
    if market.excluded_receipts:
        gaps.add("excluded_historical_receipts")
    if token_safety is None:
        gaps.add("token_safety_missing")
    if liquidity is None:
        gaps.add("liquidity_evidence_missing")
    gaps.update(("quote_not_authenticated", "historical_coverage_unknown"))
    if audit.classification.operational_authorized:
        raise AssertionError("classificador não pode autorizar operações reais")
    return HistoricalOpportunityFrame(
        cutoff=cutoff.astimezone(timezone.utc), archived_market=market,
        assessment=audit, gaps=tuple(sorted(gaps)),
    )
