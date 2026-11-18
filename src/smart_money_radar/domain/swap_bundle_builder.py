"""Converte reconciliações CPMM comprovadas nos contratos do domínio."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from smart_money_radar.data_sources.raydium_cpmm_analyzer import (
    RaydiumCpmmDecodedSwap,
)
from smart_money_radar.data_sources.raydium_cpmm_decoder import (
    RAYDIUM_CPMM_PROGRAM_ID,
)
from smart_money_radar.data_sources.raydium_cpmm_transfer_reconciliation import (
    RaydiumCpmmSwapReconciliation,
)
from smart_money_radar.domain.models import (
    SwapClassification,
    SwapEvidence,
    SwapObservation,
    build_swap_operation_id,
)


@dataclass(frozen=True)
class SwapDomainBundle:
    observation: SwapObservation
    classification: SwapClassification
    evidence: SwapEvidence


def _decimal_amount(amount_raw: int, decimals: int) -> Decimal:
    if isinstance(amount_raw, bool) or not isinstance(amount_raw, int) or amount_raw <= 0:
        raise ValueError("Quantidade bruta deve ser inteiro positivo.")
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 255:
        raise ValueError("Decimals deve ser inteiro entre 0 e 255.")
    return Decimal(amount_raw).scaleb(-decimals)


def _classify(
    operation_id: str,
    input_mint: str,
    output_mint: str,
    reference_mints: set[str],
) -> SwapClassification:
    # BUY/SELL is defined only relative to an explicitly configured quote asset.
    input_is_reference = input_mint in reference_mints
    output_is_reference = output_mint in reference_mints
    if input_is_reference and not output_is_reference:
        return SwapClassification(
            operation_id=operation_id,
            side="BUY",
            confidence=Decimal("1"),
            reason="Ativo de entrada pertence à lista configurada de referência; saída é o ativo adquirido.",
        )
    if output_is_reference and not input_is_reference:
        return SwapClassification(
            operation_id=operation_id,
            side="SELL",
            confidence=Decimal("1"),
            reason="Ativo de saída pertence à lista configurada de referência; entrada é o ativo vendido.",
        )
    return SwapClassification(
        operation_id=operation_id,
        side="UNKNOWN",
        confidence=Decimal("0"),
        reason="Não há exatamente um lado de referência configurado para determinar BUY ou SELL.",
    )


def build_swap_domain_bundles(
    reconciliations: Iterable[RaydiumCpmmSwapReconciliation],
    *,
    chain: str,
    signature: str,
    monitored_wallet: str,
    observed_at: datetime,
    parser_version: str,
    reference_mints: Iterable[str] = (),
) -> list[SwapDomainBundle]:
    """Cria bundles de domínio somente a partir de reconciliações MATCHED.

    Não persiste os bundles. Classificação BUY/SELL só ocorre se exatamente
    um lado pertencer à lista explícita de mints de referência.
    """
    if not all(isinstance(value, str) and value.strip() for value in (
        chain, signature, monitored_wallet, parser_version
    )):
        raise ValueError("Chain, signature, monitored_wallet e parser_version são obrigatórios.")
    if not isinstance(observed_at, datetime):
        raise TypeError("observed_at deve ser datetime")
    quote_mints = set(reference_mints)
    if any(not isinstance(mint, str) or not mint.strip() for mint in quote_mints):
        raise ValueError("reference_mints deve conter apenas mints não vazios")

    bundles = []
    seen_operation_ids: set[str] = set()
    for item in reconciliations:
        if item.status != "MATCHED":
            continue
        swap: RaydiumCpmmDecodedSwap = item.swap
        accounts = swap.accounts
        if item.wallet_address != monitored_wallet:
            raise ValueError("Reconciliação MATCHED não pertence à carteira monitorada.")
        if (
            item.input_amount_raw is None
            or item.output_amount_raw is None
            or item.input_decimals is None
            or item.output_decimals is None
            or item.input_transfer is None
            or item.output_transfer is None
        ):
            raise ValueError("Reconciliação MATCHED sem quantidades, decimals ou transferências completas.")

        operation_id = build_swap_operation_id(
            chain, signature, swap.instruction_index, swap.cpi_path
        )
        if operation_id in seen_operation_ids:
            raise ValueError("operation_id duplicado nas reconciliações.")
        seen_operation_ids.add(operation_id)
        observation = SwapObservation(
            operation_id=operation_id,
            chain=chain,
            wallet_address=monitored_wallet,
            signature=signature,
            input_mint=accounts.input_token_mint,
            output_mint=accounts.output_token_mint,
            input_amount=_decimal_amount(item.input_amount_raw, item.input_decimals),
            output_amount=_decimal_amount(item.output_amount_raw, item.output_decimals),
            observed_at=observed_at,
            parser_version=parser_version,
        )
        classification = _classify(
            operation_id,
            accounts.input_token_mint,
            accounts.output_token_mint,
            quote_mints,
        )
        evidence = SwapEvidence(
            operation_id=operation_id,
            program_id=RAYDIUM_CPMM_PROGRAM_ID,
            venue="Raydium CPMM",
            instruction_index=swap.instruction_index,
            cpi_path=swap.cpi_path,
            evidence=(
                f"input_transfer:{item.input_transfer.instruction_index}:{item.input_transfer.inner_instruction_index}",
                f"output_transfer:{item.output_transfer.instruction_index}:{item.output_transfer.inner_instruction_index}",
                f"input_token_account:{accounts.input_token_account}:transfer_amount_raw={item.input_transfer.amount_raw}",
                f"output_token_account:{accounts.output_token_account}:transfer_amount_raw={item.output_transfer.amount_raw}",
                f"pool_state:{accounts.pool_state}",
                f"input_vault:{accounts.input_vault}",
                f"output_vault:{accounts.output_vault}",
            ),
        )
        bundles.append(SwapDomainBundle(
            observation=observation,
            classification=classification,
            evidence=evidence,
        ))
    return bundles
