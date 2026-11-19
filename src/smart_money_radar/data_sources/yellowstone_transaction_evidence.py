"""Project a verified Yellowstone transaction into the shared Solana evidence decoders."""

from dataclasses import dataclass

from google.protobuf.message import Message

from smart_money_radar.data_sources.geyser_account_timeline import AccountStateTransition
from smart_money_radar.data_sources.geyser_proto_adapter import _base58_encode
from smart_money_radar.data_sources.geyser_transaction_updates import NormalizedTransactionObservation
from smart_money_radar.data_sources.solana_transaction_evidence_bundle import (
    SolanaTransactionEvidenceBundle,
    build_solana_transaction_evidence_bundle,
)


@dataclass(frozen=True)
class YellowstoneTransactionEvidence:
    """Keep wire identity separate from the derived JSON evidence identity."""

    observation: NormalizedTransactionObservation
    bundle: SolanaTransactionEvidenceBundle
    transaction_accounts: frozenset[str]
    account_transitions: tuple[AccountStateTransition, ...] = ()


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
