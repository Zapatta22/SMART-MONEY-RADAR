"""Reconciliação conservadora entre swaps Raydium CPMM e evidências SPL.

Este módulo não usa argumentos de swap como quantidades executadas. Só retorna
MATCHED quando transferências, token accounts, mints, programas, CPI e deltas
por conta concordam sem reutilização ambígua de uma transferência.
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from smart_money_radar.data_sources.raydium_cpmm_analyzer import (
    RaydiumCpmmDecodedSwap,
)
from smart_money_radar.data_sources.solana_token_balance_deltas import (
    TokenAccountBalanceDelta,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SolanaTokenTransfer,
)


ReconciliationStatus = Literal["MATCHED", "AMBIGUOUS", "INCOMPLETE"]


@dataclass(frozen=True)
class RaydiumCpmmSwapReconciliation:
    swap: RaydiumCpmmDecodedSwap
    status: ReconciliationStatus
    reason: str
    wallet_address: str | None = None
    input_amount_raw: int | None = None
    output_amount_raw: int | None = None
    input_decimals: int | None = None
    output_decimals: int | None = None
    input_transfer: SolanaTokenTransfer | None = None
    output_transfer: SolanaTokenTransfer | None = None


def _transfer_key(transfer: SolanaTokenTransfer) -> tuple[int, int | None]:
    return transfer.instruction_index, transfer.inner_instruction_index


def _is_descendant(
    swap: RaydiumCpmmDecodedSwap,
    transfer: SolanaTokenTransfer,
) -> bool:
    if transfer.instruction_index != swap.instruction_index:
        return False
    if swap.inner_instruction_index is None:
        # The RPC innerInstructions group is scoped to this outer instruction.
        return transfer.inner_instruction_index is not None
    if (
        swap.stack_height is None
        or transfer.stack_height is None
        or transfer.inner_instruction_index is None
        or transfer.stack_height <= swap.stack_height
    ):
        return False
    return (
        len(transfer.cpi_path) > len(swap.cpi_path)
        and transfer.cpi_path[:len(swap.cpi_path)] == swap.cpi_path
    )


def _account_net_from_transfers(
    account: str,
    transfers: list[SolanaTokenTransfer],
) -> int:
    net = 0
    for transfer in transfers:
        if transfer.source_account == account:
            net -= transfer.amount_raw
        if transfer.destination_account == account:
            net += transfer.amount_raw
    return net


def _failure(
    swap: RaydiumCpmmDecodedSwap,
    status: ReconciliationStatus,
    reason: str,
) -> RaydiumCpmmSwapReconciliation:
    return RaydiumCpmmSwapReconciliation(
        swap=swap,
        status=status,
        reason=reason,
    )


def reconcile_raydium_cpmm_swaps(
    swaps: list[RaydiumCpmmDecodedSwap],
    transfers: list[SolanaTokenTransfer],
    balance_deltas: list[TokenAccountBalanceDelta],
    *,
    monitored_wallet: str,
) -> list[RaydiumCpmmSwapReconciliation]:
    """Reconcilia operações CPMM com transferências e deltas exatos por conta.

    Para swaps CPI, só considera transferências em descendentes demonstráveis
    pelo stackHeight/cpi_path. Para swaps externos, usa o grupo interno da
    instrução externa. A validação de saldo é agregada por token account sobre
    todas as transferências decodificadas da transação, permitindo várias
    operações sequenciais sem dividir um delta líquido arbitrariamente.
    """
    if not isinstance(monitored_wallet, str) or not monitored_wallet.strip():
        raise ValueError("monitored_wallet é obrigatório")
    if any(
        transfer.execution_status != "EXECUTED"
        or transfer.instruction_type not in {"TRANSFER", "TRANSFER_CHECKED"}
        for transfer in transfers
    ):
        return [
            _failure(
                swap, "INCOMPLETE",
                "Há transferência sem execução confirmada ou fora dos tipos base suportados."
            )
            for swap in swaps
        ]

    delta_by_account: dict[str, TokenAccountBalanceDelta] = {}
    for delta in balance_deltas:
        if delta.token_account in delta_by_account:
            raise ValueError("token account duplicada nos deltas")
        delta_by_account[delta.token_account] = delta

    outer_groups: dict[int, list[RaydiumCpmmDecodedSwap]] = defaultdict(list)
    for swap in swaps:
        outer_groups[swap.instruction_index].append(swap)

    provisional: list[RaydiumCpmmSwapReconciliation] = []
    claimed: dict[tuple[int, int | None], list[int]] = defaultdict(list)

    for swap_position, swap in enumerate(swaps):
        accounts = swap.accounts
        if swap.inner_instruction_index is None and any(
            other.inner_instruction_index is not None
            for other in outer_groups[swap.instruction_index]
        ):
            provisional.append(_failure(
                swap, "AMBIGUOUS",
                "Há outro swap CPMM aninhado no mesmo grupo da instrução externa."
            ))
            continue

        scoped = [item for item in transfers if _is_descendant(swap, item)]
        input_candidates = [
            item for item in scoped
            if item.source_account == accounts.input_token_account
            and item.destination_account == accounts.input_vault
        ]
        output_candidates = [
            item for item in scoped
            if item.source_account == accounts.output_vault
            and item.destination_account == accounts.output_token_account
        ]
        if len(input_candidates) != 1 or len(output_candidates) != 1:
            status: ReconciliationStatus = (
                "AMBIGUOUS"
                if len(input_candidates) > 1 or len(output_candidates) > 1
                else "INCOMPLETE"
            )
            provisional.append(_failure(
                swap, status,
                "Esperava exatamente uma transferência usuário→vault e uma vault→usuário; "
                f"encontradas {len(input_candidates)} e {len(output_candidates)}."
            ))
            continue

        input_transfer = input_candidates[0]
        output_transfer = output_candidates[0]
        if input_transfer.amount_raw <= 0 or output_transfer.amount_raw <= 0:
            provisional.append(_failure(
                swap, "INCOMPLETE", "Quantidade bruta de transferência não é positiva."
            ))
            continue
        if (
            input_transfer.program_id != accounts.input_token_program
            or output_transfer.program_id != accounts.output_token_program
        ):
            provisional.append(_failure(
                swap, "INCOMPLETE", "Programa SPL da transferência diverge do programa do lado do swap."
            ))
            continue

        input_delta = delta_by_account.get(accounts.input_token_account)
        output_delta = delta_by_account.get(accounts.output_token_account)
        if input_delta is None or output_delta is None:
            provisional.append(_failure(
                swap, "INCOMPLETE", "Falta delta pre/post de uma token account do usuário."
            ))
            continue
        if (
            input_delta.mint != accounts.input_token_mint
            or output_delta.mint != accounts.output_token_mint
        ):
            provisional.append(_failure(
                swap, "INCOMPLETE", "Mint do delta por conta diverge do mint declarado pelo swap."
            ))
            continue
        if (
            input_transfer.mint is not None
            and input_transfer.mint != input_delta.mint
        ) or (
            output_transfer.mint is not None
            and output_transfer.mint != output_delta.mint
        ):
            provisional.append(_failure(
                swap, "INCOMPLETE", "Mint explícito da transferência diverge do mint do token account."
            ))
            continue
        if (
            input_transfer.decimals is not None
            and input_transfer.decimals != input_delta.decimals
        ) or (
            output_transfer.decimals is not None
            and output_transfer.decimals != output_delta.decimals
        ):
            provisional.append(_failure(
                swap, "INCOMPLETE", "Decimals da transferência divergem dos metadados pre/post."
            ))
            continue

        owners = {input_delta.owner, output_delta.owner}
        if None in owners or len(owners) != 1 or input_delta.owner != monitored_wallet:
            provisional.append(_failure(
                swap, "INCOMPLETE",
                "Não foi possível provar que as duas token accounts pertencem à carteira monitorada."
            ))
            continue

        # Reconcile every decoded transfer affecting either user account against
        # the full transaction delta. This catches unrelated transfers, omitted
        # transfer variants, transfer fees, and netted activity not explained by
        # the decoded transfer evidence.
        for account, delta, expected_program in (
            (accounts.input_token_account, input_delta, accounts.input_token_program),
            (accounts.output_token_account, output_delta, accounts.output_token_program),
        ):
            account_transfers = [
                item for item in transfers
                if item.source_account == account or item.destination_account == account
            ]
            if any(
                item.program_id != expected_program
                or (item.mint is not None and item.mint != delta.mint)
                or (item.decimals is not None and item.decimals != delta.decimals)
                for item in account_transfers
            ):
                provisional.append(_failure(
                    swap, "INCOMPLETE",
                    "Programa, mint ou decimals de uma transferência na token account diverge da evidência de saldo."
                ))
                break
            if _account_net_from_transfers(account, account_transfers) != delta.delta_raw:
                provisional.append(_failure(
                    swap, "INCOMPLETE",
                    "Soma das transferências decodificadas não reconcilia com o delta pre/post da token account."
                ))
                break
        else:
            claimed[_transfer_key(input_transfer)].append(swap_position)
            claimed[_transfer_key(output_transfer)].append(swap_position)
            provisional.append(RaydiumCpmmSwapReconciliation(
                swap=swap,
                status="MATCHED",
                reason="Transferências, CPI, mints, programas, carteira e deltas por token account reconciliados.",
                wallet_address=monitored_wallet,
                input_amount_raw=input_transfer.amount_raw,
                output_amount_raw=output_transfer.amount_raw,
                input_decimals=input_delta.decimals,
                output_decimals=output_delta.decimals,
                input_transfer=input_transfer,
                output_transfer=output_transfer,
            ))

    # One transfer cannot be assigned to two distinct swap operations.
    reused_positions = {
        position
        for positions in claimed.values() if len(positions) > 1
        for position in positions
    }
    for position in reused_positions:
        prior = provisional[position]
        provisional[position] = _failure(
            prior.swap, "AMBIGUOUS",
            "Uma mesma instrução de transferência foi reivindicada por mais de um swap CPMM."
        )
    return provisional
