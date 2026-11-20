"""Evidence-gated wrapper around both existing SMR paper entry modes.

No change to the trading engine or its existing historical CLI. This wrapper
is opt-in until archive evidence and end-to-end acceptance are validated.
"""
from datetime import timezone

from smart_money_radar.domain.paper_evidence_gate import gate_paper_evidence
from smart_money_radar.domain.paper_replay import (
    PaperConfig, ReplayTick, replay_paper, compare_paper_reports,
)


def replay_with_evidence(ticks: list[ReplayTick], evidence_by_quote: dict,
                         *, config: PaperConfig, expected_pool: str,
                         require_observed_quote: bool = True):
    """Run both entry modes on the identical fail-closed evidence-filtered ticks.

    Every replay observation must have evidence keyed by quote_id. Missing or
    invalid evidence removes the entire tick, including its price and volume.
    No pending fill, valuation or exit can consume an unverified observation.
    """
    if not isinstance(ticks, list) or not isinstance(evidence_by_quote, dict):
        raise ValueError("ticks/evidências inválidos")
    verified = []
    rejected_evidence_ticks = 0
    previous = None
    for tick in ticks:
        if not isinstance(tick, ReplayTick):
            raise ValueError("tick inválido")
        if previous is not None and tick.at <= previous:
            raise ValueError("ticks fora de ordem")
        previous = tick.at
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
        verified.append(tick)
    immediate = replay_paper(verified, config=config, mode="immediate")
    confirmed = replay_paper(verified, config=config, mode="confirmed")
    return {
        "rejected_evidence_ticks": rejected_evidence_ticks,
        "verified_ticks": len(verified),
        "immediate": immediate,
        "confirmed": confirmed,
        "comparison": compare_paper_reports(immediate, confirmed),
        "evidence_policy": "OBSERVED_ONLY" if require_observed_quote else "MODEL_ALLOWED_PAPER_ONLY",
    }
