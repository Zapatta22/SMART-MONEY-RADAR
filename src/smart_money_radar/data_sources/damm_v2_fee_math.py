"""Aritmética pura de taxas usada pelo DAMM v2 e Token-2022.

Espelha somente operações inteiras verificadas nas fontes oficiais fixadas.
Não decodifica estado de mint, não escolhe epoch, não atribui transferências,
não reconcilia swaps e não produz contratos de domínio.

Meteora DAMM v2:
  18936b18c26708f6e9b52cacc01ea2f99868ba8e
Token-2022 interface:
  main em 2026-11-18; algoritmo TransferFee.calculate_fee /
  calculate_pre_fee_amount / calculate_inverse_fee.
"""
from dataclasses import dataclass
from typing import Literal

U64_MAX = (1 << 64) - 1
TOKEN_FEE_DENOMINATOR = 10_000
DAMM_FEE_DENOMINATOR = 1_000_000_000
CollectFeeMode = Literal["BOTH_TOKEN", "ONLY_B", "COMPOUNDING"]
TradeDirection = Literal["A_TO_B", "B_TO_A"]


@dataclass(frozen=True)
class TransferFeeResult:
    gross_amount: int
    fee_amount: int
    net_amount: int


@dataclass(frozen=True)
class AmmFeeSplit:
    total_fee: int
    claiming_fee: int
    compounding_fee: int
    protocol_fee: int
    referral_fee: int


@dataclass(frozen=True)
class DammFeeMode:
    fees_on_input: bool
    fees_on_token_a: bool
    has_referral: bool


def _u64(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= U64_MAX:
        raise ValueError(f"{field} deve ser u64")
    return value


def _ceil_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("denominador deve ser positivo")
    return (numerator + denominator - 1) // denominator


def calculate_transfer_fee(gross_amount: int, basis_points: int, maximum_fee: int) -> int:
    """Token-2022 TransferFee.calculate_fee: ceil e depois cap."""
    gross = _u64(gross_amount, "gross_amount")
    maximum = _u64(maximum_fee, "maximum_fee")
    if isinstance(basis_points, bool) or not isinstance(basis_points, int) or not 0 <= basis_points <= TOKEN_FEE_DENOMINATOR:
        raise ValueError("basis_points fora do intervalo 0..10000")
    if basis_points == 0 or gross == 0:
        return 0
    raw_fee = _ceil_div(gross * basis_points, TOKEN_FEE_DENOMINATOR)
    return min(raw_fee, maximum)


def transfer_fee_from_gross(gross_amount: int, basis_points: int, maximum_fee: int) -> TransferFeeResult:
    gross = _u64(gross_amount, "gross_amount")
    fee = calculate_transfer_fee(gross, basis_points, maximum_fee)
    return TransferFeeResult(gross, fee, gross - fee)


def transfer_fee_gross_for_net(net_amount: int, basis_points: int, maximum_fee: int) -> TransferFeeResult:
    """Token-2022 menor gross que produz o net; reproduz inverse-fee do DAMM."""
    net = _u64(net_amount, "net_amount")
    maximum = _u64(maximum_fee, "maximum_fee")
    if isinstance(basis_points, bool) or not isinstance(basis_points, int) or not 0 <= basis_points <= TOKEN_FEE_DENOMINATOR:
        raise ValueError("basis_points fora do intervalo 0..10000")
    if net == 0 or basis_points == 0:
        return TransferFeeResult(net, 0, net)

    if basis_points == TOKEN_FEE_DENOMINATOR:
        inverse_fee = maximum
    else:
        raw_gross = _ceil_div(net * TOKEN_FEE_DENOMINATOR, TOKEN_FEE_DENOMINATOR - basis_points)
        raw_inverse_fee = raw_gross - net
        inverse_fee = maximum if raw_inverse_fee >= maximum else raw_inverse_fee

    gross = net + inverse_fee
    if gross > U64_MAX:
        raise OverflowError("gross transfer amount excede u64")
    verified_fee = calculate_transfer_fee(gross, basis_points, maximum)
    if verified_fee != inverse_fee or gross - verified_fee != net:
        raise ArithmeticError("inversão da transfer fee não reproduz o net solicitado")
    return TransferFeeResult(gross, verified_fee, net)


def amm_fee_excluded_amount(included_amount: int, fee_numerator: int) -> tuple[int, int]:
    """PoolFeesStruct.get_excluded_fee_amount, arredondamento para cima."""
    included = _u64(included_amount, "included_amount")
    numerator = _u64(fee_numerator, "fee_numerator")
    if numerator > DAMM_FEE_DENOMINATOR:
        raise ValueError("fee_numerator não pode exceder FEE_DENOMINATOR")
    # O código Meteora permite 100% nesta direção: o líquido fica zero.
    fee = _ceil_div(included * numerator, DAMM_FEE_DENOMINATOR)
    if fee > included:
        raise ValueError("taxa AMM excede o montante incluído")
    return included - fee, fee


def amm_fee_included_amount(excluded_amount: int, fee_numerator: int) -> tuple[int, int]:
    """PoolFeesStruct.get_included_fee_amount, arredondamento para cima."""
    excluded = _u64(excluded_amount, "excluded_amount")
    numerator = _u64(fee_numerator, "fee_numerator")
    if numerator >= DAMM_FEE_DENOMINATOR:
        raise ValueError("fee_numerator deve ser menor que FEE_DENOMINATOR")
    if excluded == 0:
        return 0, 0
    included = _ceil_div(excluded * DAMM_FEE_DENOMINATOR, DAMM_FEE_DENOMINATOR - numerator)
    if included > U64_MAX:
        raise OverflowError("included AMM amount excede u64")
    return included, included - excluded


def split_amm_fee(
    fee_amount: int,
    protocol_fee_percent: int,
    referral_fee_percent: int,
    compounding_fee_bps: int,
    has_referral: bool,
) -> AmmFeeSplit:
    """PoolFeesStruct.split_fees; protocol no evento já vem líquido de referral."""
    fee = _u64(fee_amount, "fee_amount")
    for name, value, maximum in (
        ("protocol_fee_percent", protocol_fee_percent, 100),
        ("referral_fee_percent", referral_fee_percent, 100),
        ("compounding_fee_bps", compounding_fee_bps, 10_000),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
            raise ValueError(f"{name} inválido")
    if not isinstance(has_referral, bool):
        raise ValueError("has_referral deve ser booleano")

    protocol_gross = fee * protocol_fee_percent // 100
    lp_fee = fee - protocol_gross
    compounding = lp_fee * compounding_fee_bps // 10_000 if compounding_fee_bps else 0
    claiming = lp_fee - compounding
    referral = protocol_gross * referral_fee_percent // 100 if has_referral else 0
    protocol_net = protocol_gross - referral
    return AmmFeeSplit(fee, claiming, compounding, protocol_net, referral)


def resolve_damm_fee_mode(
    collect_fee_mode: CollectFeeMode,
    trade_direction: TradeDirection,
    has_referral: bool,
) -> DammFeeMode:
    """FeeMode::get_fee_mode para a matriz de modos suportados no código fixado."""
    if collect_fee_mode not in ("BOTH_TOKEN", "ONLY_B", "COMPOUNDING"):
        raise ValueError("collect_fee_mode desconhecido")
    if trade_direction not in ("A_TO_B", "B_TO_A"):
        raise ValueError("trade_direction desconhecida")
    if not isinstance(has_referral, bool):
        raise ValueError("has_referral deve ser booleano")

    matrix = {
        ("BOTH_TOKEN", "A_TO_B"): (False, False),
        ("BOTH_TOKEN", "B_TO_A"): (False, True),
        ("ONLY_B", "A_TO_B"): (False, False),
        ("ONLY_B", "B_TO_A"): (True, False),
        ("COMPOUNDING", "A_TO_B"): (False, False),
        ("COMPOUNDING", "B_TO_A"): (True, False),
    }
    fees_on_input, fees_on_token_a = matrix[(collect_fee_mode, trade_direction)]
    return DammFeeMode(fees_on_input, fees_on_token_a, has_referral)
