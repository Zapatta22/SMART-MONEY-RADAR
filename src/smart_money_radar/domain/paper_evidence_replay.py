"""Evidence-gated wrapper around both existing SMR paper entry modes.

The strict wrapper checks the actual order and account state at simulated fill.
Legacy exploratory replay retains its input-filtering behavior.
"""
from datetime import datetime, timezone
from dataclasses import replace
from decimal import Decimal

from smart_money_radar.domain.paper_entry_risk_policy import (
    EntryRiskLimits, EntryRiskSnapshot, evaluate_entry_risk,
)

from smart_money_radar.domain.paper_evidence_gate import gate_paper_evidence, verify_paper_quote_tick
from smart_money_radar.domain.paper_replay import (
    BPS, PaperConfig, PaperEntryCandidate, ReplayTick, replay_paper, compare_paper_reports,
)


def replay_with_evidence(ticks: list[ReplayTick], evidence_by_quote: dict,
                         *, config: PaperConfig, expected_pool: str,
                         require_observed_quote: bool = True,
                         as_of: datetime | None = None,
                         risk_limits: EntryRiskLimits | None = None,
                         risk_by_quote: dict | None = None,
                         _require_fill_risk: bool = False):
    """Run both entry modes on the identical fail-closed evidence-filtered ticks.

    Every replay observation must have evidence keyed by quote_id. Missing or
    invalid evidence removes the entire tick, including its price and volume.
    No pending fill, valuation or exit can consume an unverified observation.
    """
    if not isinstance(ticks, list) or not isinstance(evidence_by_quote, dict):
        raise ValueError("ticks/evidências inválidos")
    if as_of is not None and (not isinstance(as_of, datetime) or as_of.utcoffset() is None):
        raise ValueError("as_of exige datetime com fuso")
    if (risk_limits is None) != (risk_by_quote is None):
        raise ValueError("limites e snapshots de risco devem ser fornecidos juntos")
    if risk_by_quote is not None and not isinstance(risk_by_quote, dict):
        raise ValueError("snapshots de risco inválidos")
    verified = []
    rejected_risk_ticks = 0
    rejected_evidence_ticks = 0
    excluded_after_cutoff = 0
    previous = None
    for tick in ticks:
        if not isinstance(tick, ReplayTick):
            raise ValueError("tick inválido")
        if previous is not None and tick.at <= previous:
            raise ValueError("ticks fora de ordem")
        previous = tick.at
        if as_of is not None and tick.at > as_of:
            excluded_after_cutoff += 1
            continue
        records = evidence_by_quote.get(tick.quote_id) if tick.quote_id else None
        if not isinstance(records, list) or not records:
            rejected_evidence_ticks += 1
            continue
        stamp = tick.at.astimezone(timezone.utc).isoformat()
        try:
            gate_paper_evidence(
                signal_at=stamp, decision_at=stamp,
                evidence=records, expected_pool=expected_pool,
                require_observed_quote=require_observed_quote,
            )
        except ValueError:
            rejected_evidence_ticks += 1
            continue
        # Never let an unverified price affect fills, stop/take-profit,
        # valuation, confirmation or the execution of a pending sell.
        risk = risk_by_quote.get(tick.quote_id) if risk_by_quote is not None else None
        if _require_fill_risk and isinstance(risk, EntryRiskSnapshot) and risk.emergency_halt:
            tick = replace(tick, halted=True)
        if risk_limits is not None and tick.entry_allowed:
            if not isinstance(risk, EntryRiskSnapshot):
                rejected_risk_ticks += 1
                tick = replace(tick, entry_allowed=False)
            else:
                reasons = evaluate_entry_risk(risk_limits, risk)
                if reasons:
                    rejected_risk_ticks += 1
                    tick = replace(tick, entry_allowed=False)
        verified.append(tick)
    def guard(candidate: PaperEntryCandidate) -> str | None:
        if risk_limits is None or risk_by_quote is None:
            return "risk_snapshot_missing_at_fill"
        risk = risk_by_quote.get(candidate.tick.quote_id)
        if not isinstance(risk, EntryRiskSnapshot):
            return "risk_snapshot_missing_at_fill"
        return _fill_risk_rejection(candidate, risk_limits, risk)

    entry_guard = guard if _require_fill_risk else None
    immediate = replay_paper(verified, config=config, mode="immediate", entry_guard=entry_guard)
    confirmed = replay_paper(verified, config=config, mode="confirmed", entry_guard=entry_guard)
    return {
        "rejected_evidence_ticks": rejected_evidence_ticks,
        "excluded_after_cutoff": excluded_after_cutoff,
        "verified_ticks": len(verified),
        "rejected_risk_ticks": rejected_risk_ticks,
        "risk_policy": "REQUIRED" if risk_limits is not None else "NOT_CONFIGURED",
        "immediate": immediate,
        "confirmed": confirmed,
        "comparison": compare_paper_reports(immediate, confirmed),
        "evidence_policy": "OBSERVED_ONLY" if require_observed_quote else "MODEL_ALLOWED_PAPER_ONLY",
    }


def _fill_risk_rejection(
    candidate: PaperEntryCandidate, limits: EntryRiskLimits, risk: EntryRiskSnapshot,
) -> str | None:
    equity = min(risk.equity, candidate.equity)
    daily_pnl = min(risk.daily_realized_pnl, candidate.daily_realized_pnl)
    decision_price = candidate.decision_tick.ask or candidate.decision_tick.price
    adverse_bps = max(Decimal(0), (candidate.price - decision_price) * BPS / decision_price)
    if candidate.tick.ask is None or candidate.tick.ask_size is None:
        return "quote_depth_missing"
    liquidity = min(risk.verified_liquidity_quote, candidate.tick.ask_size * candidate.tick.ask)
    current = replace(
        risk, equity=equity, proposed_notional=candidate.budget, daily_realized_pnl=daily_pnl,
        estimated_slippage_bps=max(risk.estimated_slippage_bps, adverse_bps),
        verified_liquidity_quote=liquidity,
    )
    reasons = evaluate_entry_risk(limits, current)
    if reasons:
        return reasons[0]
    loss_base = min(equity, candidate.day_start_equity)
    if daily_pnl <= -loss_base * limits.max_daily_loss_fraction:
        return "daily_loss_limit"
    if liquidity < candidate.budget:
        return "insufficient_order_liquidity"
    return None


def replay_with_required_risk(ticks: list[ReplayTick], evidence_by_quote: dict,
                              *, config: PaperConfig, expected_pool: str,
                              risk_limits: EntryRiskLimits,
                              risk_by_quote: dict,
                              as_of: datetime | None = None):
    """Strict paper entry point: observed evidence and risk are mandatory.

    Do not use this function as a live trading authorization. Caller-supplied
    risk snapshots and quote evidence still need independent verification.
    """
    if not isinstance(risk_limits, EntryRiskLimits):
        raise ValueError("política de risco obrigatória")
    if not isinstance(risk_by_quote, dict):
        raise ValueError("snapshots de risco obrigatórios")
    if not isinstance(ticks, list) or not isinstance(evidence_by_quote, dict):
        raise ValueError("histórico protegido inválido")
    if as_of is not None and (not isinstance(as_of, datetime) or as_of.utcoffset() is None):
        raise ValueError("as_of exige datetime com fuso")
    selected = []
    seen_quotes = set()
    previous_at = None
    for tick in ticks:
        if not isinstance(tick, ReplayTick):
            raise ValueError("tick inválido")
        if as_of is not None and tick.at > as_of:
            continue
        if not tick.quote_id:
            raise ValueError("tick sem identidade de cotação")
        if previous_at is not None and tick.at <= previous_at:
            raise ValueError("histórico protegido fora de ordem")
        if tick.quote_id in seen_quotes:
            raise ValueError("cotação duplicada no histórico protegido")
        seen_quotes.add(tick.quote_id)
        previous_at = tick.at
        records = evidence_by_quote.get(tick.quote_id)
        if not isinstance(records, list) or not records:
            raise ValueError("lacuna de evidência no histórico protegido")
        if tick.entry_allowed and not isinstance(risk_by_quote.get(tick.quote_id), EntryRiskSnapshot):
            raise ValueError("lacuna de risco no histórico protegido")
        try:
            verify_paper_quote_tick(tick, records, expected_pool)
        except ValueError as exc:
            raise ValueError(f"evidência inválida no histórico protegido: {exc}") from exc
        selected.append(tick)
    result = replay_with_evidence(
        selected, evidence_by_quote, config=config, expected_pool=expected_pool,
        require_observed_quote=True, risk_limits=risk_limits, risk_by_quote=risk_by_quote,
        _require_fill_risk=True,
    )
    result["excluded_after_cutoff"] = len(ticks) - len(selected)
    return result
