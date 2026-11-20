"""Fail-closed full-chain preflight before invoking existing strict paper replay.

A candidate with unauthenticated RAW/quotes has *no executable history* and
must not enter the replay engine, even when the local quote gate returns a tick.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from smart_money_radar.domain.paper_entry_risk_policy import (
    EntryRiskLimits, EntryRiskSnapshot, evaluate_entry_risk,
)
from smart_money_radar.domain.paper_replay import PaperConfig, ReplayTick
from smart_money_radar.domain.paper_evidence_replay import replay_with_required_risk
from smart_money_radar.services.evidence_chain import EvidenceChain

@dataclass(frozen=True)
class StrictReplayCandidate:
    chain: EvidenceChain
    tick: ReplayTick | None
    risk: EntryRiskSnapshot | None
    classification_allows_simulation: bool
    quote_available_at: datetime | None
    evidence_id: str | None
    evidence_pool: str | None


@dataclass(frozen=True)
class StrictReplayOutcome:
    status: Literal["BLOCKED", "PAPER_COMPARISON_ONLY"]
    reasons: tuple[str, ...]
    immediate: object | None = None
    confirmed: object | None = None
    comparison: dict | None = None
    economic_results_credible: bool = False
    operational_authorized: bool = False


def strict_economic_replay(
    candidates: tuple[StrictReplayCandidate, ...], *, pool: str,
    config: PaperConfig, risk_limits: EntryRiskLimits, cutoff: datetime,
) -> StrictReplayOutcome:
    """Never call the paper engine unless the entire evidence chain is trusted.

    Future authenticated source adapters can supply attested chains. Current
    EvidenceChain contracts are intentionally unauthenticated and cannot
    unlock this gate via caller-controlled flags.
    """
    if not isinstance(candidates, tuple) or any(
        not isinstance(c, StrictReplayCandidate) for c in candidates
    ):
        raise TypeError("candidatos de replay inválidos")
    if not isinstance(config, PaperConfig) or not isinstance(risk_limits, EntryRiskLimits):
        raise TypeError("configuração/riscos inválidos")
    if not isinstance(cutoff, datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff sem fuso")
    if not isinstance(pool, str) or not pool.strip():
        raise ValueError("pool obrigatório")
    as_of = cutoff.astimezone(timezone.utc)
    reasons: set[str] = set()
    quote_ids: set[str] = set()
    prev = None
    for item in candidates:
        chain = item.chain
        if not isinstance(chain, EvidenceChain):
            raise TypeError("cadeia inválida")
        if chain.pool != pool or item.evidence_pool != pool:
            reasons.add("pool_mismatch")
        if chain.cutoff > as_of:
            reasons.add("chain_future")
        if prev is not None and chain.cutoff <= prev:
            reasons.add("out_of_order_or_duplicate_cutoff")
        prev = chain.cutoff
        if not chain.quote_id or not item.evidence_id:
            reasons.add("missing_quote_or_evidence_id")
        elif chain.quote_id in quote_ids:
            reasons.add("duplicate_quote_id")
        else:
            quote_ids.add(chain.quote_id)
        if item.tick is None or item.risk is None:
            reasons.add("tick_or_risk_missing")
            continue
        if item.tick.quote_id != chain.quote_id:
            reasons.add("quote_tick_mismatch")
        if item.quote_available_at is None or item.quote_available_at != item.tick.at:
            reasons.add("quote_availability_mismatch")
        if item.tick.at > as_of or item.tick.at > chain.cutoff:
            reasons.add("future_price")
        if not item.classification_allows_simulation:
            reasons.add("classification_blocked")
        if evaluate_entry_risk(risk_limits, item.risk):
            reasons.add("mandatory_risk_block")
        if (chain.status != "LOCALLY_LINKED_UNATTESTED"
                or not chain.provider_authenticated or not chain.finalized_attested
                or not chain.executable_price_verified):
            reasons.add("full_chain_not_authenticated")
    if not candidates:
        reasons.add("no_historical_evidence")
    if reasons:
        return StrictReplayOutcome(status="BLOCKED", reasons=tuple(sorted(reasons)))
    # Today this point is structurally unreachable for EvidenceChain outputs
    # because provider_authenticated/finality/executability are never inferred
    # by any local bridge. No fake paper PnL may be emitted.
    raise AssertionError("no externally attested chain adapter is configured")
