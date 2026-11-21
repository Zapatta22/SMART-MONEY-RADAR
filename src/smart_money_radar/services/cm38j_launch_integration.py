"""CM38J adapters over the existing immutable market/volume/CPMM estimates.

No RPC, prices fetched, orders, or prospective paper ticks. Caller-supplied
snapshots are checked by the existing analyzers. These adapters never upgrade
a model estimate or a locally hashed observation to independent attestation.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from smart_money_radar.domain.cpmm_reserve_snapshot import (
    validate_snapshot, estimate_from_snapshot,
)
from smart_money_radar.services.market_safety_liquidity import (
    assess_token_liquidity,
)
from smart_money_radar.services.market_volume_audit import audit_swap_volume
from smart_money_radar.services.cm38j_metric_provenance import (
    describe_metric, qualify_metric_set,
)

def _missing(*, name, at, start, source=None, ids=(), reason, strategy=None,
             pool=None, unit=None, method=None, kind="UNAVAILABLE"):
    return describe_metric(
        name=name, value=None, start=start, end=at,
        available_at=at, decision_at=at,
        source_id=source, evidence_ids=tuple(ids), quality="UNKNOWN",
        unavailable_reason=reason, radar="launch", strategy=strategy,
        pool=pool, unit=unit, method=method, kind=kind,
    )

def launch_metric_receipts(*, token_mint: str, pool: str, quote_mint: str,
                           at: datetime, strategy: str,
                           safety=None, liquidity=None, swaps=(),
                           min_liquidity_quote=Decimal("100"),
                           max_concentration_fraction=Decimal("0.4"),
                           volume_window=timedelta(minutes=5),
                           amount_in: Decimal | None = None):
    """Reconcile one pool and a bounded interval, never other-pool quotes.

    The safety/volume contracts validate RAW hashes and time. A model impact
    may be reported separately as an estimate, never as observed execution.
    """
    if strategy not in ("immediate", "confirmed"):
        raise ValueError("Launch strategy required")
    if not isinstance(at, datetime) or at.utcoffset() is None:
        raise ValueError("aware cutoff required")
    if amount_in is not None and (not isinstance(amount_in, Decimal)
                                or not amount_in.is_finite() or amount_in <= 0):
        raise ValueError("positive finite estimate amount required")
    safety_audit = assess_token_liquidity(
        token=safety, liquidity=liquidity, token_mint=token_mint,
        pool=pool, as_of=at, min_liquidity_quote=min_liquidity_quote,
        max_concentration_fraction=max_concentration_fraction,
    )
    volume_audit = audit_swap_volume(
        tuple(swaps), pool=pool, token_mint=token_mint,
        quote_mint=quote_mint, as_of=at, window=volume_window,
    )
    if len(set(safety_audit.evidence_ids + volume_audit.evidence_ids)) != (
            len(safety_audit.evidence_ids) + len(volume_audit.evidence_ids)):
        raise ValueError("cross-engine duplicate evidence")
    start = at - volume_window
    if start > at:
        raise ValueError("invalid window")
    reasons = {
        "liquidity": "independent_liquidity_attestation_missing",
        "interval_volume": "independent_volume_attestation_missing",
        "depth": "authenticated_depth_unavailable",
        "market_impact": "observed_execution_impact_unavailable",
        "entry_cost": "observed_entry_cost_unavailable",
        "exit_cost": "observed_exit_cost_unavailable",
        "holder_concentration": "holder_independence_unverified",
        "token_authorities": "token_authority_attestation_missing",
        "manipulation_risk": "market_manipulation_assessment_incomplete",
    }
    metrics = [_missing(name=k, at=at, start=start, strategy=strategy,
                        pool=pool, unit=quote_mint, reason=v)
               for k, v in reasons.items()]
    # An economic observation can be displayed with its original audit result,
    # but the CM38J canonical metric remains UNKNOWN until independent proof.
    reserve = None
    estimate = None
    if liquidity is not None:
        reserve = validate_snapshot(liquidity.reserve_snapshot,
                                    liquidity.verified_raw_reserves)
        if reserve.pool != pool or reserve.available_at != liquidity.envelope.available_at.isoformat():
            raise ValueError("reserve snapshot scope/timestamp mismatch")
        if amount_in is not None:
            estimate = estimate_from_snapshot(reserve, amount_in)
            if estimate.is_observed_quote or estimate.pool != pool:
                raise ValueError("model estimate cannot be observed quote")
    return {
        "radar": "launch", "strategy": strategy, "pool": pool,
        "cutoff": at.isoformat(), "metrics": metrics,
        "metric_audit": qualify_metric_set(radar="launch", metrics=metrics),
        "observed_reserve_quote": str(safety_audit.liquidity_quote)
          if safety_audit.liquidity_quote is not None else None,
        "observed_reserve_quality": safety_audit.token_safety,
        "observed_volume_quote": str(volume_audit.quote_volume)
          if volume_audit.quote_volume is not None else None,
        "observed_volume_quality": volume_audit.quality,
        "reserve_evidence_ids": tuple(safety_audit.evidence_ids),
        "volume_evidence_ids": tuple(volume_audit.evidence_ids),
        "volume_risk_flags": tuple(volume_audit.risk_flags),
        "safety_blocks": tuple(safety_audit.mandatory_blocks),
        "estimated_output": str(estimate.estimated_output) if estimate else None,
        "estimated_impact_fraction": str(estimate.price_impact_fraction)
          if estimate else None,
        "estimate_kind": "MODEL_ESTIMATE_NOT_OBSERVED" if estimate else None,
        "qualified": False,
        "modes": {"immediate": "BLOCKED", "confirmed": "BLOCKED"},
        "operational_authorized": False,
        "prospective_paper_authorized": False,
    }
