"""Point-in-time Raydium CPMM *theoretical* quote from audited pool reserves.

Reuses existing generic constant-product math. A local decoder or RPC
'finalized' snapshot cannot prove a filled or executable price. Never route
this output to the observed-quote gate as a real execution price.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from smart_money_radar.domain.cpmm_reserve_snapshot import (
    AuditedReserveSnapshot, validate_snapshot, estimate_from_snapshot,
)
from smart_money_radar.domain.cpmm_reserve_estimator import CPMMEstimate

@dataclass(frozen=True)
class CpmmTheoreticalQuote:
    quote_id: str
    source_id: str
    pool: str
    slot: int
    input_mint: str
    output_mint: str
    reserve_raw_sha256: str
    captured_at: datetime
    available_at: datetime
    estimate: CPMMEstimate | None
    status: Literal["THEORETICAL_ONLY", "BLOCKED"]
    reasons: tuple[str, ...]
    observed_market_quote: bool = False
    executable_price_verified: bool = False


def theoretical_cpmm_quote(
    *, snapshot_record: dict, raw_payload: bytes,
    source_id: str, quote_id: str, expected_pool: str,
    expected_slot: int, input_mint: str, output_mint: str,
    amount_in: Decimal, cutoff: datetime,
    max_age: timedelta = timedelta(minutes=2),
    fee_provenance_verified: bool = False,
) -> CpmmTheoreticalQuote:
    """Audited identity + first-publication gate for non-executable estimates."""
    if not all(isinstance(x,str) and x.strip() for x in (
        source_id, quote_id, expected_pool, input_mint, output_mint
    )):
        raise ValueError("identificadores de cotação obrigatórios")
    if type(expected_slot) is not int or expected_slot < 0:
        raise ValueError("slot inválido")
    if not isinstance(cutoff,datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff sem fuso")
    if not isinstance(max_age,timedelta) or max_age<=timedelta(0):
        raise ValueError("idade máxima inválida")
    if not isinstance(fee_provenance_verified,bool):
        raise ValueError("estado da taxa inválido")
    snap=validate_snapshot(snapshot_record,raw_payload)
    if (snap.pool!=expected_pool or snap.slot!=expected_slot
        or snap.input_mint!=input_mint or snap.output_mint!=output_mint):
        raise ValueError("pool/slot/mint do snapshot divergem da cotação")
    captured=datetime.fromisoformat(snap.captured_at.replace("Z","+00:00")).astimezone(timezone.utc)
    available=datetime.fromisoformat(snap.available_at.replace("Z","+00:00")).astimezone(timezone.utc)
    point=cutoff.astimezone(timezone.utc)
    if available>point:
        raise ValueError("cotação posterior ao instante da decisão")
    reasons=set()
    if point-available>max_age:
        reasons.add("reserve_snapshot_stale")
    if not fee_provenance_verified:
        reasons.add("fee_origin_unverified")
    if not isinstance(amount_in,Decimal) or not amount_in.is_finite() or amount_in<=0:
        raise ValueError("quantidade inválida")
    if amount_in>snap.reserve_in:
        reasons.add("input_amount_exceeds_effective_reserve")
    # A snapshot by itself does not prove Solana owner/PDA, fee parity or
    # provider authenticity. Always distinguish estimate from observation.
    estimate=estimate_from_snapshot(snap,amount_in) if not reasons else None
    reasons.add("not_observed_market_quote")
    reasons.add("provider_independent_authentication_missing")
    reasons.add("execution_not_proven")
    return CpmmTheoreticalQuote(
        quote_id=quote_id,source_id=source_id,pool=expected_pool,
        slot=expected_slot,input_mint=input_mint,output_mint=output_mint,
        reserve_raw_sha256=snap.raw_sha256,captured_at=captured,
        available_at=available,estimate=estimate,
        status="THEORETICAL_ONLY" if estimate is not None else "BLOCKED",
        reasons=tuple(sorted(reasons)),
    )
