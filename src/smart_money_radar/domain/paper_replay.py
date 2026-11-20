"""Deterministic single-market paper trading on chronological observations."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Literal

ZERO = Decimal(0)
ONE = Decimal(1)
BPS = Decimal(10_000)


@dataclass(frozen=True)
class ReplayTick:
    at: datetime
    price: Decimal
    volume: Decimal
    signal: Literal["BUY", "SELL", "NONE"] = "NONE"
    entry_allowed: bool = False

    def __post_init__(self) -> None:
        if self.at.utcoffset() is None:
            raise ValueError("observação exige horário com fuso")
        if not self.price.is_finite() or self.price <= 0:
            raise ValueError("preço da observação inválido")
        if not self.volume.is_finite() or self.volume < 0:
            raise ValueError("volume da observação inválido")
        if self.signal not in {"BUY", "SELL", "NONE"} or type(self.entry_allowed) is not bool:
            raise ValueError("sinal ou filtro de entrada inválido")


@dataclass(frozen=True)
class PaperConfig:
    initial_cash: Decimal
    max_entry_cash: Decimal
    max_exposure: Decimal
    fee_bps: Decimal = ZERO
    slippage_bps: Decimal = ZERO
    stop_loss: Decimal = Decimal("0.10")
    take_profit: Decimal = Decimal("0.20")
    max_entry_deviation_bps: Decimal | None = None

    def __post_init__(self) -> None:
        fields = (
            self.initial_cash, self.max_entry_cash, self.max_exposure, self.fee_bps,
            self.slippage_bps, self.stop_loss, self.take_profit,
        )
        if not all(value.is_finite() for value in fields):
            raise ValueError("configuração da simulação exige valores finitos")
        if self.initial_cash <= 0 or self.max_entry_cash <= 0 or not ZERO < self.max_exposure <= ONE:
            raise ValueError("caixa ou exposição inválidos")
        if not ZERO <= self.fee_bps < BPS or not ZERO <= self.slippage_bps < BPS:
            raise ValueError("taxa ou slippage em bps inválido")
        deviation = self.max_entry_deviation_bps
        if deviation is not None and (not deviation.is_finite() or deviation < 0):
            raise ValueError("desvio máximo de entrada inválido")
        if not ZERO < self.stop_loss < ONE or self.take_profit <= 0:
            raise ValueError("limites de saída inválidos")


@dataclass(frozen=True)
class PaperFill:
    side: Literal["BUY", "SELL"]
    decision_at: datetime
    filled_at: datetime
    price: Decimal
    quantity: Decimal
    fee: Decimal
    reason: str


@dataclass(frozen=True)
class PaperDecision:
    at: datetime
    action: str
    reason: str


@dataclass(frozen=True)
class PaperReport:
    fills: tuple[PaperFill, ...]
    cash: Decimal
    open_quantity: Decimal
    final_equity: Decimal
    max_drawdown: Decimal
    position_opened_at: datetime | None
    pending_side: Literal["BUY", "SELL"] | None
    rejected_entries: int
    awaiting_confirmation: bool
    decisions: tuple[PaperDecision, ...]
    realized_pnl: Decimal
    total_fees: Decimal
    average_fill_delay_seconds: Decimal | None


@dataclass(frozen=True)
class _Order:
    side: Literal["BUY", "SELL"]
    signal: ReplayTick
    reason: str


def replay_paper(
    ticks: Iterable[ReplayTick], *, config: PaperConfig,
    mode: Literal["immediate", "confirmed"],
) -> PaperReport:
    """Replay both modes with execution at a strictly later market observation."""
    if mode not in {"immediate", "confirmed"}:
        raise ValueError("modo de entrada inválido")
    with localcontext() as context:
        context.prec = 40
        return _replay(ticks, config, mode)


def _replay(ticks: Iterable[ReplayTick], config: PaperConfig, mode: str) -> PaperReport:
    fee_rate = config.fee_bps / BPS
    slippage = config.slippage_bps / BPS
    cash = equity = peak = config.initial_cash
    quantity = drawdown = ZERO
    entry_cost = ZERO
    pending: _Order | None = None
    confirmation: ReplayTick | None = None
    prior: datetime | None = None
    opened_at: datetime | None = None
    fills: list[PaperFill] = []
    rejected_entries = 0
    decisions: list[PaperDecision] = []
    realized_pnl = ZERO

    for tick in ticks:
        if prior is not None and tick.at <= prior:
            raise ValueError("observações devem estar em ordem estritamente crescente")
        prior = tick.at
        sell_price = tick.price * (ONE - slippage)

        if pending is not None and (pending.side == "BUY" or tick.volume > 0):
            if pending.side == "SELL":
                fee = quantity * sell_price * fee_rate
                proceeds = quantity * sell_price - fee
                cash += proceeds
                realized_pnl += proceeds - entry_cost
                fills.append(PaperFill("SELL", pending.signal.at, tick.at, sell_price,
                                       quantity, fee, pending.reason))
                quantity = ZERO
                opened_at = None
            else:
                buy_price = tick.price * (ONE + slippage)
                rejection = _entry_rejection(tick, pending, buy_price, config)
                if rejection is not None:
                    rejected_entries += 1
                    decisions.append(PaperDecision(tick.at, "reject", rejection))
                else:
                    entry_cost = min(config.max_entry_cash, cash * config.max_exposure)
                    notional = entry_cost / (ONE + fee_rate)
                    fee = entry_cost - notional
                    quantity = notional / buy_price
                    cash -= entry_cost
                    opened_at = tick.at
                    fills.append(PaperFill("BUY", pending.signal.at, tick.at, buy_price,
                                           quantity, fee, pending.reason))
            pending = None

        liquidation = quantity * sell_price * (ONE - fee_rate)
        equity = cash + liquidation
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)

        if pending is not None:
            continue
        if quantity:
            if tick.signal == "SELL":
                pending = _Order("SELL", tick, "sell_signal")
            elif liquidation <= entry_cost * (ONE - config.stop_loss):
                pending = _Order("SELL", tick, "stop_loss")
            elif liquidation >= entry_cost * (ONE + config.take_profit):
                pending = _Order("SELL", tick, "take_profit")
            if pending is not None:
                decisions.append(PaperDecision(tick.at, "schedule_sell", pending.reason))
            continue
        if not tick.entry_allowed or tick.signal == "SELL" or tick.volume <= 0:
            if confirmation is not None or tick.signal == "BUY":
                rejected_entries += 1
                decisions.append(PaperDecision(tick.at, "reject", "entry_conditions"))
            confirmation = None
            continue
        if confirmation is not None:
            if tick.price > confirmation.price and tick.volume > confirmation.volume:
                pending = _Order("BUY", tick, "confirmed_signal")
                decisions.append(PaperDecision(tick.at, "schedule_buy", pending.reason))
                confirmation = None
                continue
            rejected_entries += 1
            decisions.append(PaperDecision(tick.at, "reject", "confirmation_not_met"))
            confirmation = None
        if tick.signal == "BUY":
            if mode == "immediate":
                pending = _Order("BUY", tick, "immediate_signal")
                decisions.append(PaperDecision(tick.at, "schedule_buy", pending.reason))
            else:
                confirmation = tick
                decisions.append(PaperDecision(tick.at, "await_confirmation", "buy_signal"))

    delay = ZERO
    for fill in fills:
        elapsed = fill.filled_at - fill.decision_at
        delay += Decimal(elapsed.days * 86400 + elapsed.seconds)
        delay += Decimal(elapsed.microseconds) / Decimal(1_000_000)
    return PaperReport(
        tuple(fills), cash, quantity, equity, drawdown, opened_at,
        pending.side if pending is not None else None, rejected_entries,
        confirmation is not None, tuple(decisions), realized_pnl,
        sum((fill.fee for fill in fills), ZERO), delay / len(fills) if fills else None,
    )


def _entry_rejection(
    tick: ReplayTick, order: _Order, price: Decimal, config: PaperConfig,
) -> str | None:
    if not tick.entry_allowed or tick.signal == "SELL" or tick.volume <= 0:
        return "entry_conditions_at_fill"
    maximum = config.max_entry_deviation_bps
    if maximum is not None and (price - order.signal.price) * BPS > maximum * order.signal.price:
        return "entry_price_deviation"
    return None
