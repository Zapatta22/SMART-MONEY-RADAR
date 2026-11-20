"""Fail-closed bridge from audited market inputs into opportunity classifications.

This does not attest RPC provenance or infer safety from an absent alert.
The original classifier stays the sole decision/ranking implementation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal

from smart_money_radar.services.market_safety_liquidity import (
    LiquiditySnapshot, MarketSafetyFinding, TokenSafetySnapshot,
    assess_token_liquidity,
)
from smart_money_radar.services.market_volume_audit import (
    SwapVolumeEvidence, VolumeAuditResult, audit_swap_volume,
)
from smart_money_radar.services.opportunity_classifier import (
    OpportunityClassification, OpportunityEvidence, classify_opportunity,
)
from smart_money_radar.services.wallet_consensus import WalletConsensusReport


@dataclass(frozen=True)
class MarketOpportunityAudit:
    classification: OpportunityClassification
    safety: MarketSafetyFinding
    volume: VolumeAuditResult
    evidence_ids: tuple[str, ...]


def classify_with_market_evidence(
    *, base: OpportunityEvidence, consensus: WalletConsensusReport,
    safety: TokenSafetySnapshot | None, liquidity: LiquiditySnapshot | None,
    swaps: tuple[SwapVolumeEvidence, ...], quote_mint: str,
    min_liquidity_quote: Decimal, max_concentration_fraction: Decimal,
    volume_window: timedelta = timedelta(minutes=5),
    max_evidence_age: timedelta = timedelta(minutes=5),
) -> MarketOpportunityAudit:
    """Classify only from observations available at or before base.as_of.

    For safety we deliberately do NOT inherit caller-provided VERIFIED flags.
    Provenance is only as strong as the underlying evidence and its trust chain.
    """
    market = assess_token_liquidity(
        token=safety, liquidity=liquidity, token_mint=base.token_mint,
        pool=base.pool, as_of=base.as_of,
        min_liquidity_quote=min_liquidity_quote,
        max_concentration_fraction=max_concentration_fraction,
        max_age=max_evidence_age,
    )
    volume = audit_swap_volume(
        swaps, pool=base.pool, token_mint=base.token_mint,
        quote_mint=quote_mint, as_of=base.as_of, window=volume_window,
    )
    ids = market.evidence_ids + volume.evidence_ids
    if len(ids) != len(set(ids)):
        raise ValueError("evidence_id replicado entre token/liquidez e volume")

    # An archived hash binds bytes to a receipt; it does not authenticate RPC.
    source_status = base.source_status
    if source_status == "VERIFIED" and (
        not market.source_authenticated
        or volume.quality != "VERIFIED"
        or not market.source_id
    ):
        source_status = "UNKNOWN"
    if market.source_id and swaps and any(s.source_id != market.source_id for s in swaps):
        source_status = "CONFLICTED"

    danger = set(base.mandatory_blocks)
    danger.update(market.mandatory_blocks)
    manipulation = set(base.manipulation_flags)
    manipulation.update(volume.risk_flags)
    # Absence of token or pool evidence never becomes VERIFIED.
    token_status = market.token_safety
    verified_liquidity = market.liquidity_verified and market.source_authenticated
    verified_volume = volume.volume_verified and source_status == "VERIFIED"
    if market.reasons or volume.reasons:
        source_status = "UNKNOWN" if source_status != "CONFLICTED" else source_status

    evidence = replace(
        base,
        source_status=source_status,
        token_safety=token_status,
        liquidity_quote=market.liquidity_quote,
        liquidity_verified=verified_liquidity,
        volume_quote=volume.quote_volume,
        volume_verified=verified_volume,
        mandatory_blocks=tuple(sorted(danger)),
        manipulation_flags=tuple(sorted(manipulation)),
    )
    result = classify_opportunity(evidence, consensus)
    # Do not grant market safety merely because the caller asserts a pass.
    # Current WalletConsensusService always leaves independence unverified.
    return MarketOpportunityAudit(
        classification=result, safety=market, volume=volume,
        evidence_ids=ids,
    )
