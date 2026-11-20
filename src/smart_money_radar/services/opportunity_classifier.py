"""Deterministic non-executable opportunity classification based on archived evidence.

Scores describe *observed signals* only; all mandatory safety and provenance
requirements are independent of score, and no order or trading permission exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from smart_money_radar.services.wallet_consensus import WalletConsensusReport

Verdict = Literal["REJECTED", "UNKNOWN", "WATCH", "PRIORITY"]
EvidenceStatus = Literal["VERIFIED", "UNKNOWN", "CONFLICTED"]
EntryMode = Literal["immediate", "confirmed"]


@dataclass(frozen=True)
class OpportunityEvidence:
    token_mint: str
    chain: str
    pool: str
    as_of: datetime
    source_id: str
    source_status: EvidenceStatus
    history_coverage: Literal["COMPLETE", "PARTIAL", "UNKNOWN", "GAP"]
    token_safety: EvidenceStatus
    liquidity_quote: Decimal | None
    volume_quote: Decimal | None
    liquidity_verified: bool
    volume_verified: bool
    price_confirmation: bool | None
    volume_confirmation: bool | None
    mandatory_blocks: tuple[str, ...] = ()
    manipulation_flags: tuple[str, ...] = ()
    # Explicit audit-only evidence; never infer distinct wallet owners from addresses.
    wallet_independence_verified: bool = False


@dataclass(frozen=True)
class OpportunityClassification:
    token_mint: str
    chain: str
    pool: str
    as_of: datetime
    source_id: str
    score: int
    verdict: Verdict
    data_quality: Literal["VERIFIED", "PARTIAL", "UNKNOWN"]
    wallet_count: int
    unique_signatures: int
    directional_consensus: str
    wallet_independence: EvidenceStatus
    liquidity_quote: Decimal | None
    volume_quote: Decimal | None
    modes: tuple[tuple[EntryMode, str], ...]
    reasons: tuple[str, ...]
    score_breakdown: tuple[tuple[str, int], ...]
    operational_authorized: bool = False


def classify_opportunity(
    evidence: OpportunityEvidence, consensus: WalletConsensusReport,
) -> OpportunityClassification:
    """A pure and deterministic comparison function, never an executor.

    Callers must provide point-in-time evidence. False assertions about
    provenance are not independently authenticated by this function.
    """
    if not isinstance(evidence, OpportunityEvidence) or not isinstance(
        consensus, WalletConsensusReport
    ):
        raise TypeError("contratos de classificação inválidos")
    if any(not isinstance(s, str) or not s.strip()
           for s in (evidence.token_mint, evidence.chain, evidence.pool, evidence.source_id)):
        raise ValueError("identidade de token, origem e pool obrigatórias")
    if evidence.chain != "solana":
        raise ValueError("chain ainda não suportada pela evidência Smart Money")
    if not isinstance(evidence.as_of, datetime) or evidence.as_of.utcoffset() is None:
        raise ValueError("as_of deve possuir fuso horário")
    if evidence.source_status not in ("VERIFIED", "UNKNOWN", "CONFLICTED"):
        raise ValueError("estado de origem inválido")
    if evidence.token_safety not in ("VERIFIED", "UNKNOWN", "CONFLICTED"):
        raise ValueError("estado de risco inválido")
    if evidence.history_coverage not in ("COMPLETE", "PARTIAL", "UNKNOWN", "GAP"):
        raise ValueError("cobertura inválida")
    if type(evidence.liquidity_verified) is not bool or type(evidence.volume_verified) is not bool:
        raise ValueError("indicadores de integridade inválidos")
    if type(evidence.wallet_independence_verified) is not bool:
        raise ValueError("independência inválida")
    if evidence.price_confirmation not in (None, True, False):
        raise ValueError("confirmação de preço inválida")
    if evidence.volume_confirmation not in (None, True, False):
        raise ValueError("confirmação de volume inválida")
    for value in (evidence.liquidity_quote, evidence.volume_quote):
        if value is not None and (
            not isinstance(value, Decimal) or not value.is_finite() or value < 0
        ):
            raise ValueError("liquidez ou volume inválido")
    if any(not isinstance(v, str) or not v.strip()
           for v in evidence.mandatory_blocks + evidence.manipulation_flags):
        raise ValueError("riscos devem conter justificativas válidas")
    if not isinstance(consensus.eligible_wallets, int) or consensus.eligible_wallets < 0:
        raise ValueError("quantidade de carteiras inválida")
    if not isinstance(consensus.supporting_signatures, int) or consensus.supporting_signatures < 0:
        raise ValueError("quantidade de assinaturas inválida")
    if consensus.direction not in ("BUY", "SELL", "MIXED", "INSUFFICIENT"):
        raise ValueError("consenso inválido")
    if consensus.independence_verified and not evidence.wallet_independence_verified:
        raise ValueError("evidências de independência contraditórias")

    reasons: set[str] = set(evidence.mandatory_blocks)
    reasons.update(f"manipulation:{flag}" for flag in evidence.manipulation_flags)
    score_parts: dict[str, int] = {}
    # Duplicates are already collapsed by the consensus service.  This
    # function does not count individual hops and signatures as separate votes.
    score_parts["direction"] = 25 if consensus.direction == "BUY" else 0
    score_parts["wallet_consensus"] = min(consensus.eligible_wallets, 4) * 5
    score_parts["evidence_signatures"] = min(consensus.supporting_signatures, 5) * 3
    score_parts["liquidity"] = (
        15 if evidence.liquidity_verified
        and evidence.liquidity_quote is not None and evidence.liquidity_quote > 0 else 0
    )
    score_parts["volume"] = (
        10 if evidence.volume_verified
        and evidence.volume_quote is not None and evidence.volume_quote > 0 else 0
    )
    score_parts["integrity"] = (
        10 if evidence.source_status == "VERIFIED" and
        evidence.history_coverage == "COMPLETE" else 0
    )
    score = min(100, sum(score_parts.values()))

    if consensus.direction == "MIXED":
        reasons.add("contradictory_wallet_signals")
    if consensus.direction != "BUY":
        reasons.add("no_buy_consensus")
    if consensus.eligible_wallets < 2 or consensus.supporting_signatures < 2:
        reasons.add("insufficient_independent_observations")
    if not consensus.independence_verified or not evidence.wallet_independence_verified:
        reasons.add("wallet_independence_unknown")
    if evidence.source_status != "VERIFIED":
        reasons.add("source_provenance_unverified")
    if evidence.history_coverage != "COMPLETE":
        reasons.add("historical_coverage_incomplete")
    if evidence.token_safety != "VERIFIED":
        reasons.add("token_safety_unverified")
    if (not evidence.liquidity_verified or evidence.liquidity_quote is None
            or evidence.liquidity_quote <= 0):
        reasons.add("liquidity_unknown")
    if (not evidence.volume_verified or evidence.volume_quote is None
            or evidence.volume_quote <= 0):
        reasons.add("volume_unknown")
    if evidence.price_confirmation is not True:
        reasons.add("price_not_confirmed")
    if evidence.volume_confirmation is not True:
        reasons.add("volume_not_confirmed")
    if evidence.mandatory_blocks or evidence.manipulation_flags or evidence.source_status == "CONFLICTED" or evidence.token_safety == "CONFLICTED" or evidence.history_coverage == "GAP":
        verdict: Verdict = "REJECTED"
    elif consensus.direction == "MIXED" or consensus.direction == "SELL":
        verdict = "REJECTED"
    elif any(r in reasons for r in (
        "wallet_independence_unknown", "source_provenance_unverified",
        "historical_coverage_incomplete", "token_safety_unverified",
        "liquidity_unknown", "volume_unknown", "insufficient_independent_observations",
    )):
        verdict = "UNKNOWN"
    elif score >= 70:
        verdict = "PRIORITY"
    else:
        verdict = "WATCH"
    # These are *simulation eligibility descriptions* only; neither option
    # ever authorizes financial execution.
    safety_ready = verdict in ("PRIORITY", "WATCH") and not any(r in reasons for r in (
        "wallet_independence_unknown", "source_provenance_unverified",
        "historical_coverage_incomplete", "token_safety_unverified",
        "liquidity_unknown", "volume_unknown", "no_buy_consensus",
    ))
    modes: tuple[tuple[EntryMode, str], ...] = (
        ("immediate", "SIMULATION_CANDIDATE" if safety_ready else "BLOCKED"),
        ("confirmed", "SIMULATION_CANDIDATE" if safety_ready
         and evidence.price_confirmation is True
         and evidence.volume_confirmation is True else "BLOCKED"),
    )
    if not safety_ready and verdict not in ("REJECTED", "UNKNOWN"):
        verdict = "UNKNOWN"
    if (evidence.source_status == "VERIFIED" and evidence.history_coverage == "COMPLETE"
            and evidence.token_safety == "VERIFIED" and evidence.liquidity_verified
            and evidence.volume_verified and evidence.wallet_independence_verified
            and consensus.independence_verified and not evidence.mandatory_blocks
            and not evidence.manipulation_flags):
        quality: Literal["VERIFIED","PARTIAL","UNKNOWN"] = "VERIFIED"
    elif evidence.source_status == "UNKNOWN" or evidence.history_coverage == "UNKNOWN":
        quality = "UNKNOWN"
    else:
        quality = "PARTIAL"
    return OpportunityClassification(
        token_mint=evidence.token_mint,
        chain=evidence.chain,
        pool=evidence.pool,
        as_of=evidence.as_of.astimezone(timezone.utc),
        source_id=evidence.source_id,
        score=score,
        verdict=verdict,
        data_quality=quality,
        wallet_count=consensus.eligible_wallets,
        unique_signatures=consensus.supporting_signatures,
        directional_consensus=consensus.direction,
        wallet_independence="VERIFIED" if consensus.independence_verified
        and evidence.wallet_independence_verified else "UNKNOWN",
        liquidity_quote=evidence.liquidity_quote,
        volume_quote=evidence.volume_quote,
        modes=modes,
        reasons=tuple(sorted(reasons)),
        score_breakdown=tuple(sorted(score_parts.items())),
        operational_authorized=False,
    )


def rank_opportunities(
    items: tuple[OpportunityClassification, ...],
) -> tuple[OpportunityClassification, ...]:
    """Deterministic, informational rank; rejected/unknown never outrank eligible."""
    if not isinstance(items, tuple) or any(not isinstance(i, OpportunityClassification) for i in items):
        raise TypeError("ranking requer relatórios de classificação")
    priority = {"PRIORITY": 0, "WATCH": 1, "UNKNOWN": 2, "REJECTED": 3}
    return tuple(sorted(items, key=lambda item: (
        priority[item.verdict], -item.score, item.chain, item.token_mint,
        item.pool, item.as_of.isoformat(),
    )))
