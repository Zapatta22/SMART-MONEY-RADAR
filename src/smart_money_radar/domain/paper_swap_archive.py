"""Translate first-seen archived swaps into chronological replay observations."""

from datetime import datetime
from decimal import Decimal, localcontext

from smart_money_radar.domain.paper_replay import ReplayTick


def ticks_from_swap_archive(
    rows: list[dict], *, quote_mint: str, min_confidence: Decimal,
) -> tuple[list[ReplayTick], list[str]]:
    """Use arrival time for decisions and omit stale or temporally ambiguous marks."""
    if not min_confidence.is_finite() or not 0 <= min_confidence <= 1:
        raise ValueError("confiança mínima precisa estar entre 0 e 1")
    result = []
    skipped = []
    latest_arrival = latest_event = None
    with localcontext() as context:
        context.prec = 40
        for row in rows:
            arrival = datetime.fromisoformat(row["available_at"])
            occurred = datetime.fromisoformat(row["occurred_at"])
            if (arrival.utcoffset() is None or occurred.utcoffset() is None
                    or occurred > arrival or (latest_arrival is not None and arrival <= latest_arrival)
                    or (latest_event is not None and occurred <= latest_event)):
                skipped.append(row["operation_id"])
                continue
            latest_arrival, latest_event = arrival, occurred
            buy = row["input_mint"] == quote_mint
            quantity_in, quantity_out = Decimal(row["input_amount"]), Decimal(row["output_amount"])
            if not all(value.is_finite() and value > 0 for value in (quantity_in, quantity_out)):
                raise ValueError("quantidades inválidas no arquivo de swaps")
            quote, base = (quantity_in, quantity_out) if buy else (quantity_out, quantity_in)
            expected_side = "BUY" if buy else "SELL"
            confidence = Decimal(row["confidence"])
            if not confidence.is_finite() or not 0 <= confidence <= 1:
                raise ValueError("confiança inválida no arquivo de swaps")
            side = expected_side if row["side"] == expected_side and confidence >= min_confidence else "NONE"
            result.append(ReplayTick(arrival, quote / base, quote, side, entry_allowed=True, market_at=occurred))
    return result, skipped
