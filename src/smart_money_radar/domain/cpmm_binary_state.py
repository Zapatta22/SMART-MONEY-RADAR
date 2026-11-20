"""Strict binary decoders for Raydium CPMM PoolState and AmmConfig.

Layouts follow raydium-io/raydium-cp-swap programs/cp-swap/src/states
(pool.rs and config.rs). This does not authenticate the RPC provider or PDAs.
"""
from dataclasses import dataclass
from hashlib import sha256

POOL_LENGTH = 637
CONFIG_LENGTH = 236
POOL_DISCRIMINATOR = sha256(b"account:PoolState").digest()[:8]
CONFIG_DISCRIMINATOR = sha256(b"account:AmmConfig").digest()[:8]
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _pubkey(raw):
    number = int.from_bytes(raw, "big")
    result = ""
    while number:
        number, digit = divmod(number, 58)
        result = ALPHABET[digit] + result
    return "1" * (len(raw) - len(raw.lstrip(bytes([0])))) + result


def _u64(raw, start):
    return int.from_bytes(raw[start:start + 8], "little")


@dataclass(frozen=True)
class PoolStateFields:
    amm_config: str
    token_0_vault: str
    token_1_vault: str
    token_0_mint: str
    token_1_mint: str
    token_0_program: str
    token_1_program: str
    observation_key: str
    status: int
    mint_0_decimals: int
    mint_1_decimals: int
    protocol_fees_token_0: int
    protocol_fees_token_1: int
    fund_fees_token_0: int
    fund_fees_token_1: int
    creator_fees_token_0: int
    creator_fees_token_1: int


@dataclass(frozen=True)
class AmmConfigFields:
    trade_fee_rate: int
    protocol_fee_rate: int
    fund_fee_rate: int
    creator_fee_rate: int
    disable_create_pool: bool


def decode_pool_state(raw: bytes) -> PoolStateFields:
    if not isinstance(raw, bytes) or len(raw) != POOL_LENGTH or raw[:8] != POOL_DISCRIMINATOR:
        raise ValueError("layout/discriminador PoolState inválido")
    keys = [_pubkey(raw[8 + 32*i:8 + 32*(i+1)]) for i in range(10)]
    status = raw[329]
    decimals0, decimals1 = raw[331], raw[332]
    if status & ~7 or decimals0 > 18 or decimals1 > 18:
        raise ValueError("status ou decimals PoolState inválidos")
    return PoolStateFields(
        amm_config=keys[0], token_0_vault=keys[2], token_1_vault=keys[3],
        token_0_mint=keys[5], token_1_mint=keys[6],
        token_0_program=keys[7], token_1_program=keys[8],
        observation_key=keys[9], status=status,
        mint_0_decimals=decimals0, mint_1_decimals=decimals1,
        protocol_fees_token_0=_u64(raw, 341),
        protocol_fees_token_1=_u64(raw, 349),
        fund_fees_token_0=_u64(raw, 357),
        fund_fees_token_1=_u64(raw, 365),
        creator_fees_token_0=_u64(raw, 397),
        creator_fees_token_1=_u64(raw, 405),
    )


def decode_amm_config(raw: bytes) -> AmmConfigFields:
    if not isinstance(raw, bytes) or len(raw) != CONFIG_LENGTH or raw[:8] != CONFIG_DISCRIMINATOR:
        raise ValueError("layout/discriminador AmmConfig inválido")
    if raw[9] not in (0, 1):
        raise ValueError("flag AmmConfig inválida")
    rates = [_u64(raw, offset) for offset in (12, 20, 28, 108)]
    if any(rate > 1_000_000 for rate in rates):
        raise ValueError("taxa CPMM fora do limite")
    return AmmConfigFields(rates[0], rates[1], rates[2], rates[3], bool(raw[9]))


def verify_pool_swap_identity(pool: PoolStateFields, config: AmmConfigFields,
                              *, amm_config: str, input_vault: str,
                              output_vault: str, input_mint: str,
                              output_mint: str, input_token_program: str,
                              output_token_program: str):
    """Bind decoded state to the swap's 13-account identity, both directions."""
    if not isinstance(pool, PoolStateFields) or not isinstance(config, AmmConfigFields):
        raise ValueError("estado CPMM não decodificado")
    if pool.amm_config != amm_config or pool.status & 4:
        raise ValueError("config divergente ou swap desabilitado")
    directions = (
        (pool.token_0_vault, pool.token_1_vault, pool.token_0_mint,
         pool.token_1_mint, pool.token_0_program, pool.token_1_program),
        (pool.token_1_vault, pool.token_0_vault, pool.token_1_mint,
         pool.token_0_mint, pool.token_1_program, pool.token_0_program),
    )
    supplied = (input_vault, output_vault, input_mint, output_mint,
                input_token_program, output_token_program)
    if supplied not in directions:
        raise ValueError("identidade vault/mint/program divergente")
    return True
