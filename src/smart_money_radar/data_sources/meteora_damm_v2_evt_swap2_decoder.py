"""Strict offline decoder for Meteora DAMM v2 EvtSwap2 event-CPI data.

Schema pinned to MeteoraAg/damm-v2-sdk IDL commit
eab5e8aaa951418db43abbac471d9762b2005f11 (cp_amm IDL 0.2.5).
This module decodes bytes only; it does not associate CPI instructions,
reconcile token transfers, or classify a wallet trade.
"""
from dataclasses import dataclass


PROGRAM_ID = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"
IDL_REPOSITORY = "MeteoraAg/damm-v2-sdk"
IDL_COMMIT = "eab5e8aaa951418db43abbac471d9762b2005f11"
IDL_VERSION = "0.2.5"

ANCHOR_EVENT_DISCRIMINATOR = bytes((29, 154, 203, 81, 46, 165, 69, 228))
EVT_SWAP2_DISCRIMINATOR = bytes((189, 66, 51, 168, 38, 80, 117, 153))
EVENT_PREFIX_LENGTH = 16
EVT_SWAP2_BODY_LENGTH = 180
EVT_SWAP2_DATA_LENGTH = EVENT_PREFIX_LENGTH + EVT_SWAP2_BODY_LENGTH

TRADE_DIRECTIONS = {0, 1}
COLLECT_FEE_MODES = {0, 1, 2}
SWAP_MODES = {0, 1, 2}
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


@dataclass(frozen=True)
class MeteoraDammV2SwapEvent:
    pool: str
    trade_direction: int
    collect_fee_mode: int
    has_referral: bool
    amount_0: int
    amount_1: int
    swap_mode: int
    included_fee_input_amount: int
    excluded_fee_input_amount: int
    amount_left: int
    output_amount: int
    next_sqrt_price: int
    claiming_fee: int
    protocol_fee: int
    compounding_fee: int
    referral_fee: int
    included_transfer_fee_amount_in: int
    included_transfer_fee_amount_out: int
    excluded_transfer_fee_amount_out: int
    current_timestamp: int
    reserve_a_amount: int
    reserve_b_amount: int


def _read_uint(data: bytes, offset: int, size: int, field: str) -> int:
    end = offset + size
    if end > len(data):
        raise ValueError(f"campo {field} truncado")
    return int.from_bytes(data[offset:end], "little")


def _encode_base58(value: bytes) -> str:
    number = int.from_bytes(value, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = _BASE58_ALPHABET[remainder] + encoded
    leading_zeroes = len(value) - len(value.lstrip(b"\\x00"))
    return ("1" * leading_zeroes) + (encoded or ("" if leading_zeroes else "1"))


def decode_meteora_damm_v2_evt_swap2(data: bytes) -> MeteoraDammV2SwapEvent:
    """Decode the full Anchor event-CPI instruction data for EvtSwap2.

    The current pinned IDL uses claiming_fee + compounding_fee. Legacy
    partner_fee layouts are intentionally rejected by the exact-length check.
    """
    if not isinstance(data, bytes):
        raise TypeError("data deve ser bytes")
    if len(data) != EVT_SWAP2_DATA_LENGTH:
        raise ValueError(
            f"tamanho inválido de EvtSwap2: esperado {EVT_SWAP2_DATA_LENGTH}, recebido {len(data)}"
        )
    if data[:8] != ANCHOR_EVENT_DISCRIMINATOR:
        raise ValueError("Anchor event discriminator inválido")
    if data[8:16] != EVT_SWAP2_DISCRIMINATOR:
        raise ValueError("EvtSwap2 discriminator inválido")

    body = data[EVENT_PREFIX_LENGTH:]
    offset = 0
    pool_bytes = body[offset:offset + 32]
    offset += 32
    trade_direction = _read_uint(body, offset, 1, "trade_direction")
    offset += 1
    collect_fee_mode = _read_uint(body, offset, 1, "collect_fee_mode")
    offset += 1
    bool_value = _read_uint(body, offset, 1, "has_referral")
    offset += 1
    if bool_value not in (0, 1):
        raise ValueError("has_referral Borsh bool inválido")
    if trade_direction not in TRADE_DIRECTIONS:
        raise ValueError("trade_direction desconhecida")
    if collect_fee_mode not in COLLECT_FEE_MODES:
        raise ValueError("collect_fee_mode desconhecido")

    amount_0 = _read_uint(body, offset, 8, "params.amount_0")
    offset += 8
    amount_1 = _read_uint(body, offset, 8, "params.amount_1")
    offset += 8
    swap_mode = _read_uint(body, offset, 1, "params.swap_mode")
    offset += 1
    if swap_mode not in SWAP_MODES:
        raise ValueError("swap_mode desconhecido")

    values = {}
    for field in (
        "included_fee_input_amount",
        "excluded_fee_input_amount",
        "amount_left",
        "output_amount",
    ):
        values[field] = _read_uint(body, offset, 8, f"swap_result.{field}")
        offset += 8
    values["next_sqrt_price"] = _read_uint(body, offset, 16, "swap_result.next_sqrt_price")
    offset += 16
    for field in ("claiming_fee", "protocol_fee", "compounding_fee", "referral_fee"):
        values[field] = _read_uint(body, offset, 8, f"swap_result.{field}")
        offset += 8
    for field in (
        "included_transfer_fee_amount_in",
        "included_transfer_fee_amount_out",
        "excluded_transfer_fee_amount_out",
        "current_timestamp",
        "reserve_a_amount",
        "reserve_b_amount",
    ):
        values[field] = _read_uint(body, offset, 8, field)
        offset += 8

    if offset != EVT_SWAP2_BODY_LENGTH:
        raise ValueError("layout interno de EvtSwap2 inconsistente")

    return MeteoraDammV2SwapEvent(
        pool=_encode_base58(pool_bytes),
        trade_direction=trade_direction,
        collect_fee_mode=collect_fee_mode,
        has_referral=bool(bool_value),
        amount_0=amount_0,
        amount_1=amount_1,
        swap_mode=swap_mode,
        **values,
    )
