"""Offline and point-in-time volume audit for Solana CPMM pools.

Volume is not independently authenticated. Same-signature contradictory
records, wash-like patterns and incomplete provenance fail closed.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Literal


@dataclass(frozen=True)
class SwapVolumeEvidence:
    evidence_id: str
    signature: str
    source_id: str
    pool: str
    token_mint: str
    quote_mint: str
    slot: int
    occurred_at: datetime
    available_at: datetime
    commitment: str
    quote_amount: Decimal
    side: Literal["BUY", "SELL"]
    raw_payload: bytes
    raw_sha256: str
    source_authenticated: bool = False
    wallet: str | None = None


@dataclass(frozen=True)
class VolumeAuditResult:
    quote_volume: Decimal | None
    volume_verified: bool
    quality: Literal["VERIFIED", "UNKNOWN", "CONFLICTED"]
    unique_signatures: int
    duplicate_count: int
    risk_flags: tuple[str, ...]
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    latest_available_at: datetime | None


def audit_swap_volume(
    items: tuple[SwapVolumeEvidence, ...], *, pool: str, token_mint: str,
    quote_mint: str, as_of: datetime, window: timedelta,
    min_unique_signatures: int = 2,
    max_wallet_fraction: Decimal = Decimal("0.80"),
) -> VolumeAuditResult:
    if not isinstance(items, tuple) or any(not isinstance(x, SwapVolumeEvidence) for x in items):
        raise TypeError("evidência de volume inválida")
    if not all(isinstance(x, str) and x.strip() for x in (pool, token_mint, quote_mint)):
        raise ValueError("identidade de volume inválida")
    if token_mint == quote_mint:
        raise ValueError("mint e quote não podem coincidir")
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("as_of sem fuso")
    if not isinstance(window, timedelta) or window <= timedelta(0):
        raise ValueError("janela inválida")
    if type(min_unique_signatures) is not int or min_unique_signatures < 2:
        raise ValueError("limite de assinaturas inválido")
    if (not isinstance(max_wallet_fraction, Decimal)
            or not max_wallet_fraction.is_finite()
            or not Decimal(0) < max_wallet_fraction <= Decimal(1)):
        raise ValueError("fração de concentração inválida")
    point = as_of.astimezone(timezone.utc)
    earliest = point - window
    ids: set[str] = set()
    signatures: dict[str, SwapVolumeEvidence] = {}
    reasons: set[str] = set()
    risks: set[str] = set()
    duplicate_count = 0
    source_ids = set()
    for item in items:
        if any(not isinstance(v, str) or not v.strip() for v in
               (item.evidence_id, item.signature, item.source_id,
                item.pool, item.token_mint, item.quote_mint)):
            raise ValueError("identificadores inválidos")
        if item.evidence_id in ids:
            raise ValueError("evidence_id duplicado")
        ids.add(item.evidence_id)
        if (item.pool, item.token_mint, item.quote_mint) != (pool, token_mint, quote_mint):
            raise ValueError("escopo de volume divergente")
        if type(item.slot) is not int or item.slot < 0:
            raise ValueError("slot inválido")
        if (not isinstance(item.occurred_at, datetime) or item.occurred_at.utcoffset() is None
                or not isinstance(item.available_at, datetime)
                or item.available_at.utcoffset() is None):
            raise ValueError("evidência temporal sem fuso")
        occurred = item.occurred_at.astimezone(timezone.utc)
        available = item.available_at.astimezone(timezone.utc)
        if occurred > available or available > point:
            raise ValueError("dados futuros no replay")
        if not isinstance(item.raw_payload, bytes) or not item.raw_payload:
            raise ValueError("payload RAW ausente")
        if sha256(item.raw_payload).hexdigest() != item.raw_sha256:
            raise ValueError("SHA-256 de volume divergente")
        if not isinstance(item.quote_amount, Decimal) or not item.quote_amount.is_finite() or item.quote_amount <= 0:
            raise ValueError("volume inválido")
        if item.side not in ("BUY", "SELL"):
            raise ValueError("direção de swap inválida")
        if occurred < earliest:
            reasons.add("stale_swap_outside_window")
            continue
        if item.commitment != "finalized":
            reasons.add("unfinalized_volume_evidence")
        if not item.source_authenticated:
            reasons.add("volume_source_not_authenticated")
        source_ids.add(item.source_id)
        previous = signatures.get(item.signature)
        if previous is not None:
            duplicate_count += 1
            # A second record for the same signature cannot contribute new
            # volume; different amount or side is an integrity conflict.
            if (previous.quote_amount != item.quote_amount
                    or previous.side != item.side or previous.slot != item.slot
                    or previous.raw_sha256 != item.raw_sha256):
                risks.add("contradictory_duplicate_signature")
            continue
        signatures[item.signature] = item
    if len(source_ids) > 1:
        reasons.add("mixed_volume_sources")
    if len(signatures) < min_unique_signatures:
        reasons.add("insufficient_unique_swaps")
    if not signatures:
        return VolumeAuditResult(None, False, "UNKNOWN", 0, duplicate_count,
                                 tuple(sorted(risks)), tuple(sorted(reasons | {"volume_unknown"})),
                                 tuple(sorted(ids)), None)
    total = sum((x.quote_amount for x in signatures.values()), Decimal(0))
    per_wallet: dict[str, Decimal] = {}
    for swap in signatures.values():
        if swap.wallet is None:
            reasons.add("wallet_identity_unknown")
            continue
        per_wallet[swap.wallet] = per_wallet.get(swap.wallet, Decimal(0)) + swap.quote_amount
    if per_wallet and max(per_wallet.values()) / total > max_wallet_fraction:
        risks.add("concentrated_volume_by_wallet")
    if len(per_wallet) < 2:
        reasons.add("independent_market_participants_unknown")
    if risks:
        quality: Literal["VERIFIED", "UNKNOWN", "CONFLICTED"] = "CONFLICTED"
    elif reasons:
        quality = "UNKNOWN"
    else:
        quality = "VERIFIED"
    return VolumeAuditResult(
        quote_volume=total,
        volume_verified=quality == "VERIFIED",
        quality=quality,
        unique_signatures=len(signatures),
        duplicate_count=duplicate_count,
        risk_flags=tuple(sorted(risks)),
        reasons=tuple(sorted(reasons)),
        evidence_ids=tuple(sorted(ids)),
        latest_available_at=max(s.available_at for s in signatures.values()),
    )
