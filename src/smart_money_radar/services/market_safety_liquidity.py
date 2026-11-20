"""Offline safety/liquidity evidence contracts for Solana opportunity analysis.

No RPC credentials, no orders. Every positive field remains caller-supplied
unless bound to an independently authenticated archive; source assertions by
themselves cannot establish operational safety.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from smart_money_radar.domain.cpmm_reserve_snapshot import validate_snapshot

EvidenceQuality = Literal["UNKNOWN", "PARTIAL", "VERIFIED", "CONFLICTED"]


@dataclass(frozen=True)
class MarketEvidenceEnvelope:
    evidence_id: str
    source_id: str
    token_mint: str
    pool: str
    slot: int
    observed_at: datetime
    available_at: datetime
    commitment: str
    integrity_sha256: str
    raw_payload: bytes
    provider_authenticated: bool = False


@dataclass(frozen=True)
class TokenSafetySnapshot:
    envelope: MarketEvidenceEnvelope
    mint_authority: str | None
    freeze_authority: str | None
    token_program: str
    concentration_fraction: Decimal | None
    concentration_audited: bool
    liquidity_withdrawal_risk: Literal["UNKNOWN", "NONE_EVIDENCED", "FLAGGED"]
    mint_authority_audited: bool
    freeze_authority_audited: bool
    token_program_audited: bool


@dataclass(frozen=True)
class LiquiditySnapshot:
    envelope: MarketEvidenceEnvelope
    quote_mint: str
    quote_reserve: Decimal
    base_reserve: Decimal
    reserve_snapshot: dict
    verified_raw_reserves: bytes
    depth_quote: Decimal | None
    depth_audited: bool
    withdrawal_risk_audited: bool


@dataclass(frozen=True)
class MarketSafetyFinding:
    token_safety: EvidenceQuality
    liquidity_quote: Decimal | None
    liquidity_verified: bool
    mandatory_blocks: tuple[str, ...]
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    observed_at: datetime | None
    available_at: datetime | None
    slot: int | None
    source_id: str | None
    # This does not authenticate the provider. Reserved for externally attested evidence.
    source_authenticated: bool = False


def _time(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} deve ter fuso")
    return value.astimezone(timezone.utc)


def validate_envelope(
    envelope: MarketEvidenceEnvelope, *, as_of: datetime, token_mint: str, pool: str,
    max_age: timedelta = timedelta(minutes=5),
) -> tuple[str, ...]:
    if not isinstance(envelope, MarketEvidenceEnvelope):
        raise TypeError("envelope de mercado inválido")
    point = _time(as_of, "as_of")
    available = _time(envelope.available_at, "available_at")
    observed = _time(envelope.observed_at, "observed_at")
    if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
        raise ValueError("max_age inválido")
    if any(not isinstance(x, str) or not x.strip() for x in
           (envelope.evidence_id, envelope.source_id, envelope.token_mint,
            envelope.pool, envelope.integrity_sha256)):
        raise ValueError("identidade de evidência inválida")
    if envelope.token_mint != token_mint or envelope.pool != pool:
        raise ValueError("token/pool não correspondem à análise")
    if type(envelope.slot) is not int or envelope.slot < 0:
        raise ValueError("slot inválido")
    if not isinstance(envelope.raw_payload, bytes) or not envelope.raw_payload:
        raise ValueError("RAW obrigatório")
    if sha256(envelope.raw_payload).hexdigest() != envelope.integrity_sha256:
        raise ValueError("RAW diverge do hash registrado")
    if observed > available or available > point:
        raise ValueError("evidência futura ou indisponível no instante da decisão")
    reasons = []
    if envelope.commitment != "finalized":
        reasons.append("not_finalized")
    if point - available > max_age:
        reasons.append("stale_evidence")
    if not envelope.provider_authenticated:
        reasons.append("provider_not_authenticated")
    return tuple(reasons)


def assess_token_liquidity(
    *, token: TokenSafetySnapshot | None, liquidity: LiquiditySnapshot | None,
    token_mint: str, pool: str, as_of: datetime,
    min_liquidity_quote: Decimal, max_concentration_fraction: Decimal,
    max_age: timedelta = timedelta(minutes=5),
) -> MarketSafetyFinding:
    """Evaluate scoped claims conservatively; do not promote unsupported safety."""
    _time(as_of, "as_of")
    if (not all(isinstance(v, Decimal) and v.is_finite() for v in
                (min_liquidity_quote, max_concentration_fraction))
            or min_liquidity_quote <= 0
            or not Decimal(0) < max_concentration_fraction < Decimal(1)):
        raise ValueError("limites inválidos")
    if not token_mint.strip() or not pool.strip():
        raise ValueError("escopo inválido")
    reasons: set[str] = set()
    blocks: set[str] = set()
    ids = []
    used = []
    source_ids = set()
    slots = set()
    authenticated = True
    if token is None:
        reasons.add("token_safety_unknown")
    else:
        envelope = token.envelope
        ids.append(envelope.evidence_id)
        used.append(envelope)
        reasons.update(validate_envelope(envelope, as_of=as_of,
                                         token_mint=token_mint, pool=pool, max_age=max_age))
        if token.mint_authority is not None:
            blocks.add("mint_authority_active")
        elif not token.mint_authority_audited:
            reasons.add("mint_authority_unknown")
        if token.freeze_authority is not None:
            blocks.add("freeze_authority_active")
        elif not token.freeze_authority_audited:
            reasons.add("freeze_authority_unknown")
        if not token.token_program_audited or not token.token_program:
            reasons.add("token_program_unknown")
        if token.concentration_fraction is None or not token.concentration_audited:
            reasons.add("concentration_unknown")
        else:
            c = token.concentration_fraction
            if not isinstance(c, Decimal) or not c.is_finite() or not Decimal(0) <= c <= Decimal(1):
                raise ValueError("concentração inválida")
            if c > max_concentration_fraction:
                blocks.add("excessive_concentration")
        if token.liquidity_withdrawal_risk == "FLAGGED":
            blocks.add("liquidity_withdrawal_risk")
        elif token.liquidity_withdrawal_risk != "NONE_EVIDENCED":
            reasons.add("liquidity_withdrawal_unknown")
    available_liquidity = None
    liquidity_ok = False
    if liquidity is None:
        reasons.add("liquidity_unknown")
    else:
        envelope = liquidity.envelope
        ids.append(envelope.evidence_id)
        used.append(envelope)
        reasons.update(validate_envelope(envelope, as_of=as_of,
                                         token_mint=token_mint, pool=pool, max_age=max_age))
        if liquidity.quote_mint == token_mint or not liquidity.quote_mint.strip():
            raise ValueError("mint de cotação inválido")
        # Reuse audited reserve hash/slot/pool checks rather than trusting a label.
        snapshot = validate_snapshot(liquidity.reserve_snapshot, liquidity.verified_raw_reserves)
        if (snapshot.pool != pool or snapshot.slot != envelope.slot
                or snapshot.output_mint != token_mint
                or snapshot.input_mint != liquidity.quote_mint
                or snapshot.reserve_in != liquidity.quote_reserve
                or snapshot.reserve_out != liquidity.base_reserve):
            raise ValueError("reservas e identidade do pool divergem")
        if snapshot.available_at != envelope.available_at.isoformat():
            raise ValueError("horários de reserva e envelope divergem")
        if not isinstance(liquidity.quote_reserve, Decimal) or liquidity.quote_reserve <= 0:
            raise ValueError("reserva de cotação inválida")
        available_liquidity = liquidity.quote_reserve
        if available_liquidity < min_liquidity_quote:
            blocks.add("insufficient_liquidity")
        if liquidity.depth_quote is None or not liquidity.depth_audited:
            reasons.add("market_depth_unknown")
        elif (not isinstance(liquidity.depth_quote, Decimal)
              or not liquidity.depth_quote.is_finite() or liquidity.depth_quote <= 0):
            raise ValueError("profundidade inválida")
        if not liquidity.withdrawal_risk_audited:
            reasons.add("withdrawal_risk_not_audited")
        # RPC JSON+hash alone are not external attestation. Integrity is necessary,
        # not sufficient, for VERIFIED status.
        liquidity_ok = (
            not any(r in reasons for r in ("not_finalized", "stale_evidence",
                                          "provider_not_authenticated"))
            and available_liquidity >= min_liquidity_quote
            and liquidity.depth_quote is not None and liquidity.depth_audited
            and liquidity.withdrawal_risk_audited
        )
    if len(set(ids)) != len(ids):
        raise ValueError("evidence_id duplicado")
    for envelope in used:
        source_ids.add(envelope.source_id)
        slots.add(envelope.slot)
        authenticated &= envelope.provider_authenticated
    if len(source_ids) > 1 or len(slots) > 1:
        reasons.add("cross_source_or_slot_ambiguity")
        liquidity_ok = False
    if blocks:
        status: EvidenceQuality = "CONFLICTED"
    elif not token or any(x in reasons for x in (
        "token_safety_unknown", "mint_authority_unknown", "freeze_authority_unknown",
        "token_program_unknown", "concentration_unknown", "liquidity_withdrawal_unknown",
        "provider_not_authenticated", "not_finalized", "stale_evidence",
        "cross_source_or_slot_ambiguity", "withdrawal_risk_not_audited",
    )):
        status = "UNKNOWN"
    else:
        status = "VERIFIED" if liquidity_ok and not reasons else "PARTIAL"
    # The liquidity number can be displayed as an observed reserve, but is
    # not a verified execution quote or proof of account ownership.
    return MarketSafetyFinding(
        token_safety=status, liquidity_quote=available_liquidity,
        liquidity_verified=liquidity_ok and status == "VERIFIED",
        mandatory_blocks=tuple(sorted(blocks)),
        reasons=tuple(sorted(reasons)),
        evidence_ids=tuple(ids),
        observed_at=max((e.observed_at for e in used), default=None),
        available_at=max((e.available_at for e in used), default=None),
        slot=next(iter(slots)) if len(slots) == 1 else None,
        source_id=next(iter(source_ids)) if len(source_ids) == 1 else None,
        source_authenticated=authenticated and bool(used),
    )
