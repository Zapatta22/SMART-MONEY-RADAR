"""CM38J: provenance and temporal quality envelope for economic indicators.

Information-only: no RPC, ledger mutation, order submission or synthetic execution.
Values are never inferred from direction-only swaps or caller flags.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json

LAUNCH_INDICATORS = (
    "liquidity", "interval_volume", "depth", "market_impact",
    "entry_cost", "exit_cost", "holder_concentration",
    "token_authorities", "manipulation_risk",
)
SMART_MONEY_INDICATORS = (
    "realized_pnl", "acquisition_cost", "fees", "unrealized_pnl",
    "drawdown", "win_rate", "temporal_consistency",
    "wallet_correlation", "independent_consensus",
)
_ALLOWED_QUALITY = ("VERIFIED", "PARTIAL", "UNKNOWN", "CONFLICTED")


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("aware UTC datetime required")
    return value.astimezone(timezone.utc)


def describe_metric(*, name: str, value: Decimal | None,
                    evidence_ids: tuple[str, ...] = (),
                    source_id: str | None = None,
                    start: datetime, end: datetime, available_at: datetime,
                    decision_at: datetime, quality: str = "UNKNOWN",
                    unavailable_reason: str | None = None) -> dict:
    """Build an immutable-by-value, hash-addressed information-only receipt.

    An available value requires verified source provenance, a bounded observation
    window and a timestamp proving the datum existed by the decision cutoff.
    """
    if name not in LAUNCH_INDICATORS + SMART_MONEY_INDICATORS:
        raise ValueError("unsupported economic indicator")
    start, end, available_at, decision_at = map(
        _utc, (start, end, available_at, decision_at))
    if not start <= end <= available_at <= decision_at:
        raise ValueError("lookahead or invalid observation interval")
    if decision_at > datetime.now(timezone.utc):
        raise ValueError("future decision cutoff")
    if quality not in _ALLOWED_QUALITY:
        raise ValueError("invalid evidence quality")
    if any(not isinstance(e, str) or len(e) != 64 or
           any(c not in "0123456789abcdef" for c in e) for e in evidence_ids):
        raise ValueError("invalid evidence digest")
    if value is not None:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError("finite Decimal required")
        if quality != "VERIFIED" or not source_id or not evidence_ids:
            raise ValueError("value without verified linked evidence")
        if unavailable_reason is not None:
            raise ValueError("available indicator cannot have missing reason")
    elif not unavailable_reason or not isinstance(unavailable_reason, str):
        raise ValueError("unavailable indicator requires reason")
    receipt = {
        "schema": "smr.cm38j.economic_metric.v1",
        "name": name, "value": str(value) if value is not None else None,
        "source_id": source_id, "evidence_ids": sorted(set(evidence_ids)),
        "window_start": start.isoformat(), "window_end": end.isoformat(),
        "available_at": available_at.isoformat(),
        "decision_at": decision_at.isoformat(), "quality": quality,
        "unavailable_reason": unavailable_reason,
        "operational_authorized": False,
        "prospective_paper_authorized": False,
    }
    receipt["sha256"] = sha256(json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()
    return receipt


def qualify_metric_set(*, radar: str, metrics: list[dict]) -> dict:
    """Completeness cannot silently upgrade untrusted market evidence."""
    names = LAUNCH_INDICATORS if radar == "launch" else (
        SMART_MONEY_INDICATORS if radar == "smart_money" else None)
    if names is None:
        raise ValueError("unknown radar")
    by_name = {}
    for metric in metrics:
        name = metric.get("name")
        if name not in names or name in by_name:
            raise ValueError("unrecognized or duplicate metric")
        by_name[name] = metric
    missing = [name for name in names if name not in by_name]
    unverified = [name for name in names if
                  name in by_name and (by_name[name].get("value") is None or
                  by_name[name].get("quality") != "VERIFIED")]
    return {
        "radar": radar, "expected": len(names), "received": len(by_name),
        "missing": tuple(missing), "unverified": tuple(unverified),
        "complete_economic_evidence": not missing and not unverified,
        "status": "INFORMATION_ONLY",
        "qualified": False,
        "operational_authorized": False,
        "prospective_paper_authorized": False,
        "strategies": {"immediate": "BLOCKED", "confirmed": "BLOCKED"}
          if radar == "launch" else {},
    }
