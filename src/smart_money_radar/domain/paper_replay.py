"""Deterministic single-market paper trading on chronological observations."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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
    halted: bool = False
    market_at: datetime | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    quote_id: str | None = None

    def __post_init__(self) -> None:
        if self.at.utcoffset() is None:
            raise ValueError("observação exige horário com fuso")
        object.__setattr__(self, "at", self.at.astimezone(timezone.utc))
        if self.market_at is not None:
            if self.market_at.utcoffset() is None or self.market_at > self.at:
                raise ValueError("horário de mercado precisa ser conhecido na observação")
            object.__setattr__(self, "market_at", self.market_at.astimezone(timezone.utc))
        if not self.price.is_finite() or self.price <= 0:
            raise ValueError("preço da observação inválido")
        if not self.volume.is_finite() or self.volume < 0:
            raise ValueError("volume da observação inválido")
        if (self.signal not in {"BUY", "SELL", "NONE"}
                or type(self.entry_allowed) is not bool or type(self.halted) is not bool):
            raise ValueError("sinal ou filtro de entrada inválido")

        for value in (self.bid, self.ask):
            if value is not None and (not value.is_finite() or value <= 0):
                raise ValueError("cotação inválida")
        for value in (self.bid_size, self.ask_size):
            if value is not None and (not value.is_finite() or value < 0):
                raise ValueError("profundidade inválida")
        if (self.bid is None) != (self.ask is None) or (
            self.bid is not None and self.ask is not None and self.bid > self.ask
        ):
            raise ValueError("bid/ask incoerentes")


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
    quote_id: str | None = None
    market_at: datetime | None = None


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
    average_decision_to_market_seconds: Decimal | None
    average_market_to_availability_seconds: Decimal | None


def compare_paper_reports(immediate: PaperReport, confirmed: PaperReport) -> dict:
    """Compare mode outcomes on the shared replay inputs."""
    closed_trades = {
        "immediate": sum(fill.side == "SELL" for fill in immediate.fills),
        "confirmed": sum(fill.side == "SELL" for fill in confirmed.fills),
    }
    modes_with_closed_trades = sum(count > 0 for count in closed_trades.values())
    with localcontext() as context:
        context.prec = 40
        return {
            "basis": "confirmed_minus_immediate",
            "closed_trade_coverage": ("neither_mode", "one_mode", "both_modes")[modes_with_closed_trades],
            "equity_delta": confirmed.final_equity - immediate.final_equity,
            "realized_pnl_delta": confirmed.realized_pnl - immediate.realized_pnl,
            "fee_delta": confirmed.total_fees - immediate.total_fees,
            "drawdown_delta": confirmed.max_drawdown - immediate.max_drawdown,
            "rejected_entry_delta": confirmed.rejected_entries - immediate.rejected_entries,
            "closed_trades": closed_trades,
        }


@dataclass(frozen=True)
class PaperEntryCandidate:
    """Actual entry cost and state immediately before a simulated fill."""

    tick: ReplayTick
    decision_tick: ReplayTick
    price: Decimal
    budget: Decimal
    equity: Decimal
    day_start_equity: Decimal
    daily_realized_pnl: Decimal


@dataclass(frozen=True)
class _Order:
    side: Literal["BUY", "SELL"]
    signal: ReplayTick
    reason: str


def replay_paper(
    ticks: Iterable[ReplayTick], *, config: PaperConfig,
    mode: Literal["immediate", "confirmed"],
    entry_guard: Callable[[PaperEntryCandidate], str | None] | None = None,
) -> PaperReport:
    """Replay both modes with execution at a strictly later market observation."""
    if mode not in {"immediate", "confirmed"}:
        raise ValueError("modo de entrada inválido")
    with localcontext() as context:
        context.prec = 40
        return _replay(ticks, config, mode, entry_guard)


def _replay(
    ticks: Iterable[ReplayTick], config: PaperConfig, mode: str,
    entry_guard: Callable[[PaperEntryCandidate], str | None] | None,
) -> PaperReport:
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
    current_day: date | None = None
    day_start_equity = config.initial_cash
    day_start_realized_pnl = ZERO

    for tick in ticks:
        if prior is not None and tick.at <= prior:
            raise ValueError("observações devem estar em ordem estritamente crescente")
        prior = tick.at
        if tick.at.date() != current_day:
            current_day = tick.at.date()
            day_start_equity = equity
            day_start_realized_pnl = realized_pnl
        sell_price = (tick.bid or tick.price) * (ONE - slippage)

        market_at = tick.market_at or tick.at
        cancel_entry = pending is not None and pending.side == "BUY" and (
            tick.halted or not tick.entry_allowed or tick.signal == "SELL"
        )
        if pending is not None and (cancel_entry or (
            market_at > pending.signal.at and (
                pending.side == "BUY" or (
                    tick.volume > 0 and (tick.bid_size is None or tick.bid_size >= quantity)
                )
            )
        )):
            if pending.side == "SELL":
                fee = quantity * sell_price * fee_rate
                proceeds = quantity * sell_price - fee
                cash += proceeds
                realized_pnl += proceeds - entry_cost
                fills.append(PaperFill("SELL", pending.signal.at, tick.at, sell_price,
                                       quantity, fee, pending.reason, tick.quote_id, market_at))
                quantity = ZERO
                opened_at = None
            else:
                buy_price = (tick.ask or tick.price) * (ONE + slippage)
                entry_budget = min(config.max_entry_cash, cash * config.max_exposure)
                notional = entry_budget / (ONE + fee_rate)
                buy_quantity = notional / buy_price
                rejection = _entry_rejection(tick, pending, buy_price, config)
                if rejection is None and tick.ask_size is not None and buy_quantity > tick.ask_size:
                    rejection = "insufficient_ask_size"
                if rejection is None and entry_guard is not None:
                    rejection = entry_guard(PaperEntryCandidate(
                        tick, pending.signal, buy_price, entry_budget, cash, day_start_equity,
                        realized_pnl - day_start_realized_pnl,
                    ))
                if rejection is not None:
                    rejected_entries += 1
                    decisions.append(PaperDecision(tick.at, "reject", rejection))
                else:
                    entry_cost = entry_budget
                    fee = entry_cost - notional
                    quantity = buy_quantity
                    cash -= entry_cost
                    opened_at = tick.at
                    fills.append(PaperFill("BUY", pending.signal.at, tick.at, buy_price,
                                           quantity, fee, pending.reason, tick.quote_id, market_at))
            pending = None

        liquidation = quantity * sell_price * (ONE - fee_rate)
        equity = cash + liquidation
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)

        if pending is not None:
            continue
        if quantity:
            if tick.halted:
                pending = _Order("SELL", tick, "kill_switch")
            elif tick.signal == "SELL":
                pending = _Order("SELL", tick, "sell_signal")
            elif liquidation <= entry_cost * (ONE - config.stop_loss):
                pending = _Order("SELL", tick, "stop_loss")
            elif liquidation >= entry_cost * (ONE + config.take_profit):
                pending = _Order("SELL", tick, "take_profit")
            if pending is not None:
                decisions.append(PaperDecision(tick.at, "schedule_sell", pending.reason))
            continue
        if tick.halted or not tick.entry_allowed or tick.signal == "SELL" or tick.volume <= 0:
            if confirmation is not None or tick.signal == "BUY":
                rejected_entries += 1
                decisions.append(PaperDecision(tick.at, "reject", "kill_switch" if tick.halted else "entry_conditions"))
            confirmation = None
            continue
        if confirmation is not None:
            if market_at <= confirmation.at:
                continue
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

    market_delay = availability_delay = ZERO
    for fill in fills:
        market_at = fill.market_at or fill.filled_at
        market_delay += _seconds(market_at - fill.decision_at)
        availability_delay += _seconds(fill.filled_at - market_at)

    return PaperReport(
        tuple(fills), cash, quantity, equity, drawdown, opened_at,
        pending.side if pending is not None else None, rejected_entries,
        confirmation is not None, tuple(decisions), realized_pnl,
        sum((fill.fee for fill in fills), ZERO),
        (market_delay + availability_delay) / len(fills) if fills else None,
        market_delay / len(fills) if fills else None,
        availability_delay / len(fills) if fills else None,
    )


def _seconds(value: timedelta) -> Decimal:
    return Decimal(value.days * 86400 + value.seconds) + Decimal(value.microseconds) / Decimal(1_000_000)


def _entry_rejection(
    tick: ReplayTick, order: _Order, price: Decimal, config: PaperConfig,
) -> str | None:
    if tick.halted:
        return "kill_switch"
    if not tick.entry_allowed or tick.signal == "SELL" or tick.volume <= 0:
        return "entry_conditions_at_fill"
    maximum = config.max_entry_deviation_bps
    reference = order.signal.ask or order.signal.price
    if maximum is not None and (price - reference) * BPS > maximum * reference:
        return "entry_price_deviation"
    return None
