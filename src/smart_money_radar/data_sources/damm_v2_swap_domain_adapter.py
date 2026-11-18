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
from smart_money_radar.data_sources.solana_wrapped_sol_funding import NATIVE_MINT
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
    seen_operation_keys: set[tuple[int, int | None, tuple[int, ...]]] = set()
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
            or (
                association.inner_instruction_index is not None
                and (
                    isinstance(association.inner_instruction_index, bool)
                    or not isinstance(association.inner_instruction_index, int)
                    or association.inner_instruction_index < 0
                )
            )
            or isinstance(association.stack_height, bool)
            or not isinstance(association.stack_height, int)
            or association.stack_height < 1
            or isinstance(association.event_inner_instruction_index, bool)
            or not isinstance(association.event_inner_instruction_index, int)
            or association.event_inner_instruction_index < 0
            or isinstance(association.event_stack_height, bool)
            or not isinstance(association.event_stack_height, int)
            or association.event_stack_height != association.stack_height + 1
            or not isinstance(association.event_cpi_path, tuple)
            or any(isinstance(part, bool) or not isinstance(part, int) or part < 0
                   for part in association.event_cpi_path)
            or len(association.event_cpi_path) != len(association.cpi_path) + 1
            or association.event_cpi_path[:-1] != association.cpi_path
            or (
                association.inner_instruction_index is not None
                and association.event_inner_instruction_index <= association.inner_instruction_index
            )
            or accounts.program != METEORA_DAMM_V2_PROGRAM_ID
        ):
            raise ValueError("identidade CPI ou programa DAMM v2 inválido")
        operation_key = (
            association.instruction_index,
            association.inner_instruction_index,
            association.cpi_path,
        )
        if operation_key in seen_operation_keys:
            raise ValueError("identidade de swap DAMM v2 duplicada no lote")
        seen_operation_keys.add(operation_key)
        if item.status != "ATTRIBUTED":
            raise ValueError("transferências não estão ATTRIBUTED")
        if (
            item.instruction_index != association.instruction_index
            or item.inner_instruction_index != association.inner_instruction_index
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
        lifecycle_owners = {
            lifecycle.token_account: lifecycle.owner_wallet
            for lifecycle in reconciliation.wrapped_sol_lifecycles
        }
        input_owner = (
            input_delta.owner if input_delta is not None
            else lifecycle_owners.get(input_transfer.source_account)
        )
        output_owner = (
            output_delta.owner if output_delta is not None
            else lifecycle_owners.get(output_transfer.destination_account)
        )
        if input_owner != monitored_wallet or output_owner != monitored_wallet:
            raise ValueError("propriedade das token accounts não confirma a carteira monitorada")
        if input_delta is None:
            if accounts.input_mint != NATIVE_MINT:
                raise ValueError("delta de input ausente sem evidência lifecycle wSOL")
        elif input_delta.mint != accounts.input_mint:
            raise ValueError("mint do delta input da carteira diverge do swap")
        if output_delta is None:
            if accounts.output_mint != NATIVE_MINT:
                raise ValueError("delta de output ausente sem evidência lifecycle wSOL")
        elif output_delta.mint != accounts.output_mint:
            raise ValueError("mint do delta output da carteira diverge do swap")

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
        fee_absence_evidence = tuple(
            (
                f"Token-2022 transfer fee comprovadamente zero para mint {proof.mint}; "
                f"signature={proof.signature}; slot={proof.transaction_slot}; "
                f"transaction_index={proof.transaction_index}; "
                f"snapshot_slot={proof.current_snapshot_slot}; {proof.basis}"
            )
            for proof in reconciliation.transfer_fee_absence_proofs
            if (
                item.referral_transfer is not None
                and item.referral_transfer.mint == proof.mint
                and event.has_referral
            )
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
                "lote completo reconciliado contra deltas pre/post e lifecycle wSOL quando aplicável",
                "propriedade das token accounts confirmada por snapshots ou ATA lifecycle para a carteira monitorada",
                "input_amount representa débito bruto; output_amount representa crédito líquido",
            ) + fee_absence_evidence,
        )
        bundles.append(DammV2SwapDomainBundle(observation, classification, evidence))

    return tuple(bundles)
