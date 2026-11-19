"""Reconciliação econômica conservadora de swaps Meteora DAMM v2.

A validação é feita em lote por transação: transferências identificadas por
operação são agregadas por token account e comparadas com os deltas pre/post.
Isso evita repartir arbitrariamente deltas líquidos entre swaps sequenciais.

Não cria SwapObservation, BUY/SELL, sinal ou autorização de execução.
"""
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from smart_money_radar.data_sources.damm_v2_transfer_analyzer import (
    DammV2SwapTransferContext,
    DammV2TransferEvidence,
)
from smart_money_radar.data_sources.damm_v2_fee_math import (
    calculate_transfer_fee,
    resolve_damm_fee_mode,
)
from smart_money_radar.data_sources.solana_token_balance_delta_decoder import (
    SolanaTokenBalanceDeltaResult,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    SolanaTokenTransfer,
)
from smart_money_radar.data_sources.token2022_transfer_fee_state import (
    TransferFeeAmountDelta,
    TransferFeeConfigState,
)


EconomicStatus = Literal["RECONCILED", "INCOMPLETE", "AMBIGUOUS"]


@dataclass(frozen=True)
class DammV2ExpectedAccountDelta:
    token_account: str
    mint: str
    decimals: int
    expected_delta_raw: int


@dataclass(frozen=True)
class DammV2ExpectedWithheldFeeDelta:
    """Aumento esperado de withheld fees no extension state da conta destino.

    É derivado do bruto menos o crédito spendable; não é uma leitura observada
    do estado TLV pre/post e, portanto, permanece não verificado nesta camada.
    """

    token_account: str
    mint: str
    expected_withheld_delta_raw: int


@dataclass(frozen=True)
class DammV2ExpectedTransferFee:
    instruction_index: int
    inner_instruction_index: int
    source_account: str
    destination_account: str
    mint: str
    gross_amount_raw: int
    expected_fee_raw: int


@dataclass(frozen=True)
class DammV2EconomicReconciliation:
    status: EconomicStatus
    operation_count: int
    expected_account_deltas: tuple[DammV2ExpectedAccountDelta, ...]
    reason: str
    expected_withheld_fee_deltas: tuple[DammV2ExpectedWithheldFeeDelta, ...] = ()
    withheld_fee_status: Literal[
        "NOT_REQUIRED", "EXPECTED_NOT_VERIFIED", "VERIFIED"
    ] = "NOT_REQUIRED"
    expected_transfer_fees: tuple[DammV2ExpectedTransferFee, ...] = ()
    mint_fee_config_status: Literal[
        "NOT_REQUIRED", "EXPECTED_NOT_VERIFIED", "VERIFIED"
    ] = "NOT_REQUIRED"


@dataclass(frozen=True)
class DammV2MintFeeConfigSnapshot:
    mint: str
    config_state: TransferFeeConfigState | None
    transaction_epoch: int
    transaction_slot: int
    transaction_order: int
    pre_snapshot_order: int
    source: str
    pre_state_ref: str


@dataclass(frozen=True)
class DammV2WithheldFeeSnapshot:
    token_account: str
    mint: str
    decoded_delta: TransferFeeAmountDelta
    transaction_signature: str
    transaction_slot: int
    transaction_order: int
    pre_snapshot_order: int
    post_snapshot_order: int
    source: str
    pre_state_ref: str
    post_state_ref: str


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
        or not 0 < transfer.amount_raw <= (1 << 64) - 1
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
        "TRANSFER_CHECKED", "TRANSFER_CHECKED_WITH_FEE"
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
    monitored_wallet: str,
) -> DammV2EconomicReconciliation:
    """Reconcilia todas as operações DAMM v2 do mesmo payload de transação.

    A lista contexts/evidence deve representar o conjunto completo de swaps
    DAMM v2 analisados naquela transação. Deltas incompletos, evidência ausente,
    CPI não confiável, conta compartilhada com conflito ou divergência bruta/
    líquida fazem o lote falhar fechado.
    """
    if not isinstance(monitored_wallet, str) or not monitored_wallet.strip():
        raise ValueError("monitored_wallet é obrigatório")
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
    expected_owners: dict[str, str] = {}
    expected_withheld: dict[str, dict[str, int | str]] = {}
    expected_transfer_fees: list[DammV2ExpectedTransferFee] = []
    claimed_transfers: set[SolanaTokenTransfer] = set()

    def add_expected_owner(account: str, owner: str) -> None:
        prior = expected_owners.get(account)
        if prior is not None and prior != owner:
            raise ValueError("token account reutilizada com owners esperados divergentes")
        expected_owners[account] = owner

    def add_expected_transfer_fee(transfer: SolanaTokenTransfer, net_amount: int) -> None:
        if transfer.program_id != TOKEN_2022_PROGRAM_ID:
            return
        if (
            isinstance(transfer.instruction_index, bool)
            or not isinstance(transfer.instruction_index, int)
            or transfer.instruction_index < 0
            or isinstance(transfer.inner_instruction_index, bool)
            or not isinstance(transfer.inner_instruction_index, int)
            or transfer.inner_instruction_index < 0
            or not isinstance(transfer.mint, str)
            or not transfer.mint
        ):
            raise ValueError("identidade da transfer fee Token-2022 inválida")
        expected_transfer_fees.append(DammV2ExpectedTransferFee(
            instruction_index=transfer.instruction_index,
            inner_instruction_index=transfer.inner_instruction_index,
            source_account=transfer.source_account,
            destination_account=transfer.destination_account,
            mint=transfer.mint,
            gross_amount_raw=transfer.amount_raw,
            expected_fee_raw=transfer.amount_raw - net_amount,
        ))

    def add_expected_withheld(transfer: SolanaTokenTransfer, net_amount: int) -> None:
        fee = transfer.amount_raw - net_amount
        if fee == 0:
            return
        if transfer.program_id != TOKEN_2022_PROGRAM_ID:
            raise ValueError("transfer fee em programa diferente de Token-2022")
        current = expected_withheld.get(transfer.destination_account)
        if current is None:
            expected_withheld[transfer.destination_account] = {
                "mint": transfer.mint or "",
                "amount": fee,
            }
            return
        if current["mint"] != transfer.mint:
            raise ValueError("token account withheld reutilizada com mint divergente")
        current["amount"] = int(current["amount"]) + fee
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
            main_accounts = (
                accounts.input_token_account,
                accounts.input_vault,
                accounts.output_vault,
                accounts.output_token_account,
            )
            if any(not isinstance(account, str) or not account for account in main_accounts):
                raise ValueError("conta obrigatória do swap ausente")
            if len(set(main_accounts)) != 4:
                raise ValueError("colisão entre contas de usuário e vaults do swap")
            add_expected_owner(accounts.input_token_account, monitored_wallet)
            add_expected_owner(accounts.output_token_account, monitored_wallet)
            add_expected_owner(accounts.token_a_vault, accounts.pool_authority)
            add_expected_owner(accounts.token_b_vault, accounts.pool_authority)
            if (
                event.has_referral
                and event.swap_result.referral_fee > 0
                and accounts.referral_token_account in set(main_accounts)
            ):
                raise ValueError("referral token account colide com outra conta do swap")

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
            add_expected_transfer_fee(input_transfer, input_net)
            add_expected_withheld(input_transfer, input_net)
            _add_expected(
                expected, output_transfer.source_account, output_transfer.mint,
                output_transfer.decimals, -output_transfer.amount_raw,
            )
            _add_expected(
                expected, output_transfer.destination_account, output_transfer.mint,
                output_transfer.decimals, output_net,
            )
            add_expected_transfer_fee(output_transfer, output_net)
            add_expected_withheld(output_transfer, output_net)

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
                add_expected_transfer_fee(referral, referral_net)
                add_expected_withheld(referral, referral_net)

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
            raise ValueError(
                "há transferências não atribuídas que afetam token accounts do swap"
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
        for account, owner in sorted(expected_owners.items()):
            delta = actual.get(account)
            if delta is None:
                mismatches.append(f"delta/owner ausente para {account}")
            elif delta.owner != owner:
                mismatches.append(
                    f"owner diverge para {account}: esperado {owner}, observado {delta.owner}"
                )
        withheld_rows = tuple(
            DammV2ExpectedWithheldFeeDelta(
                token_account=account,
                mint=str(values["mint"]),
                expected_withheld_delta_raw=int(values["amount"]),
            )
            for account, values in sorted(expected_withheld.items())
        )
        if mismatches:
            return DammV2EconomicReconciliation(
                "INCOMPLETE", len(contexts), tuple(expected_rows),
                "; ".join(mismatches),
                withheld_rows,
                "EXPECTED_NOT_VERIFIED" if withheld_rows else "NOT_REQUIRED",
                tuple(expected_transfer_fees),
                "EXPECTED_NOT_VERIFIED" if expected_transfer_fees else "NOT_REQUIRED",
            )
        return DammV2EconomicReconciliation(
            "RECONCILED", len(contexts), tuple(expected_rows),
            "transferências input/output/referral, owners e deltas agregados por token account "
            "conferem com EvtSwap2 para o lote completo; withheld fee permanece apenas esperado",
            withheld_rows,
            "EXPECTED_NOT_VERIFIED" if withheld_rows else "NOT_REQUIRED",
            tuple(expected_transfer_fees),
            "EXPECTED_NOT_VERIFIED" if expected_transfer_fees else "NOT_REQUIRED",
        )
    except RuntimeError as exc:
        return DammV2EconomicReconciliation(
            "AMBIGUOUS", len(contexts), (), str(exc)
        )
    except (TypeError, ValueError) as exc:
        return DammV2EconomicReconciliation(
            "INCOMPLETE", len(contexts), (), str(exc)
        )


def verify_damm_v2_withheld_fee_deltas(
    reconciliation: DammV2EconomicReconciliation,
    snapshots: Sequence[DammV2WithheldFeeSnapshot],
    *,
    transaction_signature: str,
    transaction_slot: int,
    transaction_order: int,
) -> DammV2EconomicReconciliation:
    """Verifies expected withheld increments against provenance-bound TLV snapshots.

    The caller is responsible for obtaining account data immediately before and
    after this exact transaction. Snapshot order values must come from the same
    source ordering domain and prove pre < transaction < post.
    """
    if not isinstance(reconciliation, DammV2EconomicReconciliation):
        raise TypeError("reconciliation inválida")
    if reconciliation.status != "RECONCILED":
        raise ValueError("reconciliação base precisa estar RECONCILED")
    if not isinstance(snapshots, Sequence) or isinstance(snapshots, (str, bytes)):
        raise TypeError("snapshots deve ser uma sequência")
    if any(not isinstance(item, DammV2WithheldFeeSnapshot) for item in snapshots):
        raise TypeError("snapshot withheld inválido")
    if not isinstance(transaction_signature, str) or not transaction_signature.strip():
        raise ValueError("transaction_signature é obrigatório")
    for label, value in (("transaction_slot", transaction_slot), ("transaction_order", transaction_order)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} inválido")

    if not reconciliation.expected_withheld_fee_deltas:
        if snapshots:
            return replace(
                reconciliation,
                status="INCOMPLETE",
                withheld_fee_status="NOT_REQUIRED",
                reason="snapshots withheld fornecidos sem fee withheld esperada",
            )
        return replace(reconciliation, withheld_fee_status="NOT_REQUIRED")

    by_account = {}
    for snapshot in snapshots:
        if snapshot.token_account in by_account:
            return replace(
                reconciliation,
                status="AMBIGUOUS",
                withheld_fee_status="EXPECTED_NOT_VERIFIED",
                reason=f"snapshot withheld duplicado para {snapshot.token_account}",
            )
        by_account[snapshot.token_account] = snapshot

    mismatches = []
    for expected in reconciliation.expected_withheld_fee_deltas:
        snapshot = by_account.get(expected.token_account)
        if snapshot is None:
            mismatches.append(f"snapshot withheld ausente para {expected.token_account}")
            continue
        if snapshot.mint != expected.mint:
            mismatches.append(f"mint do snapshot withheld diverge para {expected.token_account}")
            continue
        if snapshot.transaction_signature != transaction_signature:
            mismatches.append(f"assinatura do snapshot diverge para {expected.token_account}")
            continue
        if (
            isinstance(snapshot.transaction_slot, bool)
            or not isinstance(snapshot.transaction_slot, int)
            or snapshot.transaction_slot != transaction_slot
        ):
            mismatches.append(f"slot do snapshot diverge para {expected.token_account}")
            continue
        if (
            isinstance(snapshot.transaction_order, bool)
            or not isinstance(snapshot.transaction_order, int)
            or snapshot.transaction_order != transaction_order
        ):
            mismatches.append(f"ordem da transação diverge para {expected.token_account}")
            continue
        order_values = (
            snapshot.pre_snapshot_order,
            snapshot.transaction_order,
            snapshot.post_snapshot_order,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in order_values):
            mismatches.append(f"ordem temporal inválida para {expected.token_account}")
            continue
        if not snapshot.pre_snapshot_order < snapshot.transaction_order < snapshot.post_snapshot_order:
            mismatches.append(f"snapshots não provam pre < transação < post para {expected.token_account}")
            continue
        if (
            not isinstance(snapshot.source, str) or not snapshot.source.strip()
            or not isinstance(snapshot.pre_state_ref, str) or not snapshot.pre_state_ref.strip()
            or not isinstance(snapshot.post_state_ref, str) or not snapshot.post_state_ref.strip()
            or snapshot.pre_state_ref == snapshot.post_state_ref
        ):
            mismatches.append(f"proveniência/hash de snapshot ausente para {expected.token_account}")
            continue
        decoded = snapshot.decoded_delta
        if (
            not isinstance(decoded, TransferFeeAmountDelta)
            or not isinstance(decoded.extension_types, tuple)
            or any(isinstance(item, bool) or not isinstance(item, int) for item in decoded.extension_types)
            or 2 not in decoded.extension_types
        ):
            mismatches.append(f"delta TLV TransferFeeAmount ausente/inválido para {expected.token_account}")
            continue
        amounts = (decoded.pre_withheld_amount, decoded.post_withheld_amount)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= (1 << 64) - 1
            for value in amounts
        ):
            mismatches.append(f"quantidade withheld inválida para {expected.token_account}")
            continue
        observed_delta = decoded.post_withheld_amount - decoded.pre_withheld_amount
        if (
            isinstance(decoded.delta, bool)
            or not isinstance(decoded.delta, int)
            or decoded.delta != observed_delta
        ):
            mismatches.append(f"delta TLV inconsistente para {expected.token_account}")
            continue
        if observed_delta != expected.expected_withheld_delta_raw:
            mismatches.append(
                f"withheld diverge para {expected.token_account}: "
                f"esperado {expected.expected_withheld_delta_raw}, observado {observed_delta}"
            )

    if mismatches:
        return replace(
            reconciliation,
            status="INCOMPLETE",
            withheld_fee_status="EXPECTED_NOT_VERIFIED",
            reason="; ".join(mismatches),
        )
    return replace(
        reconciliation,
        withheld_fee_status="VERIFIED",
        reason=reconciliation.reason + "; deltas TLV withheld conferidos com snapshots pre/post vinculados à transação",
    )


def verify_damm_v2_mint_fee_config(
    reconciliation: DammV2EconomicReconciliation,
    snapshots: Sequence[DammV2MintFeeConfigSnapshot],
    *,
    transaction_epoch: int,
    transaction_slot: int,
    transaction_order: int,
) -> DammV2EconomicReconciliation:
    """Verifies each inferred/explicit Token-2022 fee against the mint pre-state.

    A missing TransferFeeConfig extension is represented by config_state=None,
    but only when the adapter decoded the exact pre-transaction mint bytes with
    decode_transfer_fee_config_optional.
    """
    if not isinstance(reconciliation, DammV2EconomicReconciliation):
        raise TypeError("reconciliation inválida")
    if reconciliation.status != "RECONCILED":
        raise ValueError("reconciliação base precisa estar RECONCILED")
    if not isinstance(snapshots, Sequence) or isinstance(snapshots, (str, bytes)):
        raise TypeError("snapshots de mint devem ser uma sequência")
    if any(not isinstance(item, DammV2MintFeeConfigSnapshot) for item in snapshots):
        raise TypeError("snapshot de mint inválido")
    for label, value in (
        ("transaction_epoch", transaction_epoch),
        ("transaction_slot", transaction_slot),
        ("transaction_order", transaction_order),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} inválido")

    if not reconciliation.expected_transfer_fees:
        if snapshots:
            return replace(
                reconciliation,
                status="INCOMPLETE",
                reason="snapshots de mint fornecidos sem transfer fee Token-2022 esperada",
            )
        return replace(reconciliation, mint_fee_config_status="NOT_REQUIRED")

    by_mint = {}
    for snapshot in snapshots:
        if snapshot.mint in by_mint:
            return replace(
                reconciliation,
                status="AMBIGUOUS",
                mint_fee_config_status="EXPECTED_NOT_VERIFIED",
                reason=f"snapshot de mint duplicado para {snapshot.mint}",
            )
        by_mint[snapshot.mint] = snapshot

    mismatches = []
    for expected in reconciliation.expected_transfer_fees:
        snapshot = by_mint.get(expected.mint)
        if snapshot is None:
            mismatches.append(f"snapshot histórico de mint ausente para {expected.mint}")
            continue
        if (
            isinstance(snapshot.transaction_epoch, bool)
            or not isinstance(snapshot.transaction_epoch, int)
            or snapshot.transaction_epoch != transaction_epoch
        ):
            mismatches.append(f"epoch do snapshot diverge para {expected.mint}")
            continue
        if (
            isinstance(snapshot.transaction_slot, bool)
            or not isinstance(snapshot.transaction_slot, int)
            or snapshot.transaction_slot != transaction_slot
        ):
            mismatches.append(f"slot do snapshot diverge para {expected.mint}")
            continue
        if (
            isinstance(snapshot.transaction_order, bool)
            or not isinstance(snapshot.transaction_order, int)
            or snapshot.transaction_order != transaction_order
        ):
            mismatches.append(f"ordem da transação diverge para {expected.mint}")
            continue
        if (
            isinstance(snapshot.pre_snapshot_order, bool)
            or not isinstance(snapshot.pre_snapshot_order, int)
            or snapshot.pre_snapshot_order >= transaction_order
        ):
            mismatches.append(f"prestate do mint não antecede a transação para {expected.mint}")
            continue
        if (
            not isinstance(snapshot.source, str) or not snapshot.source.strip()
            or not isinstance(snapshot.pre_state_ref, str) or not snapshot.pre_state_ref.strip()
        ):
            mismatches.append(f"proveniência do mint ausente para {expected.mint}")
            continue
        if snapshot.config_state is None:
            calculated_fee = 0
        elif isinstance(snapshot.config_state, TransferFeeConfigState):
            rate = snapshot.config_state.fee_for_epoch(transaction_epoch)
            calculated_fee = calculate_transfer_fee(
                expected.gross_amount_raw,
                rate.basis_points,
                rate.maximum_fee,
            )
        else:
            mismatches.append(f"TransferFeeConfig inválido para {expected.mint}")
            continue
        if calculated_fee != expected.expected_fee_raw:
            mismatches.append(
                f"transfer fee diverge para {expected.mint} "
                f"instruction {expected.instruction_index}/{expected.inner_instruction_index}: "
                f"esperado {expected.expected_fee_raw}, calculado {calculated_fee}"
            )

    if mismatches:
        return replace(
            reconciliation,
            status="INCOMPLETE",
            mint_fee_config_status="EXPECTED_NOT_VERIFIED",
            reason="; ".join(mismatches),
        )
    return replace(
        reconciliation,
        mint_fee_config_status="VERIFIED",
        reason=reconciliation.reason + "; transfer fees Token-2022 conferidas com config/epoch prestate",
    )
