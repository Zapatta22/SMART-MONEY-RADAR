"""Atribuição conservadora de transferências SPL a swaps DAMM v2.

Este módulo atribui transferências de input, output e referral a uma operação
já associada a EvtSwap2. Atribuição não equivale a reconciliação econômica:
deltas de token accounts/vaults e taxas Token-2022 ainda exigem validação.
"""
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from smart_money_radar.data_sources.damm_v2_accounts import DammV2SwapAccounts
from smart_money_radar.data_sources.damm_v2_analyzer import (
    DammV2SwapEventAssociation,
)
from smart_money_radar.data_sources.damm_v2_fee_math import resolve_damm_fee_mode
from smart_money_radar.data_sources.damm_v2_decoder import METEORA_DAMM_V2_PROGRAM_ID
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
    referral_transfer: SolanaTokenTransfer | None
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
        or not transfer.cpi_path_valid
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
    """Atribui input/output/referral a no máximo uma operação por transferência.

    A atribuição exige descendência CPI demonstrável. Referral é localizado no
    vault do token definido por FeeMode e deve corresponder ao referral_fee do
    EvtSwap2. Atribuição continua não sendo reconciliação econômica.
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
        event = association.event
        if association.status != "MATCHED" or event is None:
            candidates.append({"input": [], "output": [], "referral": []})
            continue

        selected = {"input": [], "output": [], "referral": []}
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

        fee_mode = resolve_damm_fee_mode(
            event.collect_fee_mode, event.trade_direction, event.has_referral
        )
        if event.has_referral:
            fee_vault = accounts.token_a_vault if fee_mode.fees_on_token_a else accounts.token_b_vault
            referral_account = accounts.referral_token_account
            if referral_account and referral_account != METEORA_DAMM_V2_PROGRAM_ID:
                for transfer_index, transfer in enumerate(transfers):
                    if transfer.execution_status != "EXECUTED":
                        continue
                    if not _is_descendant_transfer(transfer, association):
                        continue
                    if (
                        transfer.source_account == fee_vault
                        and transfer.destination_account == referral_account
                    ):
                        selected["referral"].append(transfer_index)

        # When the referral account is also the user's output account, the
        # principal output and referral payment share the same source/destination.
        # If multiple referral candidates exist, the event's exact referral_fee
        # safely distinguishes the referral leg; duplicate exact matches remain
        # ambiguous and fail closed.
        if len(selected["referral"]) > 1:
            exact_referral = [
                index for index in selected["referral"]
                if transfers[index].amount_raw == event.swap_result.referral_fee
            ]
            if exact_referral:
                selected["referral"] = exact_referral

        # A referral account may intentionally be the same token account as
        # the user's input/output account. Once a transfer is uniquely identified
        # as referral by fee-vault -> referral-account, do not also count it as
        # the swap's principal input/output transfer.
        referral_indexes = set(selected["referral"])
        if referral_indexes:
            selected["input"] = [
                index for index in selected["input"]
                if index not in referral_indexes
            ]
            selected["output"] = [
                index for index in selected["output"]
                if index not in referral_indexes
            ]

        candidates.append(selected)
        for role, indexes in selected.items():
            for transfer_index in indexes:
                transfer_owners[transfer_index].append((context_index, role))

    results: list[DammV2TransferEvidence] = []
    for context_index, context in enumerate(contexts):
        association = context.association
        accounts = context.accounts
        event = association.event
        base = dict(
            instruction_index=association.instruction_index,
            inner_instruction_index=association.inner_instruction_index,
            cpi_path=association.cpi_path,
        )
        if association.status != "MATCHED" or event is None:
            results.append(DammV2TransferEvidence(
                status="ASSOCIATION_UNRESOLVED",
                input_transfer=None,
                output_transfer=None,
                referral_transfer=None,
                reason="swap e EvtSwap2 não possuem associação estrutural única",
                transfer_fee_review_required=True,
                **base,
            ))
            continue

        selected = candidates[context_index]
        if any(len(selected[role]) > 1 for role in ("input", "output", "referral")):
            results.append(DammV2TransferEvidence(
                status="AMBIGUOUS",
                input_transfer=None,
                output_transfer=None,
                referral_transfer=None,
                reason="mais de uma transferência candidata para o mesmo papel",
                transfer_fee_review_required=True,
                **base,
            ))
            continue

        input_transfer = transfers[selected["input"][0]] if selected["input"] else None
        output_transfer = transfers[selected["output"][0]] if selected["output"] else None
        referral_transfer = transfers[selected["referral"][0]] if selected["referral"] else None
        if input_transfer is None or output_transfer is None:
            results.append(DammV2TransferEvidence(
                status="TRANSFER_MISSING",
                input_transfer=input_transfer,
                output_transfer=output_transfer,
                referral_transfer=referral_transfer,
                reason="transferência de entrada ou saída não foi identificada univocamente",
                transfer_fee_review_required=True,
                **base,
            ))
            continue

        if not event.has_referral and event.swap_result.referral_fee != 0:
            results.append(DammV2TransferEvidence(
                status="INCOMPLETE",
                input_transfer=input_transfer,
                output_transfer=output_transfer,
                referral_transfer=referral_transfer,
                reason="EvtSwap2 informa referral_fee sem has_referral",
                transfer_fee_review_required=True,
                **base,
            ))
            continue
        if event.has_referral and event.swap_result.referral_fee > 0 and referral_transfer is None:
            results.append(DammV2TransferEvidence(
                status="TRANSFER_MISSING",
                input_transfer=input_transfer,
                output_transfer=output_transfer,
                referral_transfer=None,
                reason="EvtSwap2 exige transferência de referral, mas nenhuma transferência descendente foi encontrada",
                transfer_fee_review_required=True,
                **base,
            ))
            continue

        fee_mode = resolve_damm_fee_mode(
            event.collect_fee_mode, event.trade_direction, event.has_referral
        )
        if fee_mode.fees_on_token_a:
            referral_mint = accounts.token_a_mint
            referral_program = accounts.token_a_program
            referral_vault = accounts.token_a_vault
        else:
            referral_mint = accounts.token_b_mint
            referral_program = accounts.token_b_program
            referral_vault = accounts.token_b_vault

        expected = [
            (input_transfer, accounts.input_mint, accounts.input_token_program, "entrada", True),
            (output_transfer, accounts.output_mint, accounts.output_token_program, "saída", True),
        ]
        if referral_transfer is not None:
            expected.append((
                referral_transfer, referral_mint, referral_program, "referral", False
            ))

        invalid = []
        for transfer, expected_mint, expected_program, label, must_be_positive in expected:
            if transfer.program_id != expected_program:
                invalid.append(f"programa token diverge da conta de {label}")
            if transfer.mint is None or transfer.decimals is None:
                invalid.append(f"mint/decimals ausentes na transferência de {label}")
            elif transfer.mint != expected_mint:
                invalid.append(f"mint da transferência de {label} diverge da conta")
            if must_be_positive and transfer.amount_raw <= 0:
                invalid.append(f"quantidade bruta da transferência de {label} não é positiva")
            if transfer.instruction_type == "TRANSFER_CHECKED_WITH_FEE":
                if (
                    isinstance(transfer.fee_amount_raw, bool)
                    or not isinstance(transfer.fee_amount_raw, int)
                    or not 0 <= transfer.fee_amount_raw <= transfer.amount_raw
                ):
                    invalid.append(f"fee inválida na transferência de {label}")

        if referral_transfer is not None:
            if referral_transfer.source_account != referral_vault:
                invalid.append("vault de origem da transferência de referral diverge do FeeMode")
            if referral_transfer.amount_raw != event.swap_result.referral_fee:
                invalid.append("quantidade bruta da transferência de referral diverge do EvtSwap2")
        if invalid:
            results.append(DammV2TransferEvidence(
                status="INCOMPLETE",
                input_transfer=input_transfer,
                output_transfer=output_transfer,
                referral_transfer=referral_transfer,
                reason="; ".join(dict.fromkeys(invalid)),
                transfer_fee_review_required=True,
                **base,
            ))
            continue

        selected_indexes = [
            selected["input"][0],
            selected["output"][0],
        ] + ([selected["referral"][0]] if referral_transfer is not None else [])
        if any(len(transfer_owners[index]) != 1 for index in selected_indexes):
            results.append(DammV2TransferEvidence(
                status="AMBIGUOUS",
                input_transfer=None,
                output_transfer=None,
                referral_transfer=None,
                reason="uma transferência candidata foi reutilizada por mais de uma operação/papel",
                transfer_fee_review_required=True,
                **base,
            ))
            continue

        fee_review = any(
            transfer.program_id == TOKEN_2022_PROGRAM_ID
            or transfer.fee_amount_raw not in (None, 0)
            for transfer in (input_transfer, output_transfer, referral_transfer)
            if transfer is not None
        )
        results.append(DammV2TransferEvidence(
            status="ATTRIBUTED",
            input_transfer=input_transfer,
            output_transfer=output_transfer,
            referral_transfer=referral_transfer,
            reason=(
                "transferências input/output/referral atribuídas por contas e CPI; "
                "deltas e taxas ainda não reconciliados"
            ),
            transfer_fee_review_required=fee_review,
            **base,
        ))
    return results

