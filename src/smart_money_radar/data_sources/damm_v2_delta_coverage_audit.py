"""Critérios redigidos de cobertura dos quatro deltas de um swap DAMM v2.

Esta camada verifica presença, identidade de mint e sinais. Não reconcilia
quantidades econômicas nem atribui deltas agregados a operações por heurística.
"""
from typing import Any


def summarize_four_account_delta_coverage(accounts: Any, delta_result: Any) -> str:
    """Classifica somente cobertura/sinais; nunca promove a reconciliação econômica."""
    required = (
        accounts.input_token_account,
        accounts.input_vault,
        accounts.output_vault,
        accounts.output_token_account,
    )
    if len(set(required)) != 4:
        return "ACCOUNT_ROLE_COLLISION"
    if not delta_result.complete:
        return "SNAPSHOT_SET_INCOMPLETE"
    by_account = {item.token_account: item for item in delta_result.deltas}
    if any(key not in by_account for key in required):
        return "FOUR_ACCOUNT_DELTA_MISSING"
    input_user = by_account[accounts.input_token_account]
    input_vault = by_account[accounts.input_vault]
    output_vault = by_account[accounts.output_vault]
    output_user = by_account[accounts.output_token_account]
    if (
        input_user.mint != accounts.input_mint
        or input_vault.mint != accounts.input_mint
        or output_vault.mint != accounts.output_mint
        or output_user.mint != accounts.output_mint
    ):
        return "MINT_ROLE_MISMATCH"
    if (
        input_user.delta_raw >= 0
        or input_vault.delta_raw <= 0
        or output_vault.delta_raw >= 0
        or output_user.delta_raw <= 0
    ):
        return "DELTA_SIGN_MISMATCH"
    return "FOUR_ACCOUNT_DELTAS_PRESENT"
