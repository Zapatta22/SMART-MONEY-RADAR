"""Evidence-gated wrapper around both existing SMR paper entry modes.

No change to the trading engine or its existing historical CLI. This wrapper
is opt-in until archive evidence and end-to-end acceptance are validated.
"""
from datetime import datetime, timezone
from dataclasses import replace

from smart_money_radar.domain.paper_entry_risk_policy import (
    EntryRiskLimits, EntryRiskSnapshot, evaluate_entry_risk,
)

from smart_money_radar.domain.paper_evidence_gate import gate_paper_evidence
from smart_money_radar.domain.paper_replay import (
    PaperConfig, ReplayTick, replay_paper, compare_paper_reports,
)


def replay_with_evidence(ticks: list[ReplayTick], evidence_by_quote: dict,
                         *, config: PaperConfig, expected_pool: str,
                         require_observed_quote: bool = True,
                         as_of: datetime | None = None,
                         risk_limits: EntryRiskLimits | None = None,
                         risk_by_quote: dict | None = None):
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
        if risk_limits is not None and tick.entry_allowed:
            risk = risk_by_quote.get(tick.quote_id)
            if not isinstance(risk, EntryRiskSnapshot):
                rejected_risk_ticks += 1
                tick = replace(tick, entry_allowed=False)
            else:
                reasons = evaluate_entry_risk(risk_limits, risk)
                if reasons:
                    rejected_risk_ticks += 1
                    tick = replace(tick, entry_allowed=False)
        verified.append(tick)
    immediate = replay_paper(verified, config=config, mode="immediate")
    confirmed = replay_paper(verified, config=config, mode="confirmed")
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
    # Reject gaps rather than stitching a pending order across missing ticks.
    if not isinstance(ticks, list) or not isinstance(evidence_by_quote, dict):
        raise ValueError("histórico protegido inválido")
    for tick in ticks:
        if not isinstance(tick, ReplayTick) or not tick.quote_id:
            raise ValueError("tick sem identidade de cotação")
        records = evidence_by_quote.get(tick.quote_id)
        if not isinstance(records, list) or not records:
            raise ValueError("lacuna de evidência no histórico protegido")
        if tick.entry_allowed and not isinstance(risk_by_quote.get(tick.quote_id), EntryRiskSnapshot):
            raise ValueError("lacuna de risco no histórico protegido")
    # Preflight every observation: an invalid record must not be silently
    # discarded while a pending order later fills at another price.
    previous_at = None
    for tick in ticks:
        if previous_at is not None and tick.at <= previous_at:
            raise ValueError("histórico protegido fora de ordem")
        previous_at = tick.at
        stamp = tick.at.astimezone(timezone.utc).isoformat()
        try:
            gate_paper_evidence(
                signal_at=stamp, decision_at=stamp,
                evidence=evidence_by_quote[tick.quote_id],
                expected_pool=expected_pool, require_observed_quote=True,
            )
        except ValueError as exc:
            raise ValueError("evidência inválida no histórico protegido") from exc
    return replay_with_evidence(
        ticks, evidence_by_quote, config=config, expected_pool=expected_pool,
        require_observed_quote=True, as_of=as_of,
        risk_limits=risk_limits, risk_by_quote=risk_by_quote,
    )
