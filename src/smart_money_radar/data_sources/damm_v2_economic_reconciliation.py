"""Reconciliação econômica conservadora de swaps Meteora DAMM v2.

A validação é feita em lote por transação: transferências identificadas por
operação são agregadas por token account e comparadas com os deltas pre/post.
Isso evita repartir arbitrariamente deltas líquidos entre swaps sequenciais.

Não cria SwapObservation, BUY/SELL, sinal ou autorização de execução.
"""
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from smart_money_radar.data_sources.damm_v2_transfer_analyzer import (
    DammV2SwapTransferContext,
    DammV2TransferEvidence,
)
from smart_money_radar.data_sources.solana_token_balance_delta_decoder import (
    SolanaTokenBalanceDeltaResult,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    SolanaTokenTransfer,
)


EconomicStatus = Literal["RECONCILED", "INCOMPLETE", "AMBIGUOUS"]


@dataclass(frozen=True)
class DammV2ExpectedAccountDelta:
    token_account: str
    mint: str
    decimals: int
    expected_delta_raw: int


@dataclass(frozen=True)
class DammV2EconomicReconciliation:
    status: EconomicStatus
    operation_count: int
    expected_account_deltas: tuple[DammV2ExpectedAccountDelta, ...]
    reason: str


def _add_expected(
    expected: dict[str, dict[str, int | str]],
    account: str,
    mint: str,
    decimals: int,
    delta: int,
) -> None:
    current = expected.get(account)
    if current is None:
        expected[account] = {
            "mint": mint,
            "decimals": decimals,
            "delta": delta,
        }
        return
    if current["mint"] != mint or current["decimals"] != decimals:
        raise ValueError("token account reutilizada com mint/decimals divergentes")
    current["delta"] = int(current["delta"]) + delta


def _net_received(
    transfer: SolanaTokenTransfer,
    expected_gross: int,
    expected_net: int | None,
    label: str,
) -> int:
    if transfer.execution_status != "EXECUTED":
        raise ValueError(f"transferência {label} não executada")
    if transfer.amount_raw != expected_gross:
        raise ValueError(f"amount bruto de {label} diverge do EvtSwap2")
    if transfer.instruction_type not in {
        "TRANSFER", "TRANSFER_CHECKED", "TRANSFER_CHECKED_WITH_FEE"
    }:
        raise ValueError(f"tipo de transferência {label} não suportado")
    if transfer.program_id not in {SPL_TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID}:
        raise ValueError(f"Token Program de {label} não suportado")
    if transfer.mint is None or transfer.decimals is None:
        raise ValueError(f"mint/decimals ausentes em {label}")
    if transfer.instruction_type == "TRANSFER_CHECKED_WITH_FEE":
        fee = transfer.fee_amount_raw
        if (
            isinstance(fee, bool)
            or not isinstance(fee, int)
            or not 0 <= fee <= transfer.amount_raw
        ):
            raise ValueError(f"fee explícita inválida em {label}")
        net = transfer.amount_raw - fee
        if expected_net is not None and net != expected_net:
            raise ValueError(f"crédito líquido de {label} diverge do EvtSwap2")
        return net
    if transfer.fee_amount_raw not in (None, 0):
        raise ValueError(f"fee inesperada em {label}")
    if transfer.program_id == SPL_TOKEN_PROGRAM_ID:
        if expected_net is not None and expected_net != transfer.amount_raw:
            raise ValueError(f"SPL Token não pode reter transfer fee em {label}")
        return transfer.amount_raw
    # A fee de um TransferChecked Token-2022 comum não está no payload.
    # Input/output podem ser conferidos com os campos bruto/líquido do EvtSwap2.
    if expected_net is None:
        raise ValueError(
            f"transfer fee Token-2022 de {label} não está explícita nem no evento"
        )
    if not 0 <= expected_net <= transfer.amount_raw:
        raise ValueError(f"crédito líquido inválido em {label}")
    return expected_net


def reconcile_damm_v2_economic_batch(
    contexts: Sequence[DammV2SwapTransferContext],
    evidence: Sequence[DammV2TransferEvidence],
    balance_deltas: SolanaTokenBalanceDeltaResult,
) -> DammV2EconomicReconciliation:
    """Reconcilia todas as operações DAMM v2 do mesmo payload de transação.

    A lista contexts/evidence deve representar o conjunto completo de swaps
    DAMM v2 analisados naquela transação. Deltas incompletos, evidência ausente,
    CPI não confiável, conta compartilhada com conflito ou divergência bruta/
    líquida fazem o lote falhar fechado.
    """
    if not isinstance(contexts, Sequence) or isinstance(contexts, (str, bytes)):
        raise TypeError("contexts deve ser uma sequência")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        raise TypeError("evidence deve ser uma sequência")
    if len(contexts) == 0 or len(contexts) != len(evidence):
        raise ValueError("contexts/evidence devem conter o mesmo conjunto não vazio")
    if not isinstance(balance_deltas, SolanaTokenBalanceDeltaResult):
        raise TypeError("balance_deltas inválido")
    if not balance_deltas.complete:
        return DammV2EconomicReconciliation(
            "INCOMPLETE", len(contexts), (),
            "snapshots pre/post incompletos ou inconsistentes: "
            + ", ".join(issue.code for issue in balance_deltas.issues),
        )

    expected: dict[str, dict[str, int | str]] = {}
    claimed_transfers: set[SolanaTokenTransfer] = set()
    try:
        for context, item in zip(contexts, evidence):
            if not isinstance(context, DammV2SwapTransferContext):
                raise TypeError("contexto DAMM v2 inválido")
            if not isinstance(item, DammV2TransferEvidence):
                raise TypeError("evidência de transferência inválida")
            association = context.association
            event = association.event
            if association.status != "MATCHED" or event is None:
                raise ValueError("associação swap/EvtSwap2 não está MATCHED")
            if item.status != "ATTRIBUTED":
                raise ValueError(f"transfer evidence não está ATTRIBUTED: {item.status}")
            if (
                item.instruction_index != association.instruction_index
                or item.inner_instruction_index != association.inner_instruction_index
                or item.cpi_path != association.cpi_path
            ):
                raise ValueError("identidade da evidência diverge da associação")
            if (
                item.input_transfer is None
                or item.output_transfer is None
            ):
                raise ValueError("transferência input/output ausente")
            transfers = [item.input_transfer, item.output_transfer]
            if item.referral_transfer is not None:
                transfers.append(item.referral_transfer)
            if len(set(transfers)) != len(transfers) or any(
                transfer in claimed_transfers for transfer in transfers
            ):
                raise ValueError("transferência reutilizada entre papéis/operações")
            claimed_transfers.update(transfers)

            accounts = context.accounts
            input_transfer = item.input_transfer
            output_transfer = item.output_transfer
            input_net = _net_received(
                input_transfer,
                event.included_transfer_fee_amount_in,
                event.swap_result.included_fee_input_amount,
                "input",
            )
            output_net = _net_received(
                output_transfer,
                event.included_transfer_fee_amount_out,
                event.excluded_transfer_fee_amount_out,
                "output",
            )
            if (
                input_transfer.source_account != accounts.input_token_account
                or input_transfer.destination_account != accounts.input_vault
                or input_transfer.mint != accounts.input_mint
                or input_transfer.program_id != accounts.input_token_program
            ):
                raise ValueError("contas/mint/programa da transferência input divergem")
            if (
                output_transfer.source_account != accounts.output_vault
                or output_transfer.destination_account != accounts.output_token_account
                or output_transfer.mint != accounts.output_mint
                or output_transfer.program_id != accounts.output_token_program
            ):
                raise ValueError("contas/mint/programa da transferência output divergem")

            _add_expected(
                expected, input_transfer.source_account, input_transfer.mint,
                input_transfer.decimals, -input_transfer.amount_raw,
            )
            _add_expected(
                expected, input_transfer.destination_account, input_transfer.mint,
                input_transfer.decimals, input_net,
            )
            _add_expected(
                expected, output_transfer.source_account, output_transfer.mint,
                output_transfer.decimals, -output_transfer.amount_raw,
            )
            _add_expected(
                expected, output_transfer.destination_account, output_transfer.mint,
                output_transfer.decimals, output_net,
            )

            referral = item.referral_transfer
            referral_fee = event.swap_result.referral_fee
            if event.has_referral and referral_fee > 0 and referral is None:
                raise ValueError("referral esperado pelo EvtSwap2 está ausente")
            if not event.has_referral and referral_fee != 0:
                raise ValueError("referral_fee incompatível com has_referral")
            if referral is not None:
                if not event.has_referral or referral_fee <= 0:
                    raise ValueError("transferência referral sem referral válido no evento")
                if referral.amount_raw != referral_fee:
                    raise ValueError("amount bruto referral diverge do EvtSwap2")
                if (
                    referral.destination_account != accounts.referral_token_account
                    or referral.source_account not in {
                        accounts.token_a_vault, accounts.token_b_vault
                    }
                ):
                    raise ValueError("contas da transferência referral divergem")
                if referral.program_id not in {accounts.token_a_program, accounts.token_b_program}:
                    raise ValueError("Token Program referral diverge dos tokens do pool")
                if referral.mint not in {accounts.token_a_mint, accounts.token_b_mint}:
                    raise ValueError("mint referral diverge dos tokens do pool")
                referral_net = _net_received(
                    referral, referral_fee,
                    None if referral.program_id == TOKEN_2022_PROGRAM_ID
                    and referral.instruction_type != "TRANSFER_CHECKED_WITH_FEE"
                    else (
                        referral.amount_raw - (referral.fee_amount_raw or 0)
                    ),
                    "referral",
                )
                _add_expected(
                    expected, referral.source_account, referral.mint,
                    referral.decimals, -referral.amount_raw,
                )
                _add_expected(
                    expected, referral.destination_account, referral.mint,
                    referral.decimals, referral_net,
                )

        actual: dict[str, object] = {}
        for delta in balance_deltas.deltas:
            if delta.token_account in actual:
                raise ValueError("token account aparece em mais de um delta")
            actual[delta.token_account] = delta

        expected_rows = []
        mismatches = []
        for account, values in sorted(expected.items()):
            delta = actual.get(account)
            mint = str(values["mint"])
            decimals = int(values["decimals"])
            amount = int(values["delta"])
            expected_rows.append(DammV2ExpectedAccountDelta(
                account, mint, decimals, amount
            ))
            if delta is None:
                mismatches.append(f"delta ausente para {account}")
                continue
            if delta.mint != mint or delta.decimals != decimals:
                mismatches.append(f"mint/decimals divergem para {account}")
            elif delta.delta_raw != amount:
                mismatches.append(
                    f"delta diverge para {account}: esperado {amount}, observado {delta.delta_raw}"
                )
        if mismatches:
            return DammV2EconomicReconciliation(
                "INCOMPLETE", len(contexts), tuple(expected_rows),
                "; ".join(mismatches),
            )
        return DammV2EconomicReconciliation(
            "RECONCILED", len(contexts), tuple(expected_rows),
            "transferências input/output/referral e deltas agregados por token account "
            "conferem com EvtSwap2 para o lote completo de operações",
        )
    except (TypeError, ValueError) as exc:
        return DammV2EconomicReconciliation(
            "INCOMPLETE", len(contexts), (), str(exc)
        )
