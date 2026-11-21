"""Controlled arithmetic only. No input flag can attest economic observations."""
from decimal import Decimal, localcontext
from datetime import datetime, timezone

def _decimal(v):
    if not isinstance(v,Decimal) or not v.is_finite() or v<0:
        raise ValueError("nonnegative finite Decimal required")
    return v

def _time(v):
    if not isinstance(v,datetime) or v.utcoffset() is None:
        raise ValueError("aware timestamp required")
    return v.astimezone(timezone.utc)

def controlled_valuation(*,quantity,cost,price,market_at,available_at,cutoff):
    """Synthetic calculation; not a verified price receipt."""
    market,available,end=map(_time,(market_at,available_at,cutoff))
    if not market<=available<=end<=datetime.now(timezone.utc):
        raise ValueError("future or inverted mark")
    with localcontext() as ctx:
        ctx.prec=100
        value=_decimal(quantity)*_decimal(price)
        return {"market_value":value,"unrealized_pnl":value-_decimal(cost),
                "quality":"CONTROLLED_MATH_ONLY","operational_authorized":False}

def controlled_drawdown(points, *, cutoff):
    """Max fractional peak-to-trough loss, on a controlled equity series."""
    end=_time(cutoff)
    if end>datetime.now(timezone.utc) or len(points)<2:
        raise ValueError("bounded equity series required")
    peak=Decimal(0); worst=Decimal(0); previous=None
    with localcontext() as ctx:
        ctx.prec=100
        for observed,available,equity in points:
            t,a=map(_time,(observed,available))
            if not t<=a<=end or (previous is not None and t<=previous):
                raise ValueError("future or ambiguous equity ordering")
            equity=_decimal(equity)
            peak=max(peak,equity)
            if peak:worst=max(worst,(peak-equity)/peak)
            previous=t
        if not peak:raise ValueError("undefined zero equity drawdown")
    return {"drawdown":worst,"quality":"CONTROLLED_MATH_ONLY","operational_authorized":False}
