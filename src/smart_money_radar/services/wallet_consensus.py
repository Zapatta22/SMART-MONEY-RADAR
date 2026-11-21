"""Point-in-time, non-trading consensus of independent Smart Money wallets.

This consumes WalletSignalService reports and never claims wallet independence
from address count alone. Missing provenance, mixed direction, insufficient
samples or owner-identity uncertainty fail closed into non-actionable status.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal, Protocol

from smart_money_radar.services.wallet_signals import WalletSignalService


@dataclass(frozen=True)
class WalletConsensusMember:
    wallet: str
    direction: Literal["BUY", "SELL", "MIXED", "INSUFFICIENT"]
    signatures: tuple[str, ...]
    excluded_count: int


@dataclass(frozen=True)
class WalletConsensusReport:
    direction: Literal["BUY", "SELL", "MIXED", "INSUFFICIENT"]
    eligible_wallets: int
    supporting_signatures: int
    rejected_wallets: tuple[str, ...]
    members: tuple[WalletConsensusMember, ...]
    independence_verified: bool
    actionable: bool
    reasons: tuple[str, ...]
    dependency_groups: tuple[tuple[str, ...], ...] = ()
    verified_independent_wallets: int = 0


class WalletConsensusService:
    """Aggregate existing scoped wallet reports without generating trade signals."""

    def __init__(self, signal_service: WalletSignalService) -> None:
        self.signal_service = signal_service

    def get_report(
        self, *, wallets: tuple[str, ...], program: str, pool: str,
        base_mint: str, quote_mint: str, as_of: datetime,
        window: timedelta, max_publication_delay: timedelta,
        min_confidence: Decimal, min_transactions_per_wallet: int = 2,
        min_wallets: int = 2,
    ) -> WalletConsensusReport:
        if (not isinstance(wallets, tuple) or not wallets
                or any(not isinstance(w, str) or not w.strip() for w in wallets)
                or len(set(wallets)) != len(wallets)):
            raise ValueError("lista de carteiras deve ser não vazia e sem duplicatas")
        if type(min_wallets) is not int or min_wallets < 2:
            raise ValueError("consenso exige pelo menos duas carteiras distintas")
        if len(wallets) > 256:
            raise ValueError("limite de carteiras excedido")
        members: list[WalletConsensusMember] = []
        accepted = []
        rejected = []
        signatures = set()
        for wallet in wallets:
            report = self.signal_service.get_report(
                wallet=wallet, program=program, pool=pool,
                base_mint=base_mint, quote_mint=quote_mint, as_of=as_of,
                window=window, max_publication_delay=max_publication_delay,
                min_confidence=min_confidence,
                min_transactions=min_transactions_per_wallet,
            )
            observed = tuple(e.signature for e in report.evidence)
            members.append(WalletConsensusMember(
                wallet=wallet, direction=report.direction,
                signatures=observed,
                excluded_count=len(report.excluded),
            ))
            if report.direction not in ("BUY", "SELL"):
                rejected.append(wallet)
            else:
                accepted.append((wallet, report.direction, observed))
                signatures.update(observed)
        directions = {direction for _, direction, _ in accepted}
        if len(directions) > 1:
            direction: Literal["BUY","SELL","MIXED","INSUFFICIENT"] = "MIXED"
        elif len(accepted) < min_wallets:
            direction = "INSUFFICIENT"
        else:
            direction = accepted[0][1]
        reasons = ["wallet_independence_unverified"]
        if rejected:
            reasons.append("ineligible_wallet_reports")
        if len(directions) > 1:
            reasons.append("conflicting_directions")
        if len(accepted) < min_wallets:
            reasons.append("insufficient_distinct_wallets")
        # Connected components of shared transaction evidence, not ownership clusters.
        groups = shared_evidence_groups([(w, sigs) for w, _, sigs in accepted])
        if any(len(g)>1 for g in groups):
            reasons.append("shared_transaction_dependency")
        # One transaction can appear across wallets. Count the signature once.
        if len(signatures) < min_wallets:
            reasons.append("insufficient_distinct_signatures")
        # Wallet addresses can be controlled by a single actor (Sybil).
        # A directional summary is deliberately NOT an executable signal.
        return WalletConsensusReport(
            direction=direction,
            eligible_wallets=len(accepted),
            supporting_signatures=len(signatures),
            rejected_wallets=tuple(rejected),
            members=tuple(members),
            independence_verified=False,
            actionable=False,
            reasons=tuple(reasons),
            dependency_groups=groups,
            verified_independent_wallets=0,
        )


def shared_evidence_groups(members):
    """Deterministic transitive evidence grouping; singleton is not independence."""
    groups=[]
    for wallet, signatures in sorted(members):
        sigs=set(signatures)
        matching=[i for i,(_,evidence) in enumerate(groups) if evidence & sigs]
        wallets={wallet}
        for i in reversed(matching):
            old,ev=groups.pop(i)
            wallets.update(old);sigs.update(ev)
        groups.append((wallets,sigs))
    return tuple(sorted(tuple(sorted(wallets)) for wallets,_ in groups))
