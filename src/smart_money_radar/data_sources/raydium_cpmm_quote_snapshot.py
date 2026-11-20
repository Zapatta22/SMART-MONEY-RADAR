"""Model same-pool prices from a finalized, archived CPMM account snapshot."""

import base64
from dataclasses import dataclass
from decimal import Decimal, localcontext

from smart_money_radar.data_sources.geyser_proto_adapter import _base58_encode
from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID
from smart_money_radar.data_sources.solana_token_transfer_decoder import SPL_TOKEN_PROGRAM_ID

_POOL_DISCRIMINATOR = bytes.fromhex("f7ede3f5d7c3de46")
_CONFIG_DISCRIMINATOR = bytes.fromhex("daf42168cbcb2b6f")
_FEE_DENOMINATOR = 1_000_000


@dataclass(frozen=True)
class CpmmSnapshot:
    slot: int
    pool: str
    base_mint: str
    quote_mint: str
    base_reserve: int
    quote_reserve: int
    base_decimals: int
    quote_decimals: int
    trade_fee_rate: int


def _u64(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 8], "little")


def _key(data: bytes, offset: int) -> str:
    return _base58_encode(data[offset:offset + 32], field="conta do pool", expected_length=32)


def _account(value: dict, owner: str, size: int, discriminator: bytes = b"") -> bytes:
    if not isinstance(value, dict) or value.get("owner") != owner or value.get("executable") is not False:
        raise ValueError("owner ou tipo de conta CPMM inválido")
    encoded, encoding = value["data"]
    if encoding != "base64":
        raise ValueError("snapshot CPMM precisa de bytes base64")
    data = base64.b64decode(encoded, validate=True)
    if len(data) != size or not data.startswith(discriminator):
        raise ValueError("layout de conta CPMM incompatível")
    return data


def decode_cpmm_snapshot(
    request: dict, response: dict, *, base_mint: str, quote_mint: str, block_time: int,
) -> CpmmSnapshot:
    """Validate pool, configuration and vault linkage at one RPC context slot."""
    params = request.get("params")
    if (request.get("method") != "getMultipleAccounts" or not isinstance(params, list)
            or len(params) != 2 or not isinstance(params[1], dict)
            or params[1].get("commitment") != "finalized"
            or params[1].get("encoding") != "base64" or "dataSlice" in params[1]
            or request.get("id") != response.get("id")):
        raise ValueError("requisição CPMM não corresponde a uma leitura finalizada")
    addresses = params[0]
    result = response["result"]
    accounts = result["value"]
    slot = result["context"]["slot"]
    if (not isinstance(addresses, list) or len(addresses) != 4
            or not all(isinstance(item, str) and item for item in addresses)
            or len(set(addresses)) != 4 or not isinstance(accounts, list) or len(accounts) != 4
            or type(slot) is not int or slot < 0 or type(block_time) is not int or block_time < 0):
        raise ValueError("snapshot CPMM precisa de pool, configuração e dois vaults")
    pool, config, vault_a, vault_b = accounts
    state = _account(pool, RAYDIUM_CPMM_PROGRAM_ID, 637, _POOL_DISCRIMINATOR)
    configuration = _account(config, RAYDIUM_CPMM_PROGRAM_ID, 236, _CONFIG_DISCRIMINATOR)
    if addresses[1:] != [_key(state, offset) for offset in (8, 72, 104)]:
        raise ValueError("configuração e vaults não pertencem ao pool CPMM")
    if state[329] & 4 or block_time < _u64(state, 373):
        raise ValueError("pool CPMM fechado para swaps no snapshot")
    if state[390] != 0 or any(_key(state, offset) != SPL_TOKEN_PROGRAM_ID for offset in (232, 264)):
        raise ValueError("modelo disponível somente para SPL clássico com taxa do criador desabilitada")
    mints = (_key(state, 168), _key(state, 200))
    if base_mint == quote_mint or set(mints) != {base_mint, quote_mint}:
        raise ValueError("mints do snapshot divergem do mercado")
    reserves = []
    for index, vault in enumerate((vault_a, vault_b)):
        data = _account(vault, SPL_TOKEN_PROGRAM_ID, 165)
        reserve = _u64(data, 64) - sum(_u64(state, offset + 8 * index) for offset in (341, 357, 397))
        if _key(data, 0) != mints[index] or data[108] != 1 or reserve <= 0:
            raise ValueError("vault CPMM inválido ou sem liquidez")
        reserves.append(reserve)
    base = mints.index(base_mint)
    quote = 1 - base
    fee = _u64(configuration, 12)
    if fee >= _FEE_DENOMINATOR:
        raise ValueError("taxa CPMM inválida")
    return CpmmSnapshot(
        slot, addresses[0], base_mint, quote_mint, reserves[base], reserves[quote],
        state[331 + base], state[331 + quote], fee,
    )


def model_cpmm_quotes(snapshot: CpmmSnapshot, *, base_size_raw: int) -> dict[str, Decimal]:
    """Estimate fixed-size round-trip prices with integer fee rounding."""
    if type(base_size_raw) is not int or not 0 < base_size_raw < snapshot.base_reserve:
        raise ValueError("quantidade base fora da profundidade modelada")
    denominator = _FEE_DENOMINATOR
    kept = denominator - snapshot.trade_fee_rate
    net_base = base_size_raw * kept // denominator
    bid_quote = snapshot.quote_reserve * net_base // (snapshot.base_reserve + net_base)
    input_denominator = snapshot.base_reserve - base_size_raw
    net_quote = (snapshot.quote_reserve * base_size_raw + input_denominator - 1) // input_denominator
    ask_quote = (net_quote * denominator + kept - 1) // kept
    if bid_quote <= 0:
        raise ValueError("quantidade não produz cotação de venda positiva")
    with localcontext() as context:
        context.prec = 40
        size = Decimal(base_size_raw).scaleb(-snapshot.base_decimals)
        return {
            "bid": Decimal(bid_quote).scaleb(-snapshot.quote_decimals) / size,
            "ask": Decimal(ask_quote).scaleb(-snapshot.quote_decimals) / size,
            "base_size": size,
        }
