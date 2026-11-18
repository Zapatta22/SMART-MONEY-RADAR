"""Mapeamento dos 13 accounts-base do swap Raydium CPMM."""
from dataclasses import dataclass
from typing import Sequence


RAYDIUM_CPMM_SWAP_REQUIRED_ACCOUNTS = 13


@dataclass(frozen=True)
class RaydiumCpmmAccounts:
    payer: str
    authority: str
    amm_config: str
    pool_state: str
    input_token_account: str
    output_token_account: str
    input_vault: str
    output_vault: str
    input_token_program: str
    output_token_program: str
    input_token_mint: str
    output_token_mint: str
    observation_state: str
    remaining_accounts: tuple[str, ...] = ()


def decode_raydium_cpmm_accounts(
    account_keys: Sequence[str],
) -> RaydiumCpmmAccounts:
    """Decodifica 13 contas obrigatórias e preserva todas as contas adicionais."""

    if not isinstance(account_keys, (list, tuple)):
        raise TypeError("account_keys deve ser list ou tuple")

    if len(account_keys) < RAYDIUM_CPMM_SWAP_REQUIRED_ACCOUNTS:
        raise ValueError(
            "swap CPMM exige pelo menos 13 contas; "
            f"recebidas {len(account_keys)}"
        )

    if any(not isinstance(key, str) or not key for key in account_keys):
        raise ValueError("todas as contas devem ser strings não vazias")

    required = account_keys[:RAYDIUM_CPMM_SWAP_REQUIRED_ACCOUNTS]
    remaining = tuple(account_keys[RAYDIUM_CPMM_SWAP_REQUIRED_ACCOUNTS:])

    return RaydiumCpmmAccounts(
        payer=required[0],
        authority=required[1],
        amm_config=required[2],
        pool_state=required[3],
        input_token_account=required[4],
        output_token_account=required[5],
        input_vault=required[6],
        output_vault=required[7],
        input_token_program=required[8],
        output_token_program=required[9],
        input_token_mint=required[10],
        output_token_mint=required[11],
        observation_state=required[12],
        remaining_accounts=remaining,
    )
