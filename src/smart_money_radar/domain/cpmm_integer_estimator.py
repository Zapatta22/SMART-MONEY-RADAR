"""Offline Raydium CPMM curve arithmetic in raw token units.

Reserves are effective reserves ordered by swap direction. Amounts are at the
curve boundary, excluding token transfer fees and transaction costs.
"""

from dataclasses import dataclass

FEE_RATE_DENOMINATOR = 1_000_000
_U64_MAX = (1 << 64) - 1


@dataclass(frozen=True)
class CPMMIntegerEstimate:
    input_amount: int
    output_amount: int
    trade_fee: int
    creator_fee: int
    protocol_fee: int
    fund_fee: int
    creator_fee_on_input: bool
    new_input_vault_amount: int
    new_output_vault_amount: int


@dataclass(frozen=True)
class CPMMFeeRates:
    trade_fee_rate: int
    creator_fee_rate: int
    protocol_fee_rate: int
    fund_fee_rate: int
    creator_fee_on_input: bool

    def __post_init__(self) -> None:
        if type(self.creator_fee_on_input) is not bool:
            raise ValueError("creator_fee_on_input must be a bool")
        for name in ("trade_fee_rate", "creator_fee_rate", "protocol_fee_rate", "fund_fee_rate"):
            rate = getattr(self, name)
            if type(rate) is not int or not 0 <= rate <= FEE_RATE_DENOMINATOR:
                raise ValueError(f"{name} must be an integer fee rate in millionths")
        if self.input_rate >= FEE_RATE_DENOMINATOR or self.creator_fee_rate == FEE_RATE_DENOMINATOR:
            raise ValueError("swap fee rate must be below 100%")
        if self.protocol_fee_rate + self.fund_fee_rate > FEE_RATE_DENOMINATOR:
            raise ValueError("protocol and fund shares exceed the trade fee")
        if self.creator_fee_on_input and self.input_rate == 0:
            raise ValueError("Raydium cannot split a combined fee with zero total rate")

    @property
    def input_rate(self) -> int:
        return self.trade_fee_rate + (self.creator_fee_rate if self.creator_fee_on_input else 0)


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


def _validate_amounts(**amounts: int) -> None:
    for name, amount in amounts.items():
        if type(amount) is not int or not 0 < amount <= _U64_MAX:
            raise ValueError(f"{name} must be a positive u64")


def _result(
    *,
    reserve_in: int,
    reserve_out: int,
    amount_in: int,
    amount_out: int,
    curve_input: int,
    curve_output: int,
    fees: CPMMFeeRates,
) -> CPMMIntegerEstimate:
    input_fee = amount_in - curve_input
    if fees.creator_fee_on_input:
        creator_fee = input_fee * fees.creator_fee_rate // fees.input_rate
        trade_fee = input_fee - creator_fee
    else:
        creator_fee = curve_output - amount_out
        trade_fee = input_fee
    return CPMMIntegerEstimate(
        input_amount=amount_in,
        output_amount=amount_out,
        trade_fee=trade_fee,
        creator_fee=creator_fee,
        protocol_fee=trade_fee * fees.protocol_fee_rate // FEE_RATE_DENOMINATOR,
        fund_fee=trade_fee * fees.fund_fee_rate // FEE_RATE_DENOMINATOR,
        creator_fee_on_input=fees.creator_fee_on_input,
        new_input_vault_amount=reserve_in + curve_input,
        new_output_vault_amount=reserve_out - curve_output,
    )


def estimate_exact_input(
    *, reserve_in: int, reserve_out: int, amount_in: int, fees: CPMMFeeRates,
) -> CPMMIntegerEstimate:
    """Return the curve result for a fixed input, including possible zero output."""
    _validate_amounts(reserve_in=reserve_in, reserve_out=reserve_out, amount_in=amount_in)
    curve_input = amount_in - _ceil_div(amount_in * fees.input_rate, FEE_RATE_DENOMINATOR)
    curve_output = curve_input * reserve_out // (reserve_in + curve_input)
    amount_out = curve_output
    if not fees.creator_fee_on_input:
        amount_out -= _ceil_div(curve_output * fees.creator_fee_rate, FEE_RATE_DENOMINATOR)
    return _result(
        reserve_in=reserve_in, reserve_out=reserve_out, amount_in=amount_in,
        amount_out=amount_out, curve_input=curve_input, curve_output=curve_output, fees=fees,
    )


def estimate_exact_output(
    *, reserve_in: int, reserve_out: int, amount_out: int, fees: CPMMFeeRates,
) -> CPMMIntegerEstimate:
    """Return the input required for a fixed output after any CPMM creator fee."""
    _validate_amounts(reserve_in=reserve_in, reserve_out=reserve_out, amount_out=amount_out)
    curve_output = amount_out
    if not fees.creator_fee_on_input:
        curve_output = _ceil_div(
            amount_out * FEE_RATE_DENOMINATOR, FEE_RATE_DENOMINATOR - fees.creator_fee_rate,
        )
    if curve_output >= reserve_out:
        raise ValueError("gross output must be below the output reserve")
    curve_input = _ceil_div(reserve_in * curve_output, reserve_out - curve_output)
    amount_in = _ceil_div(
        curve_input * FEE_RATE_DENOMINATOR, FEE_RATE_DENOMINATOR - fees.input_rate,
    )
    _validate_amounts(amount_in=amount_in)
    return _result(
        reserve_in=reserve_in, reserve_out=reserve_out, amount_in=amount_in,
        amount_out=amount_out, curve_input=curve_input, curve_output=curve_output, fees=fees,
    )
