"""Atribuição conservadora de transferências SPL a swaps DAMM v2.

Este módulo atribui instruções Transfer/TransferChecked aos papéis de input e
output de uma operação já associada a EvtSwap2. Atribuição não equivale a
reconciliação econômica: valores, deltas de token accounts/vaults e taxas
Token-2022 precisam de validação independente.
"""
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from smart_money_radar.data_sources.damm_v2_accounts import DammV2SwapAccounts
from smart_money_radar.data_sources.damm_v2_analyzer import (
    DammV2SwapEventAssociation,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    TOKEN_2022_PROGRAM_ID,
    SolanaTokenTransfer,
)


TransferEvidenceStatus = Literal[
    "ATTRIBUTED",
    "TRANSFER_MISSING",
    "AMBIGUOUS",
    "INCOMPLETE",
    "ASSOCIATION_UNRESOLVED",
]


@dataclass(frozen=True)
class DammV2SwapTransferContext:
    association: DammV2SwapEventAssociation
    accounts: DammV2SwapAccounts


@dataclass(frozen=True)
class DammV2TransferEvidence:
    status: TransferEvidenceStatus
    instruction_index: int | None
    inner_instruction_index: int | None
    cpi_path: tuple[int, ...] | None
    input_transfer: SolanaTokenTransfer | None
    output_transfer: SolanaTokenTransfer | None
    reason: str
    transfer_fee_review_required: bool


def _is_descendant_transfer(
    transfer: SolanaTokenTransfer,
    association: DammV2SwapEventAssociation,
) -> bool:
    if (
        association.instruction_index != transfer.instruction_index
        or association.stack_height is None
        or transfer.stack_height is None
        or association.cpi_path is None
        or transfer.stack_height <= association.stack_height
        or transfer.inner_instruction_index is None
        or association.event_inner_instruction_index is None
        or transfer.inner_instruction_index >= association.event_inner_instruction_index
        or len(transfer.cpi_path) <= len(association.cpi_path)
    ):
        return False
    return transfer.cpi_path[: len(association.cpi_path)] == association.cpi_path


def analyze_damm_v2_transfer_evidence(
    contexts: Sequence[DammV2SwapTransferContext],
    transfers: Sequence[SolanaTokenTransfer],
) -> list[DammV2TransferEvidence]:
    """Atribui no máximo um transfer de entrada e um de saída por swap.

    Requer correspondência estrutural swap↔EvtSwap2 e descendência CPI
    demonstrável. Exige mint e decimals explícitos em TransferChecked; o
    opcode Transfer sem mint/decimals permanece INCOMPLETE. Nenhuma quantidade
    é promovida a SwapObservation ou considerada economicamente reconciliada.
    """
    if not isinstance(contexts, Sequence) or isinstance(contexts, (str, bytes)):
        raise TypeError("contexts deve ser uma sequência")
    if not isinstance(transfers, Sequence) or isinstance(transfers, (str, bytes)):
        raise TypeError("transfers deve ser uma sequência")
    for context in contexts:
        if not isinstance(context, DammV2SwapTransferContext):
            raise TypeError("contexto DAMM v2 inválido")
    for transfer in transfers:
        if not isinstance(transfer, SolanaTokenTransfer):
            raise TypeError("transferência SPL inválida")

    candidates: list[dict[str, list[int]]] = []
    transfer_owners: dict[int, list[tuple[int, str]]] = defaultdict(list)

    for context_index, context in enumerate(contexts):
        association = context.association
        accounts = context.accounts
        if association.status != "MATCHED":
            candidates.append({"input": [], "output": []})
            continue
        selected = {"input": [], "output": []}
        for transfer_index, transfer in enumerate(transfers):
            if transfer.execution_status != "EXECUTED":
                continue
            if not _is_descendant_transfer(transfer, association):
                continue
            if (
                transfer.source_account == accounts.input_token_account
                and transfer.destination_account == accounts.input_vault
            ):
                selected["input"].append(transfer_index)
            if (
                transfer.source_account == accounts.output_vault
                and transfer.destination_account == accounts.output_token_account
            ):
                selected["output"].append(transfer_index)
        candidates.append(selected)
        for role, indexes in selected.items():
            for transfer_index in indexes:
                transfer_owners[transfer_index].append((context_index, role))

    results: list[DammV2TransferEvidence] = []
    for context_index, context in enumerate(contexts):
        association = context.association
        accounts = context.accounts
        base = dict(
            instruction_index=association.instruction_index,
            inner_instruction_index=association.inner_instruction_index,
            cpi_path=association.cpi_path,
        )
        if association.status != "MATCHED":
            results.append(DammV2TransferEvidence(
                status="ASSOCIATION_UNRESOLVED",
                input_transfer=None,
                output_transfer=None,
                reason="swap e EvtSwap2 não possuem associação estrutural única",
                transfer_fee_review_required=True,
                **base,
            ))
            continue

        selected = candidates[context_index]
        if any(len(selected[role]) > 1 for role in ("input", "output")):
            results.append(DammV2TransferEvidence(
                status="AMBIGUOUS",
                input_transfer=None,
                output_transfer=None,
                reason="mais de uma transferência candidata para o mesmo papel",
                transfer_fee_review_required=True,
                **base,
            ))
            continue
        if not selected["input"] or not selected["output"]:
            results.append(DammV2TransferEvidence(
                status="TRANSFER_MISSING",
                input_transfer=transfers[selected["input"][0]] if selected["input"] else None,
                output_transfer=transfers[selected["output"][0]] if selected["output"] else None,
                reason="transferência de entrada ou saída não foi identificada univocamente",
                transfer_fee_review_required=True,
                **base,
            ))
            continue

        input_index = selected["input"][0]
        output_index = selected["output"][0]
        if (
            len(transfer_owners[input_index]) != 1
            or len(transfer_owners[output_index]) != 1
            or input_index == output_index
        ):
            results.append(DammV2TransferEvidence(
                status="AMBIGUOUS",
                input_transfer=None,
                output_transfer=None,
                reason="uma transferência candidata foi reutilizada por mais de uma operação/papel",
                transfer_fee_review_required=True,
                **base,
            ))
            continue

        input_transfer = transfers[input_index]
        output_transfer = transfers[output_index]
        expected = (
            (input_transfer, accounts.input_mint, accounts.input_token_program),
            (output_transfer, accounts.output_mint, accounts.output_token_program),
        )
        invalid = []
        for transfer, expected_mint, expected_program in expected:
            if transfer.program_id != expected_program:
                invalid.append("programa token diverge da conta da operação")
            if transfer.mint is None or transfer.decimals is None:
                invalid.append("mint/decimals ausentes; Transfer simples não basta para atribuição completa")
            elif transfer.mint != expected_mint:
                invalid.append("mint da transferência diverge do mint da conta da operação")
            if transfer.amount_raw <= 0:
                invalid.append("quantidade bruta da transferência não é positiva")
        if invalid:
            results.append(DammV2TransferEvidence(
                status="INCOMPLETE",
                input_transfer=input_transfer,
                output_transfer=output_transfer,
                reason="; ".join(dict.fromkeys(invalid)),
                transfer_fee_review_required=True,
                **base,
            ))
            continue

        fee_review = (
            input_transfer.program_id == TOKEN_2022_PROGRAM_ID
            or output_transfer.program_id == TOKEN_2022_PROGRAM_ID
        )
        results.append(DammV2TransferEvidence(
            status="ATTRIBUTED",
            input_transfer=input_transfer,
            output_transfer=output_transfer,
            reason=(
                "transferências atribuídas por contas e ancestralidade CPI; "
                "deltas e taxas ainda não reconciliados"
            ),
            transfer_fee_review_required=fee_review,
            **base,
        ))
    return results
