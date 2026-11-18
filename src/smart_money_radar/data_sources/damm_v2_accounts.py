"""Mapeamento estrito das contas de swap Meteora DAMM v2.

Ordem de contas baseada no IDL oficial cp_amm do SDK Meteora:
https://github.com/MeteoraAg/damm-v2-sdk/blob/main/src/idl/cp_amm.json

Este módulo não reconcilia transferências nem cria observações econômicas.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from smart_money_radar.data_sources.damm_v2_decoder import (
    METEORA_DAMM_V2_PROGRAM_ID,
    DammV2EvtSwap2,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    TOKEN_PROGRAM_IDS,
)


ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
SWAP_ACCOUNT_COUNT = 14


@dataclass(frozen=True)
class DammV2SwapAccounts:
    pool_authority: str
    pool: str
    input_token_account: str
    output_token_account: str
    token_a_vault: str
    token_b_vault: str
    token_a_mint: str
    token_b_mint: str
    payer: str
    token_a_program: str
    token_b_program: str
    referral_token_account: str
    event_authority: str
    program: str
    remaining_accounts: tuple[str, ...]
    input_vault: str
    output_vault: str
    input_mint: str
    output_mint: str
    input_token_program: str
    output_token_program: str


def _base58_encode(data: bytes) -> str:
    zeros = len(data) - len(data.lstrip(b"\\x00"))
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = ALPHABET[remainder] + encoded
    return "1" * zeros + encoded


def _resolve(value: Any, keys: list[str], field: str) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < len(keys):
        raise ValueError(f"{field} inválido")
    return keys[value]


def decode_damm_v2_swap_accounts(
    instruction: Mapping[str, Any],
    account_keys: list[str],
    event: DammV2EvtSwap2,
) -> DammV2SwapAccounts:
    """Resolve a lista de contas e orienta vault/mint/programa pelo evento.

    A direção do evento define qual vault A/B é input/output. Não usa payer
    como carteira monitorada. Exige pool do evento igual à conta pool da ix.
    """
    if not isinstance(instruction, Mapping):
        raise TypeError("instrução deve ser um mapeamento")
    if not isinstance(account_keys, list) or any(
        not isinstance(key, str) or not key for key in account_keys
    ):
        raise ValueError("account_keys inválidas")
    if not isinstance(event, DammV2EvtSwap2):
        raise TypeError("event deve ser DammV2EvtSwap2")
    if instruction.get("programId") not in (None, METEORA_DAMM_V2_PROGRAM_ID):
        raise ValueError("programa da instrução não é DAMM v2")
    accounts = instruction.get("accounts")
    if not isinstance(accounts, list) or len(accounts) < SWAP_ACCOUNT_COUNT:
        raise ValueError("swap DAMM v2 exige ao menos 14 contas")
    resolved = [
        _resolve(value, account_keys, f"accounts[{index}]")
        for index, value in enumerate(accounts)
    ]
    if resolved[13] != METEORA_DAMM_V2_PROGRAM_ID:
        raise ValueError("conta program não corresponde ao programa DAMM v2")
    if _base58_encode(event.pool) != resolved[1]:
        raise ValueError("pool do EvtSwap2 diverge da conta pool da instrução")
    if resolved[9] not in TOKEN_PROGRAM_IDS or resolved[10] not in TOKEN_PROGRAM_IDS:
        raise ValueError("token program A/B não reconhecido")

    if event.trade_direction == "A_TO_B":
        input_vault, output_vault = resolved[4], resolved[5]
        input_mint, output_mint = resolved[6], resolved[7]
        input_program, output_program = resolved[9], resolved[10]
    elif event.trade_direction == "B_TO_A":
        input_vault, output_vault = resolved[5], resolved[4]
        input_mint, output_mint = resolved[7], resolved[6]
        input_program, output_program = resolved[10], resolved[9]
    else:
        raise ValueError("direção DAMM v2 desconhecida")

    return DammV2SwapAccounts(
        pool_authority=resolved[0],
        pool=resolved[1],
        input_token_account=resolved[2],
        output_token_account=resolved[3],
        token_a_vault=resolved[4],
        token_b_vault=resolved[5],
        token_a_mint=resolved[6],
        token_b_mint=resolved[7],
        payer=resolved[8],
        token_a_program=resolved[9],
        token_b_program=resolved[10],
        referral_token_account=resolved[11],
        event_authority=resolved[12],
        program=resolved[13],
        remaining_accounts=tuple(resolved[14:]),
        input_vault=input_vault,
        output_vault=output_vault,
        input_mint=input_mint,
        output_mint=output_mint,
        input_token_program=input_program,
        output_token_program=output_program,
    )
