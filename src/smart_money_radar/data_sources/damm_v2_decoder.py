"""Decodificação estrutural de instruções e Event CPI do Meteora DAMM v2.

Este módulo não reconstrói uma operação econômica nem produz SwapObservation.
Parâmetros e campos do evento são evidências do programa; transferências SPL/
Token-2022 e deltas de token accounts/vaults ainda precisam ser reconciliados.
Referência fixada: MeteoraAg/damm-v2@18936b18c26708f6e9b52cacc01ea2f99868ba8e.
"""
from dataclasses import dataclass
from typing import Literal


METEORA_DAMM_V2_PROGRAM_ID = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"
SOURCE_COMMIT = "18936b18c26708f6e9b52cacc01ea2f99868ba8e"

SWAP_DISCRIMINATOR = bytes.fromhex("f8c69e91e17587c8")
SWAP2_DISCRIMINATOR = bytes.fromhex("414b3f4ceb5b5b88")
EVENT_CPI_TAG = bytes.fromhex("e445a52e51cb9a1d")
EVT_SWAP2_DISCRIMINATOR = bytes.fromhex("bd4233a826507599")

SWAP_DATA_LENGTH = 24
SWAP2_DATA_LENGTH = 25
EVT_SWAP2_DATA_LENGTH = 196

SwapMode = Literal["EXACT_IN", "PARTIAL_FILL", "EXACT_OUT"]
TradeDirection = Literal["A_TO_B", "B_TO_A"]
CollectFeeMode = Literal["BOTH_TOKEN", "ONLY_B", "COMPOUNDING"]


@dataclass(frozen=True)
class DammV2SwapInstruction:
    instruction_name: Literal["swap", "swap2"]
    amount_0: int
    amount_1: int
    swap_mode: SwapMode
    legacy_exact_in: bool


@dataclass(frozen=True)
class DammV2SwapResult:
    included_fee_input_amount: int
    excluded_fee_input_amount: int
    amount_left: int
    output_amount: int
    next_sqrt_price: int
    claiming_fee: int
    protocol_fee: int
    compounding_fee: int
    referral_fee: int


@dataclass(frozen=True)
class DammV2EvtSwap2:
    pool: bytes
    trade_direction: TradeDirection
    collect_fee_mode: CollectFeeMode
    has_referral: bool
    amount_0: int
    amount_1: int
    swap_mode: SwapMode
    swap_result: DammV2SwapResult
    included_transfer_fee_amount_in: int
    included_transfer_fee_amount_out: int
    excluded_transfer_fee_amount_out: int
    current_timestamp: int
    reserve_a_amount: int
    reserve_b_amount: int


_SWAP_MODES: dict[int, SwapMode] = {
    0: "EXACT_IN",
    1: "PARTIAL_FILL",
    2: "EXACT_OUT",
}
_TRADE_DIRECTIONS: dict[int, TradeDirection] = {
    0: "A_TO_B",
    1: "B_TO_A",
}
_COLLECT_FEE_MODES: dict[int, CollectFeeMode] = {
    0: "BOTH_TOKEN",
    1: "ONLY_B",
    2: "COMPOUNDING",
}


def _read_uint(data: bytes, offset: int, size: int, field: str) -> int:
    end = offset + size
    if end > len(data):
        raise ValueError(f"dados truncados ao ler {field}")
    return int.from_bytes(data[offset:end], "little")


def decode_damm_v2_instruction(
    program_id: str, data: bytes
) -> DammV2SwapInstruction | None:
    """Decodifica somente swap e swap2 do programa DAMM v2.

    swap legado contém amount_in/minimum_amount_out e equivale a ExactIn.
    swap2 contém amount_0/amount_1/swap_mode; em ExactOut, amount_0 é output
    desejado e amount_1 é input máximo.
    """
    if program_id != METEORA_DAMM_V2_PROGRAM_ID:
        return None
    if not isinstance(data, bytes):
        raise TypeError("instruction data deve ser bytes")
    if len(data) < 8:
        raise ValueError("instruction data menor que o discriminador")
    discriminator = data[:8]
    if discriminator == SWAP_DISCRIMINATOR:
        if len(data) != SWAP_DATA_LENGTH:
            raise ValueError(f"swap exige {SWAP_DATA_LENGTH} bytes")
        amount_0 = _read_uint(data, 8, 8, "amount_in")
        amount_1 = _read_uint(data, 16, 8, "minimum_amount_out")
        mode: SwapMode = "EXACT_IN"
        name: Literal["swap", "swap2"] = "swap"
        legacy = True
    elif discriminator == SWAP2_DISCRIMINATOR:
        if len(data) != SWAP2_DATA_LENGTH:
            raise ValueError(f"swap2 exige {SWAP2_DATA_LENGTH} bytes")
        amount_0 = _read_uint(data, 8, 8, "amount_0")
        amount_1 = _read_uint(data, 16, 8, "amount_1")
        raw_mode = data[24]
        if raw_mode not in _SWAP_MODES:
            raise ValueError("swap2 contém swap_mode desconhecido")
        mode = _SWAP_MODES[raw_mode]
        name = "swap2"
        legacy = False
    else:
        return None
    if amount_0 == 0:
        raise ValueError("amount_0/amount_in deve ser maior que zero")
    return DammV2SwapInstruction(name, amount_0, amount_1, mode, legacy)


def decode_damm_v2_evt_swap2(
    program_id: str, data: bytes
) -> DammV2EvtSwap2 | None:
    """Decodifica EvtSwap2 dentro do wrapper Anchor Event CPI.

    Retorna None para outros programas, wrappers ou discriminadores. Não trata
    o evento como swap independente nem como prova de quantidades transferidas.
    """
    if program_id != METEORA_DAMM_V2_PROGRAM_ID:
        return None
    if not isinstance(data, bytes):
        raise TypeError("event CPI data deve ser bytes")
    if not data.startswith(EVENT_CPI_TAG):
        return None
    if len(data) < 16:
        raise ValueError("Event CPI truncado antes do discriminador")
    if data[8:16] != EVT_SWAP2_DISCRIMINATOR:
        return None
    if len(data) != EVT_SWAP2_DATA_LENGTH:
        raise ValueError(f"EvtSwap2 exige {EVT_SWAP2_DATA_LENGTH} bytes")

    offset = 16
    pool = data[offset:offset + 32]
    offset += 32

    direction_value = data[offset]
    offset += 1
    fee_mode_value = data[offset]
    offset += 1
    referral_value = data[offset]
    offset += 1
    if direction_value not in _TRADE_DIRECTIONS:
        raise ValueError("trade_direction desconhecido")
    if fee_mode_value not in _COLLECT_FEE_MODES:
        raise ValueError("collect_fee_mode desconhecido")
    if referral_value not in (0, 1):
        raise ValueError("has_referral não é booleano Borsh válido")

    amount_0 = _read_uint(data, offset, 8, "params.amount_0")
    offset += 8
    amount_1 = _read_uint(data, offset, 8, "params.amount_1")
    offset += 8
    mode_value = data[offset]
    offset += 1
    if mode_value not in _SWAP_MODES:
        raise ValueError("params.swap_mode desconhecido")

    included_fee_input = _read_uint(data, offset, 8, "included_fee_input_amount")
    offset += 8
    excluded_fee_input = _read_uint(data, offset, 8, "excluded_fee_input_amount")
    offset += 8
    amount_left = _read_uint(data, offset, 8, "amount_left")
    offset += 8
    output_amount = _read_uint(data, offset, 8, "output_amount")
    offset += 8
    next_sqrt_price = _read_uint(data, offset, 16, "next_sqrt_price")
    offset += 16
    claiming_fee = _read_uint(data, offset, 8, "claiming_fee")
    offset += 8
    protocol_fee = _read_uint(data, offset, 8, "protocol_fee")
    offset += 8
    compounding_fee = _read_uint(data, offset, 8, "compounding_fee")
    offset += 8
    referral_fee = _read_uint(data, offset, 8, "referral_fee")
    offset += 8

    included_transfer_fee_in = _read_uint(data, offset, 8, "included_transfer_fee_amount_in")
    offset += 8
    included_transfer_fee_out = _read_uint(data, offset, 8, "included_transfer_fee_amount_out")
    offset += 8
    excluded_transfer_fee_out = _read_uint(data, offset, 8, "excluded_transfer_fee_amount_out")
    offset += 8
    current_timestamp = _read_uint(data, offset, 8, "current_timestamp")
    offset += 8
    reserve_a = _read_uint(data, offset, 8, "reserve_a_amount")
    offset += 8
    reserve_b = _read_uint(data, offset, 8, "reserve_b_amount")
    offset += 8
    if offset != len(data):
        raise ValueError("comprimento residual inesperado em EvtSwap2")

    return DammV2EvtSwap2(
        pool=pool,
        trade_direction=_TRADE_DIRECTIONS[direction_value],
        collect_fee_mode=_COLLECT_FEE_MODES[fee_mode_value],
        has_referral=bool(referral_value),
        amount_0=amount_0,
        amount_1=amount_1,
        swap_mode=_SWAP_MODES[mode_value],
        swap_result=DammV2SwapResult(
            included_fee_input_amount=included_fee_input,
            excluded_fee_input_amount=excluded_fee_input,
            amount_left=amount_left,
            output_amount=output_amount,
            next_sqrt_price=next_sqrt_price,
            claiming_fee=claiming_fee,
            protocol_fee=protocol_fee,
            compounding_fee=compounding_fee,
            referral_fee=referral_fee,
        ),
        included_transfer_fee_amount_in=included_transfer_fee_in,
        included_transfer_fee_amount_out=included_transfer_fee_out,
        excluded_transfer_fee_amount_out=excluded_transfer_fee_out,
        current_timestamp=current_timestamp,
        reserve_a_amount=reserve_a,
        reserve_b_amount=reserve_b,
    )
