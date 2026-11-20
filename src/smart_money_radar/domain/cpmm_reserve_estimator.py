"""Offline constant-product pool estimates, never observed or executable quotes.

This model deliberately does not claim Raydium on-chain fee or rounding parity.
The caller must supply audited effective reserves, decimals and fee parameters.
"""
from dataclasses import dataclass
from decimal import Decimal, localcontext


def _positive(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} inválido")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{label} inválido") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{label} precisa ser positivo e finito")
    return number


@dataclass(frozen=True)
class CPMMEstimate:
    source: str
    slot: int
    pool: str
    input_amount: Decimal
    estimated_output: Decimal
    average_execution_price: Decimal
    spot_price: Decimal
    price_impact_fraction: Decimal

    @property
    def is_observed_quote(self):
        return False


def estimate_exact_input(*, pool, slot, reserve_in, reserve_out,
                         amount_in, fee_bps):
    """Estimate output in human token units, with fee deducted from input.

    This is a generic x*y=k approximation, not a Raydium executable quote.
    No reserves, timestamps, provenance or fees are fetched by this function.
    """
    if not isinstance(pool, str) or not pool.strip():
        raise ValueError("identidade de pool obrigatória")
    if type(slot) is not int or slot < 0:
        raise ValueError("slot inválido")
    x = _positive(reserve_in, "reserve_in")
    y = _positive(reserve_out, "reserve_out")
    amount = _positive(amount_in, "amount_in")
    if isinstance(fee_bps, bool):
        raise ValueError("fee_bps inválido")
    try:
        fee = Decimal(str(fee_bps))
    except Exception as exc:
        raise ValueError("fee_bps inválido") from exc
    if not fee.is_finite() or not 0 <= fee < 10000:
        raise ValueError("fee_bps fora do intervalo")
    with localcontext() as ctx:
        ctx.prec = 60
        net = amount * (Decimal(1) - fee / Decimal(10000))
        output = y * net / (x + net)
        spot = y / x
        execution = output / amount
        impact = Decimal(1) - execution / spot
        return CPMMEstimate(
            "MODEL_ESTIMATE_NOT_OBSERVED", slot, pool, amount, output,
            execution, spot, impact,
        )
