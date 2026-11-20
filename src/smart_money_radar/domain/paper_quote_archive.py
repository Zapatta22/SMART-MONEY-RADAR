"""Join archived swap signals to an independent, point-in-time quote stream."""

from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import Literal

from smart_money_radar.domain.paper_replay import ReplayTick


def ticks_from_quote_archive(
    quotes: list[dict], signals: list[ReplayTick], *, signal_ttl_seconds: int,
    as_of: datetime | None = None,
) -> tuple[list[ReplayTick], list[dict]]:
    """Consume actionable signals only after a newer market observation exists."""
    if type(signal_ttl_seconds) is not int or not 1 <= signal_ttl_seconds <= 86_400:
        raise ValueError("signal_ttl_seconds precisa estar entre 1 e 86400")
    ttl = timedelta(seconds=signal_ttl_seconds)
    candidates = iter(tick for tick in signals if tick.signal != "NONE")
    next_signal = next(candidates, None)
    pending: deque[ReplayTick] = deque()
    result = []
    selected = []
    previous_market = previous_arrival = None
    ids = set()
    with localcontext() as context:
        context.prec = 40
        for row in quotes:
            arrival = datetime.fromisoformat(row["available_at"])
            if arrival.utcoffset() is None:
                raise ValueError("cotação exige horário de disponibilidade com fuso")
            if as_of is not None and arrival > as_of:
                continue
            market_at = datetime.fromisoformat(row["market_at"])
            quote_id = row["quote_id"]
            if (not isinstance(quote_id, str) or not quote_id.strip() or quote_id in ids
                    or market_at.utcoffset() is None or market_at > arrival
                    or (previous_market is not None and market_at <= previous_market)
                    or (previous_arrival is not None and arrival <= previous_arrival)):
                raise ValueError("identidade ou ordem temporal de cotação inválida")
            ids.add(quote_id)
            previous_market, previous_arrival = market_at, arrival

            while next_signal is not None and next_signal.at <= arrival:
                pending.append(next_signal)
                next_signal = next(candidates, None)
            while pending and arrival - pending[0].at > ttl:
                pending.popleft()
            sides = set()
            while pending and pending[0].at < market_at:
                sides.add(pending.popleft().signal)
            side: Literal["BUY", "SELL", "NONE"] = (
                "SELL" if sides == {"SELL"} else "BUY" if sides == {"BUY"} else "NONE"
            )
            values = []
            for name in ("bid", "ask", "bid_size", "ask_size", "volume"):
                if isinstance(row[name], bool):
                    raise ValueError("valor numérico da cotação inválido")
                values.append(Decimal(row[name]))
            bid, ask, bid_size, ask_size, volume = values
            if not all(value.is_finite() for value in values):
                raise ValueError("cotação exige valores finitos")
            result.append(ReplayTick(
                arrival, (bid + ask) / 2, volume, side, entry_allowed=len(sides) < 2,
                market_at=market_at, bid=bid, ask=ask, bid_size=bid_size, ask_size=ask_size,
                quote_id=quote_id,
            ))
            selected.append(row)
    return result, selected
