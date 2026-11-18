"""Pipeline transacional DAMM v2, sem persistência nem efeitos externos.

Encadeia associação swap/Event CPI, resolução de contas, atribuição de
transferências, snapshots, reconciliação econômica e adaptação aos contratos
de domínio. Qualquer lacuna estrutural ou econômica bloqueia o lote inteiro.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from smart_money_radar.data_sources.damm_v2_accounts import (
    decode_damm_v2_swap_accounts,
)
from smart_money_radar.data_sources.damm_v2_analyzer import (
    DammV2SwapEventAssociation,
    analyze_damm_v2_swap_events,
)
from smart_money_radar.data_sources.damm_v2_economic_reconciliation import (
    DammV2EconomicReconciliation,
    reconcile_damm_v2_economic_batch,
)
from smart_money_radar.data_sources.damm_v2_swap_domain_adapter import (
    DammV2SwapDomainBundle,
    build_damm_v2_swap_domain_bundles,
)
from smart_money_radar.data_sources.damm_v2_transfer_analyzer import (
    DammV2SwapTransferContext,
    DammV2TransferEvidence,
    analyze_damm_v2_transfer_evidence,
)
from smart_money_radar.data_sources.solana_token_balance_delta_decoder import (
    SolanaTokenBalanceDeltaResult,
    decode_solana_token_account_balance_deltas,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SolanaTokenTransfer,
    decode_solana_token_transfers,
)


PipelineStatus = Literal["NO_DAMM_V2_SWAPS", "REJECTED", "RECONCILED"]


@dataclass(frozen=True)
class DammV2TransactionPipelineResult:
    status: PipelineStatus
    reason: str
    associations: tuple[DammV2SwapEventAssociation, ...] = ()
    contexts: tuple[DammV2SwapTransferContext, ...] = ()
    transfers: tuple[SolanaTokenTransfer, ...] = ()
    transfer_evidence: tuple[DammV2TransferEvidence, ...] = ()
    balance_deltas: SolanaTokenBalanceDeltaResult | None = None
    reconciliation: DammV2EconomicReconciliation | None = None
    bundles: tuple[DammV2SwapDomainBundle, ...] = ()


def _payload_and_message(raw_transaction: dict) -> tuple[dict, dict, dict]:
    if not isinstance(raw_transaction, dict):
        raise TypeError("transação RAW deve ser um objeto")
    payload = raw_transaction.get("result", raw_transaction)
    if not isinstance(payload, dict):
        raise ValueError("payload RPC inválido")
    transaction = payload.get("transaction")
    meta = payload.get("meta")
    if not isinstance(transaction, dict) or not isinstance(meta, dict):
        raise ValueError("transaction/meta ausentes ou inválidos")
    message = transaction.get("message")
    if not isinstance(message, dict):
        raise ValueError("transaction.message ausente ou inválido")
    if "err" not in meta:
        raise ValueError("meta.err ausente: execução da transação não comprovada")
    if meta.get("err") is not None:
        raise ValueError("transação falhou on-chain")
    # A ausência de innerInstructions não prova que não houve CPI. DAMM v2
    # pode ser invocado por agregadores; sem esse campo não é seguro liberar
    # a transação como NO_DAMM_V2_SWAPS.
    inner_instructions = meta.get("innerInstructions")
    if not isinstance(inner_instructions, list):
        raise ValueError(
            "meta.innerInstructions ausente/nulo: não é possível comprovar ausência de swaps CPI"
        )
    instructions = message.get("instructions")
    if not isinstance(instructions, list):
        raise ValueError("message.instructions ausente ou inválido")
    return payload, message, meta


def _account_keys(message: dict, meta: dict) -> list[str]:
    raw = message.get("accountKeys")
    if not isinstance(raw, list):
        raise ValueError("message.accountKeys ausente ou inválido")
    parsed = any(isinstance(item, dict) for item in raw)
    if parsed and not all(isinstance(item, dict) for item in raw):
        raise ValueError("message.accountKeys mistura formatos jsonParsed e compiled")
    keys: list[str] = []
    for item in raw:
        key = item.get("pubkey") if isinstance(item, dict) else item
        if not isinstance(key, str) or not key:
            raise ValueError("accountKeys contém chave inválida")
        keys.append(key)
    if not parsed:
        lookups = message.get("addressTableLookups", [])
        if not isinstance(lookups, list):
            raise ValueError("message.addressTableLookups inválido")
        loaded = meta.get("loadedAddresses")
        expected = {"writable": 0, "readonly": 0}
        if lookups:
            if not isinstance(loaded, dict):
                raise ValueError(
                    "meta.loadedAddresses ausente para mensagem com addressTableLookups"
                )
            for lookup in lookups:
                if not isinstance(lookup, dict):
                    raise ValueError("addressTableLookup inválido")
                for field in ("writable", "readonly"):
                    indexes = lookup.get(field + "Indexes")
                    if not isinstance(indexes, list) or any(
                        isinstance(index, bool) or not isinstance(index, int) or index < 0
                        for index in indexes
                    ):
                        raise ValueError(f"addressTableLookup.{field}Indexes inválido")
                    expected[field] += len(indexes)
        else:
            loaded = {} if loaded is None else loaded
        if not isinstance(loaded, dict):
            raise ValueError("meta.loadedAddresses inválido")
        for field in ("writable", "readonly"):
            values = loaded.get(field, [])
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise ValueError(f"loadedAddresses.{field} inválido")
            if lookups and len(values) != expected[field]:
                raise ValueError(
                    f"loadedAddresses.{field} não corresponde à quantidade de índices da lookup table"
                )
            if not lookups and values:
                raise ValueError(
                    "meta.loadedAddresses contém endereços sem addressTableLookups"
                )
            keys.extend(values)
    return keys


def _instruction_for_association(
    association: DammV2SwapEventAssociation,
    message: dict,
    meta: dict,
) -> dict:
    outer_index = association.instruction_index
    if (
        isinstance(outer_index, bool)
        or not isinstance(outer_index, int)
        or outer_index < 0
    ):
        raise ValueError("índice externo da associação inválido")
    outer = message["instructions"]
    if outer_index >= len(outer):
        raise ValueError("índice externo da associação fora do payload")
    inner_index = association.inner_instruction_index
    if inner_index is None:
        instruction = outer[outer_index]
    else:
        if (
            isinstance(inner_index, bool)
            or not isinstance(inner_index, int)
            or inner_index < 0
        ):
            raise ValueError("índice inner da associação inválido")
        groups = meta.get("innerInstructions")
        if not isinstance(groups, list):
            raise ValueError("innerInstructions ausente para swap CPI")
        matches = [
            group for group in groups
            if isinstance(group, dict) and group.get("index") == outer_index
        ]
        if len(matches) != 1:
            raise ValueError("grupo innerInstructions não é único")
        nested = matches[0].get("instructions")
        if not isinstance(nested, list) or inner_index >= len(nested):
            raise ValueError("instrução inner da associação não encontrada")
        instruction = nested[inner_index]
    if not isinstance(instruction, dict):
        raise ValueError("instrução DAMM v2 associada não é um objeto")
    return instruction


def process_damm_v2_transaction(
    raw_transaction: dict,
    *,
    monitored_wallet: str,
    signature: str,
    observed_at: datetime,
    parser_version: str,
) -> DammV2TransactionPipelineResult:
    """Processa um payload getTransaction inteiro em modo fail-closed.

    Não grava no EventStore, não altera checkpoints, não chama RPC e não
    classifica BUY/SELL. A persistência continua sob responsabilidade do
    chamador após validar o resultado.
    """
    if not isinstance(monitored_wallet, str) or not monitored_wallet.strip():
        raise ValueError("monitored_wallet obrigatório")
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError("signature obrigatória")
    if not isinstance(observed_at, datetime):
        raise TypeError("observed_at deve ser datetime")
    if not isinstance(parser_version, str) or not parser_version.strip():
        raise ValueError("parser_version obrigatório")

    associations: tuple[DammV2SwapEventAssociation, ...] = ()
    contexts_tuple: tuple[DammV2SwapTransferContext, ...] = ()
    transfers: tuple[SolanaTokenTransfer, ...] = ()
    evidence: tuple[DammV2TransferEvidence, ...] = ()
    balance_deltas: SolanaTokenBalanceDeltaResult | None = None
    reconciliation: DammV2EconomicReconciliation | None = None
    try:
        payload, message, meta = _payload_and_message(raw_transaction)
        transaction = payload.get("transaction")
        signatures = transaction.get("signatures") if isinstance(transaction, dict) else None
        if (
            not isinstance(signatures, list)
            or not signatures
            or any(not isinstance(item, str) or not item for item in signatures)
            or len(set(signatures)) != len(signatures)
            or signatures[0] != signature
        ):
            raise ValueError(
                "signature deve corresponder à primeira assinatura única do payload"
            )
        # Resolver accountKeys antes da análise evita concluir "sem swap"
        # quando programIdIndex depende de endereços ALT ausentes/incompletos.
        keys = _account_keys(message, meta)
        associations = tuple(analyze_damm_v2_swap_events(raw_transaction))
        if not associations:
            return DammV2TransactionPipelineResult(
                "NO_DAMM_V2_SWAPS",
                "nenhuma instrução swap/Event CPI DAMM v2 foi identificada",
            )

        # A saída do analyzer também contém eventos sem swap correspondente.
        # Não descartá-los: um lote parcialmente associado é rejeitado.
        unresolved = [item for item in associations if item.status != "MATCHED"]
        if unresolved:
            states = ", ".join(item.status for item in unresolved)
            return DammV2TransactionPipelineResult(
                "REJECTED",
                f"associação DAMM v2 incompleta/ambígua: {states}",
                associations=associations,
            )
        if any(item.event is None for item in associations):
            raise ValueError("associação MATCHED sem EvtSwap2")

        contexts = []
        for association in associations:
            instruction = _instruction_for_association(
                association, message, meta
            )
            accounts = decode_damm_v2_swap_accounts(
                instruction, keys, association.event
            )
            contexts.append(DammV2SwapTransferContext(association, accounts))
        contexts_tuple = tuple(contexts)

        transfers = tuple(decode_solana_token_transfers(raw_transaction))
        balance_deltas = decode_solana_token_account_balance_deltas(
            raw_transaction
        )
        evidence = tuple(analyze_damm_v2_transfer_evidence(
            contexts_tuple, transfers
        ))
        if len(evidence) != len(contexts_tuple) or any(
            item.status != "ATTRIBUTED" for item in evidence
        ):
            states = ", ".join(item.status for item in evidence)
            return DammV2TransactionPipelineResult(
                "REJECTED",
                f"transferências DAMM v2 não atribuídas univocamente: {states}",
                associations=associations,
                contexts=contexts_tuple,
                transfers=transfers,
                transfer_evidence=evidence,
                balance_deltas=balance_deltas,
            )

        reconciliation = reconcile_damm_v2_economic_batch(
            contexts_tuple, evidence, balance_deltas, transfers
        )
        if reconciliation.status != "RECONCILED":
            return DammV2TransactionPipelineResult(
                "REJECTED",
                f"reconciliação econômica {reconciliation.status}: "
                f"{reconciliation.reason}",
                associations=associations,
                contexts=contexts_tuple,
                transfers=transfers,
                transfer_evidence=evidence,
                balance_deltas=balance_deltas,
                reconciliation=reconciliation,
            )

        bundles = build_damm_v2_swap_domain_bundles(
            contexts=contexts_tuple,
            transfer_evidence=evidence,
            balance_deltas=balance_deltas,
            reconciliation=reconciliation,
            monitored_wallet=monitored_wallet,
            signature=signature,
            observed_at=observed_at,
            parser_version=parser_version,
        )
        if len(bundles) != len(contexts_tuple):
            raise ValueError(
                "quantidade de bundles de domínio diverge do conjunto de swaps reconciliados"
            )
        return DammV2TransactionPipelineResult(
            "RECONCILED",
            "lote DAMM v2 reconciliado e convertido em bundles de domínio",
            associations=associations,
            contexts=contexts_tuple,
            transfers=transfers,
            transfer_evidence=evidence,
            balance_deltas=balance_deltas,
            reconciliation=reconciliation,
            bundles=bundles,
        )
    except Exception as exc:
        return DammV2TransactionPipelineResult(
            "REJECTED",
            f"{type(exc).__name__}: {exc}",
            associations=associations,
            contexts=contexts_tuple,
            transfers=transfers,
            transfer_evidence=evidence,
            balance_deltas=balance_deltas,
            reconciliation=reconciliation,
        )
