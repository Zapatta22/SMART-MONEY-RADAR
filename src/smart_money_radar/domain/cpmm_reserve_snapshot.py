"""Validate provenance for offline CPMM reserve estimates.

Inputs are an independently collected snapshot, not trusted RPC evidence by themselves.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib

from smart_money_radar.domain.cpmm_reserve_estimator import estimate_exact_input


@dataclass(frozen=True)
class AuditedReserveSnapshot:
    pool: str
    slot: int
    commitment: str
    captured_at: str
    available_at: str
    raw_sha256: str
    reserve_in: Decimal
    reserve_out: Decimal
    fee_bps: Decimal
    input_mint: str
    output_mint: str
    input_decimals: int
    output_decimals: int


def validate_snapshot(record: dict, raw_payload: bytes) -> AuditedReserveSnapshot:
    """Fail closed on missing provenance; hash ties record to supplied raw bytes.

    Does NOT independently establish RPC authenticity, account ownership or
    Raydium-specific fee semantics. Those require separate verification.
    """
    if not isinstance(record, dict) or not isinstance(raw_payload, bytes) or not raw_payload:
        raise ValueError("snapshot ou payload RAW inválido")
    required = ("pool", "slot", "commitment", "captured_at", "available_at",
                "raw_sha256", "reserve_in", "reserve_out", "fee_bps",
                "input_mint", "output_mint", "input_decimals", "output_decimals")
    if any(field not in record for field in required):
        raise ValueError("snapshot sem campos obrigatórios")
    for key in ("pool", "input_mint", "output_mint"):
        if not isinstance(record[key], str) or not record[key].strip():
            raise ValueError(f"{key} inválido")
    for key in ("input_decimals", "output_decimals"):
        if type(record[key]) is not int or not 0 <= record[key] <= 18:
            raise ValueError(f"{key} inválido")
    if record["input_mint"] == record["output_mint"]:
        raise ValueError("mints idênticos")
    if type(record["slot"]) is not int or record["slot"] < 0:
        raise ValueError("slot inválido")
    if record["commitment"] != "finalized":
        raise ValueError("snapshot não finalizado")
    times = []
    for key in ("captured_at", "available_at"):
        if not isinstance(record[key], str):
            raise ValueError("horário inválido")
        try:
            stamp = datetime.fromisoformat(record[key].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("horário inválido") from exc
        if stamp.utcoffset() is None:
            raise ValueError("horário sem fuso")
        times.append(stamp)
    if times[1] < times[0]:
        raise ValueError("disponibilidade anterior à captura")
    digest = hashlib.sha256(raw_payload).hexdigest()
    if record["raw_sha256"] != digest:
        raise ValueError("hash RAW divergente")
    values = {}
    for key in ("reserve_in", "reserve_out", "fee_bps"):
        value = record[key]
        if isinstance(value, bool):
            raise ValueError(f"{key} inválido")
        try:
            value = Decimal(str(value))
        except Exception as exc:
            raise ValueError(f"{key} inválido") from exc
        if not value.is_finite():
            raise ValueError(f"{key} não finito")
        values[key] = value
    if values["reserve_in"] <= 0 or values["reserve_out"] <= 0:
        raise ValueError("reservas inválidas")
    if not 0 <= values["fee_bps"] < 10000:
        raise ValueError("taxa inválida")
    return AuditedReserveSnapshot(
        record["pool"], record["slot"], record["commitment"],
        record["captured_at"], record["available_at"], digest,
        values["reserve_in"], values["reserve_out"], values["fee_bps"],
        record["input_mint"], record["output_mint"],
        record["input_decimals"], record["output_decimals"],
    )


def estimate_from_snapshot(snapshot: AuditedReserveSnapshot, amount_in):
    if not isinstance(snapshot, AuditedReserveSnapshot):
        raise ValueError("snapshot não validado")
    return estimate_exact_input(
        pool=snapshot.pool, slot=snapshot.slot,
        reserve_in=snapshot.reserve_in, reserve_out=snapshot.reserve_out,
        amount_in=amount_in, fee_bps=snapshot.fee_bps,
    )


def estimate_from_raw_units(snapshot: AuditedReserveSnapshot, *, amount_in_raw: int,
                            reserve_in_raw: int, reserve_out_raw: int):
    """Estimate using integer token quantities and explicit mint decimals.

    The integer balances must have been independently verified as effective
    pool reserves; this method does not authenticate vaults or pool ownership.
    """
    if not isinstance(snapshot, AuditedReserveSnapshot):
        raise ValueError("snapshot não validado")
    for name, value in (("amount_in_raw", amount_in_raw),
                        ("reserve_in_raw", reserve_in_raw),
                        ("reserve_out_raw", reserve_out_raw)):
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} inválido")
    input_scale = Decimal(10) ** snapshot.input_decimals
    output_scale = Decimal(10) ** snapshot.output_decimals
    reserve_in = Decimal(reserve_in_raw) / input_scale
    reserve_out = Decimal(reserve_out_raw) / output_scale
    if reserve_in != snapshot.reserve_in or reserve_out != snapshot.reserve_out:
        raise ValueError("reservas RAW divergentes do snapshot")
    return estimate_from_snapshot(snapshot, Decimal(amount_in_raw) / input_scale)
