"""Project a verified Yellowstone transaction into the shared Solana evidence decoders."""

from dataclasses import dataclass, replace
import hashlib

from google.protobuf.message import Message

from smart_money_radar.data_sources.damm_v2_economic_reconciliation import (
    DammV2EconomicReconciliation,
    DammV2WithheldFeeSnapshot,
    verify_damm_v2_withheld_fee_deltas,
)
from smart_money_radar.data_sources.geyser_account_timeline import AccountStateTransition
from smart_money_radar.data_sources.geyser_proto_adapter import _base58_encode
from smart_money_radar.data_sources.geyser_transaction_updates import NormalizedTransactionObservation
from smart_money_radar.data_sources.solana_transaction_evidence_bundle import (
    SolanaTransactionEvidenceBundle,
    build_solana_transaction_evidence_bundle,
    reconcile_solana_transaction_damm_v2_bundle,
)

from smart_money_radar.data_sources.solana_token_transfer_decoder import TOKEN_2022_PROGRAM_ID
from smart_money_radar.data_sources.token2022_transfer_fee_state import decode_transfer_fee_amount_delta


@dataclass(frozen=True)
class YellowstoneBlockOrder:
    """Transaction index corroborated by a complete block in the same journal."""

    blockhash: str
    transaction_index: int
    block_sequence: int
    block_wire_sha256: str
    previous_transaction_signature: str | None = None


@dataclass(frozen=True)
class YellowstoneTransactionEvidence:
    """Keep wire identity separate from the derived JSON evidence identity."""

    observation: NormalizedTransactionObservation
    bundle: SolanaTransactionEvidenceBundle
    transaction_accounts: frozenset[str]
    account_transitions: tuple[AccountStateTransition, ...] = ()
    provider_reported_finalized: bool = False
    block_order: YellowstoneBlockOrder | None = None

    def reconcile_damm_v2(self, *, monitored_wallet: str) -> DammV2EconomicReconciliation:
        """Reconcile economics and verify withheld fees when adjacent states are proven."""
        if not self.provider_reported_finalized:
            return DammV2EconomicReconciliation(
                "INCOMPLETE", len(self.bundle.damm_v2_associations), (),
                "evidência estrutural ou finalidade do banco Yellowstone insuficiente",
            )
        result = reconcile_solana_transaction_damm_v2_bundle(
            self.bundle, monitored_wallet=monitored_wallet,
        )
        if result.status != "RECONCILED" or not result.expected_withheld_fee_deltas:
            return result
        order = self.block_order
        if order is None or not order.previous_transaction_signature:
            return result
        observation = self.observation
        transitions = {item.pubkey: item for item in self.account_transitions}
        eligible = []
        for expected in result.expected_withheld_fee_deltas:
            transition = transitions.get(expected.token_account)
            if transition is None:
                return result
            pre, post = transition.pre_state, transition.post_state
            if ((pre.slot, pre.bank_id) != (observation.slot, observation.bank_id)
                    or pre.txn_signature != order.previous_transaction_signature
                    or pre.owner != TOKEN_2022_PROGRAM_ID or post.owner != TOKEN_2022_PROGRAM_ID):
                return result
            eligible.append((expected, pre, post))

        transaction_order = 2 * order.transaction_index
        payload_hash = self.bundle.identity.payload_sha256
        snapshots = []
        balances = {item.token_account: item for item in self.bundle.balance_deltas.deltas}
        for expected, pre, post in eligible:
            try:
                if any(_base58_encode(state.data[:32], field="token mint", expected_length=32)
                       != expected.mint for state in (pre, post)):
                    raise ValueError("mint Token-2022 diverge")
                delta = decode_transfer_fee_amount_delta(pre.data, post.data)
                balance = balances.get(expected.token_account)
                if balance is None or (
                    int.from_bytes(pre.data[64:72], "little"),
                    int.from_bytes(post.data[64:72], "little"),
                ) != (balance.pre_amount_raw, balance.post_amount_raw):
                    raise ValueError("saldos Token-2022 dos estados históricos divergem da transação")
            except (TypeError, ValueError) as exc:
                return replace(result, status="INCOMPLETE", reason=str(exc))
            snapshots.append(DammV2WithheldFeeSnapshot(
                token_account=expected.token_account, mint=expected.mint, decoded_delta=delta,
                transaction_signature=observation.transaction_signature, transaction_slot=observation.slot,
                transaction_order=transaction_order,
                pre_snapshot_order=transaction_order - 1, post_snapshot_order=transaction_order + 1,
                source="yellowstone-journal",
                pre_state_ref=f"{observation.stream_id}:{pre.stream_sequence}",
                post_state_ref=f"{observation.stream_id}:{post.stream_sequence}",
                source_id=observation.source_id, transaction_payload_sha256=payload_hash,
                pre_state_sha256=hashlib.sha256(pre.data).hexdigest(),
                post_state_sha256=hashlib.sha256(post.data).hexdigest(),
                pre_state_data=pre.data, post_state_data=post.data,
                ordering_domain_id=observation.ordering_domain_id,
            ))
        return verify_damm_v2_withheld_fee_deltas(
            result, snapshots, transaction_signature=observation.transaction_signature,
            transaction_slot=observation.slot, transaction_order=transaction_order,
            transaction_source_id=observation.source_id, transaction_payload_sha256=payload_hash,
            transaction_ordering_domain_id=observation.ordering_domain_id,
        )


def verify_yellowstone_block_order(
    block: Message, *, observation: NormalizedTransactionObservation,
    block_sequence: int, block_wire_sha256: str,
) -> YellowstoneBlockOrder:
    if (block.slot, block.bank_id) != (observation.slot, observation.bank_id):
        raise ValueError("o bloco diverge do slot ou banco da transação Yellowstone")
    transactions = block.transactions
    indices = {item.index for item in transactions}
    signatures = {item.signature for item in transactions}
    if (len(transactions) != block.executed_transaction_count
            or len(indices) != len(transactions)
            or len(signatures) != len(transactions)
            or any(index >= len(transactions) for index in indices)):
        raise ValueError("bloco Yellowstone incompleto ou com índices/assinaturas duplicados")
    if any(not item.transaction.signatures or item.transaction.signatures[0] != item.signature
           for item in transactions):
        raise ValueError("assinatura de transação diverge dentro do bloco Yellowstone")
    matches = [
        item for item in transactions
        if _base58_encode(item.signature, field="block transaction signature", expected_length=64)
        == observation.transaction_signature
    ]
    if not matches:
        raise ValueError("transação Yellowstone ausente do bloco")
    item, = matches
    if (item.index != observation.transaction_index
            or item.is_vote != observation.is_vote
            or item.transaction.SerializeToString(deterministic=True) != observation.transaction_payload
            or (item.meta.SerializeToString(deterministic=True) if item.HasField("meta") else None)
            != observation.meta_payload):
        raise ValueError("índice ou conteúdo da transação diverge no bloco Yellowstone")
    previous = next((candidate.signature for candidate in transactions
                     if candidate.index + 1 == item.index), None)
    return YellowstoneBlockOrder(
        block.blockhash, item.index, block_sequence, block_wire_sha256,
        _base58_encode(previous, field="previous signature", expected_length=64)
        if previous is not None else None,
    )


def _instruction(item: Message) -> dict:
    projected = {
        "programIdIndex": item.program_id_index,
        "accounts": list(item.accounts),
        "data": _base58_encode(item.data, field="instruction.data"),
    }
    if "stack_height" in item.DESCRIPTOR.fields_by_name and item.HasField("stack_height"):
        projected["stackHeight"] = item.stack_height
    return projected


def _token_balance(item: Message) -> dict:
    amount = item.ui_token_amount
    return {
        "accountIndex": item.account_index,
        "mint": item.mint,
        "owner": item.owner or None,
        "programId": item.program_id or None,
        "uiTokenAmount": {"amount": amount.amount, "decimals": amount.decimals}
        if item.HasField("ui_token_amount") else None,
    }


def _project_meta(info: Message, message: Message) -> dict | None:
    if not info.HasField("meta"):
        return None
    meta = info.meta
    writable = [_base58_encode(key, field="loaded writable", expected_length=32)
                for key in meta.loaded_writable_addresses]
    readonly = [_base58_encode(key, field="loaded readonly", expected_length=32)
                for key in meta.loaded_readonly_addresses]
    lookups = message.address_table_lookups
    if (len(writable) != sum(len(table.writable_indexes) for table in lookups)
            or len(readonly) != sum(len(table.readonly_indexes) for table in lookups)):
        raise ValueError("endereços Yellowstone carregados divergem das tabelas da mensagem")
    account_count = len(message.account_keys) + len(writable) + len(readonly)
    failed = meta.HasField("err")
    if not failed and (len(meta.pre_balances) != account_count or len(meta.post_balances) != account_count):
        return None
    if meta.inner_instructions_none and meta.inner_instructions:
        raise ValueError("indicação de ausência de CPI diverge das instruções Yellowstone")
    return {
        "err": {"yellowstoneErrorHex": meta.err.err.hex()} if failed else None,
        "fee": meta.fee,
        "preBalances": list(meta.pre_balances),
        "postBalances": list(meta.post_balances),
        "loadedAddresses": {"writable": writable, "readonly": readonly},
        "innerInstructions": None if meta.inner_instructions_none else [
            {"index": group.index, "instructions": [_instruction(item) for item in group.instructions]}
            for group in meta.inner_instructions
        ],
        "logMessages": None if meta.log_messages_none else list(meta.log_messages),
        "preTokenBalances": [_token_balance(item) for item in meta.pre_token_balances],
        "postTokenBalances": [_token_balance(item) for item in meta.post_token_balances],
    }


def project_yellowstone_evidence(
    frame: Message, observation: NormalizedTransactionObservation,
) -> YellowstoneTransactionEvidence:
    """Translate the replayed transaction without asserting execution or finality."""
    info = frame.transaction.transaction
    transaction = info.transaction
    if not transaction.HasField("message"):
        raise ValueError("transação Yellowstone sem mensagem Solana")
    message = transaction.message
    signatures = [_base58_encode(value, field="signature", expected_length=64)
                  for value in transaction.signatures]
    keys = [_base58_encode(key, field="account key", expected_length=32)
            for key in message.account_keys]
    if (not message.HasField("header")
            or not 0 < len(signatures) == message.header.num_required_signatures <= len(keys)):
        raise ValueError("cabeçalho Yellowstone incompatível com contas ou assinaturas")
    meta = _project_meta(info, message)
    payload = {
        "slot": frame.transaction.slot,
        "transaction": {
            "signatures": signatures,
            "message": {
                "accountKeys": keys,
                "instructions": [_instruction(item) for item in message.instructions],
            },
        },
        "meta": meta,
    }
    bundle = build_solana_transaction_evidence_bundle(payload, source_id=observation.source_id)
    if (bundle.identity.transaction_signature, bundle.identity.slot) != (
        observation.transaction_signature, observation.slot,
    ):
        raise ValueError("identidade da evidência diverge do envelope Yellowstone")
    loaded = meta["loadedAddresses"] if meta is not None else {"writable": (), "readonly": ()}
    return YellowstoneTransactionEvidence(
        observation, bundle, frozenset((*keys, *loaded["writable"], *loaded["readonly"])),
    )
