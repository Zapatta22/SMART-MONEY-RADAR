"""Reconciliação econômica conservadora de swaps Meteora DAMM v2.

A validação é feita em lote por transação: transferências identificadas por
operação são agregadas por token account e comparadas com os deltas pre/post.
Isso evita repartir arbitrariamente deltas líquidos entre swaps sequenciais.

Não cria SwapObservation, BUY/SELL, sinal ou autorização de execução.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from smart_money_radar.data_sources.damm_v2_transfer_analyzer import (
    DammV2SwapTransferContext,
    DammV2TransferEvidence,
)
from smart_money_radar.data_sources.damm_v2_fee_math import resolve_damm_fee_mode
from smart_money_radar.data_sources.token2022_fee_absence_proof import Token2022NoTransferFeeProof
from smart_money_radar.data_sources.solana_token_balance_delta_decoder import (
    SolanaTokenBalanceDeltaResult,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    SolanaTokenTransfer,
)
from smart_money_radar.data_sources.solana_wrapped_sol_funding import (
    NATIVE_MINT,
    WrappedSolFundingEvidence,
    WrappedSolLifecycleEvidence,
    decode_wrapped_sol_funding,
    decode_wrapped_sol_account_lifecycle,
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
    wrapped_sol_fundings: tuple[WrappedSolFundingEvidence, ...] = ()
    wrapped_sol_lifecycles: tuple[WrappedSolLifecycleEvidence, ...] = ()
    transfer_fee_absence_proofs: tuple[Token2022NoTransferFeeProof, ...] = ()


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
    if (
        isinstance(transfer.amount_raw, bool)
        or not isinstance(transfer.amount_raw, int)
        or not 0 <= transfer.amount_raw <= (1 << 64) - 1
    ):
        raise ValueError(f"amount bruto inválido em {label}")
    if (
        isinstance(transfer.decimals, bool)
        or not isinstance(transfer.decimals, int)
        or not 0 <= transfer.decimals <= 255
    ):
        raise ValueError(f"decimals inválidos em {label}")
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
        if transfer.program_id != TOKEN_2022_PROGRAM_ID:
            raise ValueError(f"TransferCheckedWithFee fora de Token-2022 em {label}")
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
    if transfer.fee_amount_raw is not None and (
        isinstance(transfer.fee_amount_raw, bool)
        or not isinstance(transfer.fee_amount_raw, int)
        or transfer.fee_amount_raw != 0
    ):
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
    all_transfers: Sequence[SolanaTokenTransfer],
    *,
    raw_transaction: dict | None = None,
    monitored_wallet: str | None = None,
    transfer_fee_absence_proofs: Sequence[Token2022NoTransferFeeProof] = (),
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
    if not isinstance(all_transfers, Sequence) or isinstance(all_transfers, (str, bytes)):
        raise TypeError("all_transfers deve ser uma sequência")
    if not isinstance(transfer_fee_absence_proofs, Sequence) or isinstance(
        transfer_fee_absence_proofs, (str, bytes)
    ):
        raise TypeError("transfer_fee_absence_proofs deve ser uma sequência")
    if any(
        not isinstance(proof, Token2022NoTransferFeeProof)
        for proof in transfer_fee_absence_proofs
    ):
        raise TypeError("transfer_fee_absence_proofs contém prova inválida")
    if len({proof.mint for proof in transfer_fee_absence_proofs}) != len(
        transfer_fee_absence_proofs
    ):
        raise ValueError("prova de ausência de taxa duplicada para o mesmo mint")
    proof_by_mint = {proof.mint: proof for proof in transfer_fee_absence_proofs}
    consumed_fee_proof_mints: set[str] = set()
    if transfer_fee_absence_proofs:
        payload = (
            raw_transaction.get("result", raw_transaction)
            if isinstance(raw_transaction, dict) else None
        )
        transaction = payload.get("transaction") if isinstance(payload, dict) else None
        signatures = transaction.get("signatures") if isinstance(transaction, dict) else None
        signature = signatures[0] if isinstance(signatures, list) and signatures else None
        slot = payload.get("slot") if isinstance(payload, dict) else None
        if not isinstance(signature, str) or isinstance(slot, bool) or not isinstance(slot, int):
            raise ValueError("raw_transaction precisa comprovar signature/slot para usar prova de taxa zero")
        for proof in transfer_fee_absence_proofs:
            if proof.signature != signature or proof.transaction_slot != slot:
                raise ValueError("prova de taxa zero pertence a outra transação/slot")
    if any(not isinstance(transfer, SolanaTokenTransfer) for transfer in all_transfers):
        raise TypeError("all_transfers contém transferência inválida")
    if len({id(transfer) for transfer in all_transfers}) != len(all_transfers):
        return DammV2EconomicReconciliation(
            "AMBIGUOUS", len(contexts), (),
            "inventário de transferências contém referência duplicada",
        )
    if not balance_deltas.complete:
        return DammV2EconomicReconciliation(
            "INCOMPLETE", len(contexts), (),
            "snapshots pre/post incompletos ou inconsistentes: "
            + ", ".join(issue.code for issue in balance_deltas.issues),
        )

    expected: dict[str, dict[str, int | str]] = {}
    wrapped_sol_fundings: list[WrappedSolFundingEvidence] = []
    wrapped_sol_lifecycles: list[WrappedSolLifecycleEvidence] = []
    claimed_transfers: set[SolanaTokenTransfer] = set()
    claimed_operations: set[tuple[int, int | None, tuple[int, ...]]] = set()
    native_inputs: dict[str, list[tuple[SolanaTokenTransfer, int]]] = {}
    native_accounts: set[str] = set()
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
            if (
                isinstance(association.instruction_index, bool)
                or not isinstance(association.instruction_index, int)
                or association.instruction_index < 0
                or isinstance(association.stack_height, bool)
                or not isinstance(association.stack_height, int)
                or association.stack_height < 1
                or isinstance(association.event_inner_instruction_index, bool)
                or not isinstance(association.event_inner_instruction_index, int)
                or association.event_inner_instruction_index < 0
                or not isinstance(association.cpi_path, tuple)
                or any(
                    isinstance(part, bool) or not isinstance(part, int) or part < 0
                    for part in association.cpi_path
                )
            ):
                raise ValueError("metadados CPI da associação são inválidos")
            operation_key = (
                association.instruction_index,
                association.inner_instruction_index,
                association.cpi_path,
            )
            if operation_key in claimed_operations:
                raise RuntimeError(
                    "identidade de swap DAMM v2 duplicada/reutilizada no mesmo lote"
                )
            claimed_operations.add(operation_key)
            for transfer in transfers:
                if (
                    transfer.cpi_path_valid is not True
                    or isinstance(transfer.instruction_index, bool)
                    or not isinstance(transfer.instruction_index, int)
                    or transfer.instruction_index != association.instruction_index
                    or isinstance(transfer.inner_instruction_index, bool)
                    or not isinstance(transfer.inner_instruction_index, int)
                    or transfer.inner_instruction_index < 0
                    or transfer.inner_instruction_index >= association.event_inner_instruction_index
                    or isinstance(transfer.stack_height, bool)
                    or not isinstance(transfer.stack_height, int)
                    or transfer.stack_height <= association.stack_height
                    or not isinstance(transfer.cpi_path, tuple)
                    or any(
                        isinstance(part, bool) or not isinstance(part, int) or part < 0
                        for part in transfer.cpi_path
                    )
                    or len(transfer.cpi_path) <= len(association.cpi_path)
                    or transfer.cpi_path[:len(association.cpi_path)] != association.cpi_path
                ):
                    raise ValueError("proveniência CPI da transferência não é confiável")
            if len(set(transfers)) != len(transfers) or any(
                transfer in claimed_transfers for transfer in transfers
            ):
                raise RuntimeError("transferência reutilizada entre papéis/operações")
            claimed_transfers.update(transfers)

            if (
                event.included_transfer_fee_amount_out
                != event.swap_result.output_amount
            ):
                raise ValueError(
                    "included_transfer_fee_amount_out diverge do output_amount do EvtSwap2"
                )

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
            if input_transfer.mint == NATIVE_MINT:
                native_accounts.add(input_transfer.source_account)
                if input_transfer.program_id != SPL_TOKEN_PROGRAM_ID:
                    raise ValueError("wSOL deve usar o SPL Token Program clássico")
                native_inputs.setdefault(input_transfer.source_account, []).append(
                    (input_transfer, association.instruction_index)
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
            if output_transfer.mint == NATIVE_MINT:
                native_accounts.add(output_transfer.destination_account)

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
                fee_mode = resolve_damm_fee_mode(
                    event.collect_fee_mode, event.trade_direction, event.has_referral
                )
                if fee_mode.fees_on_token_a:
                    referral_vault = accounts.token_a_vault
                    referral_mint = accounts.token_a_mint
                    referral_program = accounts.token_a_program
                else:
                    referral_vault = accounts.token_b_vault
                    referral_mint = accounts.token_b_mint
                    referral_program = accounts.token_b_program
                if (
                    referral.destination_account != accounts.referral_token_account
                    or referral.source_account != referral_vault
                ):
                    raise ValueError("contas da transferência referral divergem do FeeMode")
                if referral.program_id != referral_program:
                    raise ValueError("Token Program referral diverge do FeeMode")
                if referral.mint != referral_mint:
                    raise ValueError("mint referral diverge do FeeMode")
                if (
                    referral.program_id == TOKEN_2022_PROGRAM_ID
                    and referral.instruction_type != "TRANSFER_CHECKED_WITH_FEE"
                ):
                    no_fee_proof = proof_by_mint.get(referral.mint)
                    if no_fee_proof is None:
                        expected_referral_net = None
                    else:
                        consumed_fee_proof_mints.add(referral.mint)
                        expected_referral_net = referral.amount_raw
                else:
                    expected_referral_net = referral.amount_raw - (
                        referral.fee_amount_raw or 0
                    )
                referral_net = _net_received(
                    referral, referral_fee, expected_referral_net, "referral",
                )
                _add_expected(
                    expected, referral.source_account, referral.mint,
                    referral.decimals, -referral.amount_raw,
                )
                _add_expected(
                    expected, referral.destination_account, referral.mint,
                    referral.decimals, referral_net,
                )

        # Contas wSOL criadas e fechadas dentro da mesma transação não possuem
        # snapshots pre/post utilizáveis. Reconstruir seus ciclos antes do caminho
        # simples de funding e excluir do comparativo de delta apenas se todo o
        # ciclo (criação, funding, SyncNative, transferências atribuídas e close)
        # estiver comprovado.
        if raw_transaction is not None and monitored_wallet:
            for token_account in sorted(native_accounts):
                lifecycle = decode_wrapped_sol_account_lifecycle(
                    raw_transaction,
                    token_account=token_account,
                    owner_wallet=monitored_wallet,
                    all_transfers=all_transfers,
                    claimed_transfers=claimed_transfers,
                )
                if lifecycle is not None:
                    wrapped_sol_lifecycles.append(lifecycle)
                    expected.pop(token_account, None)
                    continue

                inputs = native_inputs.get(token_account, [])
                if not inputs:
                    continue
                total_input = sum(transfer.amount_raw for transfer, _ in inputs)
                first_swap_index = min(index for _, index in inputs)
                decimals = {transfer.decimals for transfer, _ in inputs}
                mints = {transfer.mint for transfer, _ in inputs}
                if len(decimals) != 1 or mints != {NATIVE_MINT}:
                    raise ValueError("inputs wSOL compartilham conta com decimals/mint divergentes")
                funding = decode_wrapped_sol_funding(
                    raw_transaction,
                    token_account=token_account,
                    source_wallet=monitored_wallet,
                    amount_raw=total_input,
                    before_instruction_index=first_swap_index,
                )
                if funding is not None:
                    _add_expected(
                        expected, token_account, NATIVE_MINT,
                        next(iter(decimals)), funding.amount_raw,
                    )
                    wrapped_sol_fundings.append(funding)

        unused_fee_proofs = set(proof_by_mint) - consumed_fee_proof_mints
        if unused_fee_proofs:
            raise ValueError(
                "prova de ausência de taxa não foi consumida por referral Token-2022: "
                + ", ".join(sorted(unused_fee_proofs))
            )

        expected_accounts = set(expected)
        claimed_ids = {id(transfer) for transfer in claimed_transfers}
        inventory_ids = {id(transfer) for transfer in all_transfers}
        missing_claimed = claimed_ids - inventory_ids
        if missing_claimed:
            raise ValueError(
                "inventário completo não contém todas as transferências atribuídas"
            )
        unclaimed = [
            transfer for transfer in all_transfers
            if (
                transfer.source_account in expected_accounts
                or transfer.destination_account in expected_accounts
            )
            and id(transfer) not in claimed_ids
        ]
        if unclaimed:
            details = "; ".join(
                f"ix={transfer.instruction_index}/inner={transfer.inner_instruction_index} "
                f"{transfer.source_account}->{transfer.destination_account} "
                f"mint={transfer.mint} amount={transfer.amount_raw}"
                for transfer in unclaimed
            )
            raise ValueError(
                "há transferências não atribuídas que afetam token accounts do swap: "
                + details
            )

        actual: dict[str, object] = {}
        for delta in balance_deltas.deltas:
            if delta.token_account in actual:
                raise RuntimeError("token account aparece em mais de um delta")
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
                "; ".join(mismatches), tuple(wrapped_sol_fundings), tuple(wrapped_sol_lifecycles),
                tuple(transfer_fee_absence_proofs),
            )
        return DammV2EconomicReconciliation(
            "RECONCILED", len(contexts), tuple(expected_rows),
            "transferências input/output/referral, funding ou lifecycle wSOL quando aplicável, "
            "e deltas agregados por token account conferem com EvtSwap2",
            tuple(wrapped_sol_fundings), tuple(wrapped_sol_lifecycles),
            tuple(transfer_fee_absence_proofs),
        )
    except RuntimeError as exc:
        return DammV2EconomicReconciliation(
            "AMBIGUOUS", len(contexts), (), str(exc),
            tuple(wrapped_sol_fundings), tuple(wrapped_sol_lifecycles),
            tuple(transfer_fee_absence_proofs),
        )
    except (TypeError, ValueError) as exc:
        return DammV2EconomicReconciliation(
            "INCOMPLETE", len(contexts), (), str(exc),
            tuple(wrapped_sol_fundings), tuple(wrapped_sol_lifecycles),
            tuple(transfer_fee_absence_proofs),
        )
