"""Adapta lotes DAMM v2 economicamente reconciliados aos contratos de domínio.

O adaptador é deliberadamente conservador: só emite bundles quando o lote
inteiro está RECONCILED e a propriedade das token accounts de entrada/saída
confirma a carteira monitorada. Não infere BUY/SELL.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from smart_money_radar.data_sources.damm_v2_decoder import METEORA_DAMM_V2_PROGRAM_ID
from smart_money_radar.data_sources.damm_v2_economic_reconciliation import (
    DammV2EconomicReconciliation,
)
from smart_money_radar.data_sources.damm_v2_transfer_analyzer import (
    DammV2SwapTransferContext,
    DammV2TransferEvidence,
)
from smart_money_radar.data_sources.solana_token_balance_delta_decoder import (
    SolanaTokenBalanceDeltaResult,
)
from smart_money_radar.domain.models import (
    SwapClassification,
    SwapEvidence,
    SwapObservation,
    build_swap_operation_id,
)


@dataclass(frozen=True)
class DammV2SwapDomainBundle:
    observation: SwapObservation
    classification: SwapClassification
    evidence: SwapEvidence


def _amount_decimal(raw: int, decimals: int, field: str) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise ValueError(f"{field} deve ser inteiro positivo")
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 255:
        raise ValueError(f"decimals inválidos em {field}")
    return Decimal(raw).scaleb(-decimals)


def build_damm_v2_swap_domain_bundles(
    *,
    contexts: Sequence[DammV2SwapTransferContext],
    transfer_evidence: Sequence[DammV2TransferEvidence],
    balance_deltas: SolanaTokenBalanceDeltaResult,
    reconciliation: DammV2EconomicReconciliation,
    monitored_wallet: str,
    signature: str,
    observed_at: datetime,
    parser_version: str,
) -> tuple[DammV2SwapDomainBundle, ...]:
    """Cria um bundle por swap somente após reconciliação econômica do lote.

    input_amount representa o débito bruto da token account da carteira;
    output_amount representa o crédito spendable líquido recebido. A
    classificação fica UNKNOWN porque o papel de ativo-base/quote é uma
    política de domínio separada da direção A_TO_B/B_TO_A do pool.
    """
    if not isinstance(reconciliation, DammV2EconomicReconciliation):
        raise TypeError("reconciliation inválida")
    if reconciliation.status != "RECONCILED":
        raise ValueError("lote DAMM v2 precisa estar RECONCILED")
    if not isinstance(balance_deltas, SolanaTokenBalanceDeltaResult) or not balance_deltas.complete:
        raise ValueError("deltas completos são obrigatórios")
    if not isinstance(monitored_wallet, str) or not monitored_wallet.strip():
        raise ValueError("monitored_wallet obrigatório")
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError("signature obrigatória")
    if not isinstance(observed_at, datetime):
        raise TypeError("observed_at deve ser datetime")
    if not isinstance(parser_version, str) or not parser_version.strip():
        raise ValueError("parser_version obrigatório")
    if not isinstance(contexts, Sequence) or isinstance(contexts, (str, bytes)):
        raise TypeError("contexts deve ser uma sequência")
    if not isinstance(transfer_evidence, Sequence) or isinstance(transfer_evidence, (str, bytes)):
        raise TypeError("transfer_evidence deve ser uma sequência")
    if (
        not contexts
        or len(contexts) != len(transfer_evidence)
        or len(contexts) != reconciliation.operation_count
    ):
        raise ValueError("contextos, evidências e reconciliação devem cobrir o mesmo lote")

    deltas_by_account = {}
    for delta in balance_deltas.deltas:
        if delta.token_account in deltas_by_account:
            raise ValueError("token account duplicada nos deltas")
        deltas_by_account[delta.token_account] = delta

    bundles = []
    for context, item in zip(contexts, transfer_evidence):
        association = context.association
        event = association.event
        accounts = context.accounts
        if association.status != "MATCHED" or event is None:
            raise ValueError("associação swap/EvtSwap2 não está MATCHED")
        if (
            isinstance(association.instruction_index, bool)
            or not isinstance(association.instruction_index, int)
            or association.instruction_index < 0
            or not isinstance(association.cpi_path, tuple)
            or any(isinstance(part, bool) or not isinstance(part, int) or part < 0
                   for part in association.cpi_path)
        ):
            raise ValueError("identidade CPI inválida")
        if item.status != "ATTRIBUTED":
            raise ValueError("transferências não estão ATTRIBUTED")
        if (
            item.instruction_index != association.instruction_index
            or item.cpi_path != association.cpi_path
            or item.input_transfer is None
            or item.output_transfer is None
            or item.input_transfer.execution_status != "EXECUTED"
            or item.output_transfer.execution_status != "EXECUTED"
        ):
            raise ValueError("evidência de transferências diverge da associação")
        input_transfer = item.input_transfer
        output_transfer = item.output_transfer
        for transfer in (input_transfer, output_transfer):
            if (
                transfer.cpi_path_valid is not True
                or transfer.instruction_index != association.instruction_index
                or transfer.inner_instruction_index is None
                or association.event_inner_instruction_index is None
                or transfer.inner_instruction_index >= association.event_inner_instruction_index
                or transfer.stack_height is None
                or association.stack_height is None
                or transfer.stack_height <= association.stack_height
                or not isinstance(transfer.cpi_path, tuple)
                or len(transfer.cpi_path) <= len(association.cpi_path)
                or transfer.cpi_path[:len(association.cpi_path)] != association.cpi_path
            ):
                raise ValueError("proveniência CPI das transferências não é confiável")
        if (
            input_transfer.source_account != accounts.input_token_account
            or input_transfer.destination_account != accounts.input_vault
            or input_transfer.mint != accounts.input_mint
            or input_transfer.program_id != accounts.input_token_program
            or output_transfer.source_account != accounts.output_vault
            or output_transfer.destination_account != accounts.output_token_account
            or output_transfer.mint != accounts.output_mint
            or output_transfer.program_id != accounts.output_token_program
        ):
            raise ValueError("contas ou mints das transferências divergem do contexto")

        input_delta = deltas_by_account.get(input_transfer.source_account)
        output_delta = deltas_by_account.get(output_transfer.destination_account)
        if (
            input_delta is None
            or output_delta is None
            or input_delta.owner != monitored_wallet
            or output_delta.owner != monitored_wallet
        ):
            raise ValueError("propriedade das token accounts não confirma a carteira monitorada")
        if input_delta.mint != accounts.input_mint or output_delta.mint != accounts.output_mint:
            raise ValueError("mints dos deltas da carteira divergem do swap")

        input_amount = _amount_decimal(
            event.included_transfer_fee_amount_in,
            input_transfer.decimals,
            "input bruto",
        )
        output_amount = _amount_decimal(
            event.excluded_transfer_fee_amount_out,
            output_transfer.decimals,
            "output líquido",
        )
        operation_id = build_swap_operation_id(
            "solana", signature, association.instruction_index, association.cpi_path
        )
        observation = SwapObservation(
            operation_id=operation_id,
            chain="solana",
            wallet_address=monitored_wallet,
            signature=signature,
            input_mint=accounts.input_mint,
            output_mint=accounts.output_mint,
            input_amount=input_amount,
            output_amount=output_amount,
            observed_at=observed_at,
            parser_version=parser_version,
        )
        classification = SwapClassification(
            operation_id=operation_id,
            side="UNKNOWN",
            confidence=Decimal("0"),
            reason="ativo-base/quote não foi definido pela política de classificação",
        )
        evidence = SwapEvidence(
            operation_id=operation_id,
            program_id=METEORA_DAMM_V2_PROGRAM_ID,
            venue="Meteora DAMM v2",
            instruction_index=association.instruction_index,
            cpi_path=association.cpi_path,
            evidence=(
                "EvtSwap2 associado estruturalmente ao swap",
                "transferências input/output atribuídas e executadas",
                "lote completo reconciliado contra deltas pre/post",
                "propriedade das token accounts confirmada para a carteira monitorada",
                "input_amount representa débito bruto; output_amount representa crédito líquido",
            ),
        )
        bundles.append(DammV2SwapDomainBundle(observation, classification, evidence))

    return tuple(bundles)
