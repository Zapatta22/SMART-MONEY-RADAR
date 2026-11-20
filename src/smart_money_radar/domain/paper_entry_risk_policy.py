"""Pure, fail-closed pre-trade safety policy for SMR simulation.

This module never places orders. The same policy applies to immediate and
confirmed entry modes. Caller-supplied evidence is not independently verified.
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class EntryRiskLimits:
    max_position_fraction: Decimal
    max_daily_loss_fraction: Decimal
    max_slippage_bps: Decimal
    min_liquidity_quote: Decimal

    def __post_init__(self):
        if (not all(isinstance(v, Decimal) and v.is_finite() for v in (
            self.max_position_fraction, self.max_daily_loss_fraction,
            self.max_slippage_bps, self.min_liquidity_quote
        )) or not Decimal(0) < self.max_position_fraction <= Decimal(1)
                or not Decimal(0) < self.max_daily_loss_fraction <= Decimal(1)
                or not Decimal(0) <= self.max_slippage_bps < Decimal(10000)
                or self.min_liquidity_quote <= 0):
            raise ValueError("limites de risco inválidos")


@dataclass(frozen=True)
class EntryRiskSnapshot:
    equity: Decimal
    proposed_notional: Decimal
    daily_realized_pnl: Decimal
    estimated_slippage_bps: Decimal
    verified_liquidity_quote: Decimal
    emergency_halt: bool
    evidence_verified: bool

    def __post_init__(self):
        values = (self.equity, self.proposed_notional, self.daily_realized_pnl,
                  self.estimated_slippage_bps, self.verified_liquidity_quote)
        if (not all(isinstance(v, Decimal) and v.is_finite() for v in values)
                or type(self.emergency_halt) is not bool
                or type(self.evidence_verified) is not bool):
            raise ValueError("snapshot de risco inválido")


def evaluate_entry_risk(limits: EntryRiskLimits, snapshot: EntryRiskSnapshot) -> tuple[str, ...]:
    """Return reasons to reject entry; empty tuple means policy checks passed.

    Passing this local policy does NOT authorize a real trade.
    """
    if not isinstance(limits, EntryRiskLimits) or not isinstance(snapshot, EntryRiskSnapshot):
        raise ValueError("política de risco inválida")
    reasons = []
    if snapshot.emergency_halt:
        reasons.append("emergency_halt")
    if not snapshot.evidence_verified:
        reasons.append("evidence_unverified")
    if snapshot.equity <= 0 or snapshot.proposed_notional <= 0:
        reasons.append("invalid_capital")
    else:
        if snapshot.proposed_notional > snapshot.equity * limits.max_position_fraction:
            reasons.append("position_limit")
        if snapshot.daily_realized_pnl <= -snapshot.equity * limits.max_daily_loss_fraction:
            reasons.append("daily_loss_limit")
    if snapshot.estimated_slippage_bps < 0 or snapshot.estimated_slippage_bps > limits.max_slippage_bps:
        reasons.append("slippage_limit")
    if snapshot.verified_liquidity_quote < limits.min_liquidity_quote:
        reasons.append("liquidity_limit")
    return tuple(reasons)
