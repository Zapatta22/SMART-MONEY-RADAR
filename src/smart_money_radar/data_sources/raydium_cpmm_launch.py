"""Conservative offline evidence of standard Raydium CPMM pool initialization."""

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID,
    TOKEN_PROGRAM_IDS,
    SolanaInstructionRecord,
    _decode_base58,
    decode_solana_instruction_inventory,
)
from smart_money_radar.domain.cpmm_pool_config_envelope import CPMM_VAULT_AUTHORITY

# raydium-cp-swap 3d69122790e97cd6aff24e8ba95940793773f58c, Initialize.
INITIALIZE_DISCRIMINATOR = sha256(b"global:initialize").digest()[:8]
POOL_CREATION_FEE_ACCOUNT = "DNXgeM9EiiaAbaWvwjHj9fQQLAX5ZsfHyvmYUNRAdNC8"
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"
RENT_SYSVAR_ID = "SysvarRent111111111111111111111111111111111"


@dataclass(frozen=True)
class CpmmPoolInitialization:
    """A successful initialization instruction, not a current pool state."""

    signature: str
    slot: int
    instruction_index: int
    inner_instruction_index: int | None
    cpi_path: tuple[int, ...]
    pool: str
    creator: str
    configuration: str
    token_0_mint: str
    token_1_mint: str
    token_0_program: str
    token_1_program: str
    lp_mint: str
    token_0_vault: str
    token_1_vault: str
    observation_account: str
    requested_amount_0_raw: int
    requested_amount_1_raw: int
    requested_open_time: int


def _key(value: Any, length: int) -> bytes:
    if not isinstance(value, str) or not 1 <= len(value) <= (44 if length == 32 else 88):
        raise ValueError("identificação Base58 inválida")
    decoded = _decode_base58(value)
    if len(decoded) != length:
        raise ValueError("comprimento da identificação Base58 inválido")
    return decoded


def _decode_initialization(
    item: SolanaInstructionRecord, signature: str, slot: int,
) -> CpmmPoolInitialization:
    if item.accounts is None or len(item.accounts) < 20 or not item.cpi_path_valid:
        raise ValueError("contas ou caminho CPI da inicialização CPMM incompletos")
    data = item.data
    if data is None or len(data) != 32:
        raise ValueError("dados da inicialização CPMM incompatíveis")
    accounts = item.accounts
    decoded_keys = tuple(_key(value, 32) for value in accounts[:20])
    (creator, configuration, authority, pool, mint_0, mint_1, lp_mint,
     creator_token_0, creator_token_1, creator_lp_token, vault_0, vault_1,
     creation_fee, observation, lp_program, token_program_0, token_program_1,
     ata_program, system_program, rent) = accounts[:20]
    if (authority != CPMM_VAULT_AUTHORITY or creation_fee != POOL_CREATION_FEE_ACCOUNT
            or lp_program != SPL_TOKEN_PROGRAM_ID or token_program_0 not in TOKEN_PROGRAM_IDS
            or token_program_1 not in TOKEN_PROGRAM_IDS or ata_program != ASSOCIATED_TOKEN_PROGRAM_ID
            or system_program != SYSTEM_PROGRAM_ID or rent != RENT_SYSVAR_ID):
        raise ValueError("identidade de programas ou autoridades da inicialização CPMM diverge")
    if decoded_keys[4] >= decoded_keys[5]:
        raise ValueError("mints CPMM precisam estar ordenados e distintos")
    roles = (creator, configuration, authority, pool, mint_0, mint_1, lp_mint,
             creator_token_0, creator_token_1, creator_lp_token, vault_0, vault_1, creation_fee, observation)
    if len(set(roles)) != len(roles):
        raise ValueError("contas de inicialização CPMM reutilizadas em papéis distintos")
    amount_0, amount_1, requested_open_time = (
        int.from_bytes(data[offset:offset + 8], "little") for offset in (8, 16, 24)
    )
    if min(amount_0, amount_1) == 0:
        raise ValueError("quantidade inicial CPMM inválida")
    return CpmmPoolInitialization(
        signature, slot, item.instruction_index, item.inner_instruction_index, item.cpi_path,
        pool, creator, configuration, mint_0, mint_1, token_program_0, token_program_1,
        lp_mint, vault_0, vault_1, observation, amount_0, amount_1, requested_open_time,
    )


def detect_cpmm_pool_initializations(
    raw_transaction: dict[str, Any],
) -> tuple[CpmmPoolInitialization, ...]:
    """Extract positive evidence from a structurally complete, successful RPC transaction.

    This recognizes only the standard initialize instruction. Input is an
    archived RPC projection and does not authenticate its provider or commitment.
    """
    if not isinstance(raw_transaction, dict):
        raise TypeError("transação deve ser um objeto JSON")
    payload = raw_transaction.get("result", raw_transaction)
    if not isinstance(payload, dict) or "error" in raw_transaction:
        return ()
    meta = payload.get("meta")
    if not isinstance(meta, dict) or "err" not in meta or meta["err"] is not None:
        return ()
    inventory = decode_solana_instruction_inventory(raw_transaction)
    signature, slot = inventory.transaction_signature, inventory.slot
    if not inventory.complete or signature is None or slot is None or not 0 <= slot < 2**64:
        return ()
    candidates = []
    try:
        _key(signature, 64)
        for item in inventory.instructions:
            if item.program_id != RAYDIUM_CPMM_PROGRAM_ID:
                continue
            if item.data is None or len(item.data) < 8:
                return ()
            if item.data.startswith(INITIALIZE_DISCRIMINATOR):
                candidates.append(_decode_initialization(item, signature, slot))
    except ValueError:
        return ()
    return deduplicate_cpmm_pool_initializations(candidates)


def deduplicate_cpmm_pool_initializations(
    observations: Iterable[CpmmPoolInitialization],
) -> tuple[CpmmPoolInitialization, ...]:
    """Keep exact replays once and withhold pools with conflicting identities."""
    sources: dict[str, CpmmPoolInitialization] = {}
    conflicted: set[str] = set()
    for observation in observations:
        existing = sources.setdefault(observation.pool, observation)
        if existing != observation:
            conflicted.add(observation.pool)
    return tuple(item for pool, item in sources.items() if pool not in conflicted)
