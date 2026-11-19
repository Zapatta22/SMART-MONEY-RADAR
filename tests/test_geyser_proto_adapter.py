"""Wire-level adapter tests against a pinned Yellowstone schema subset."""
import base64
import hashlib
from contextlib import redirect_stdout
from io import StringIO
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path
import unittest

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from smart_money_radar.cli import main
from smart_money_radar.data_sources.geyser_proto_adapter import (
    adapt_account_update,
    adapt_subscribe_update,
)

from smart_money_radar.data_sources.yellowstone_grpc import (
    YellowstoneCapture, capture_yellowstone, capture_yellowstone_sessions,
)
from smart_money_radar.data_sources.yellowstone_receiver import (
    YellowstoneFrameReceiver, load_yellowstone_decoder,
)
from smart_money_radar.storage.geyser_account_timeline_projection import (
    SQLiteGeyserAccountTimelineProjection,
)
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore


FIXTURE_DIR = (
    Path(__file__).parent / "fixtures" / "yellowstone" / "v16.1.5+solana.4.3.2"
)
_MANIFEST = json.loads((FIXTURE_DIR / "manifest.json").read_text())
_FIXTURES = {
    name.removesuffix(".b64"): (details["base64"], details["sha256"])
    for name, details in _MANIFEST["fixtures"].items()
}


def _protobuf_update_class():
    """Build a wire-compatible descriptor subset; field numbers match pinned geyser.proto."""
    fd = descriptor_pb2.FileDescriptorProto(
        name="geyser_wire_fixture.proto", package="geyser", syntax="proto2"
    )
    enum = fd.enum_type.add(name="SlotStatus")
    for name, number in (
        ("SLOT_PROCESSED", 0), ("SLOT_CONFIRMED", 1), ("SLOT_FINALIZED", 2),
        ("SLOT_FIRST_SHRED_RECEIVED", 3), ("SLOT_COMPLETED", 4),
        ("SLOT_CREATED_BANK", 5), ("SLOT_DEAD", 6),
    ):
        enum.value.add(name=name, number=number)
    T = descriptor_pb2.FieldDescriptorProto

    def msg(name):
        return fd.message_type.add(name=name)

    def fld(m, name, number, kind, type_name=None, oneof=None):
        f = m.field.add(name=name, number=number, type=kind, label=T.LABEL_OPTIONAL)
        if type_name:
            f.type_name = type_name
        if oneof is not None:
            f.oneof_index = oneof

    info = msg("SubscribeUpdateAccountInfo")
    for n, i, t in (
        ("pubkey", 1, T.TYPE_BYTES), ("lamports", 2, T.TYPE_UINT64),
        ("owner", 3, T.TYPE_BYTES), ("executable", 4, T.TYPE_BOOL),
        ("rent_epoch", 5, T.TYPE_UINT64), ("data", 6, T.TYPE_BYTES),
        ("write_version", 7, T.TYPE_UINT64), ("txn_signature", 8, T.TYPE_BYTES),
    ):
        fld(info, n, i, t)
    account = msg("SubscribeUpdateAccount")
    fld(account, "account", 1, T.TYPE_MESSAGE, ".geyser.SubscribeUpdateAccountInfo")
    fld(account, "slot", 2, T.TYPE_UINT64)
    fld(account, "is_startup", 3, T.TYPE_BOOL)
    fld(account, "bank_id", 4, T.TYPE_UINT64)
    slot = msg("SubscribeUpdateSlot")
    fld(slot, "slot", 1, T.TYPE_UINT64)
    fld(slot, "parent", 2, T.TYPE_UINT64)
    fld(slot, "status", 3, T.TYPE_ENUM, ".geyser.SlotStatus")
    fld(slot, "dead_error", 4, T.TYPE_STRING)
    fld(slot, "bank_id", 5, T.TYPE_UINT64)
    block_meta = msg("SubscribeUpdateBlockMeta")
    for n, i, t in (
        ("slot", 1, T.TYPE_UINT64), ("blockhash", 2, T.TYPE_STRING),
        ("parent_slot", 6, T.TYPE_UINT64), ("parent_blockhash", 7, T.TYPE_STRING),
        ("bank_id", 10, T.TYPE_UINT64),
    ):
        fld(block_meta, n, i, t)
    entry_parent = msg("SubscribeUpdateEntryUpdateParent")
    for n, i, t in (
        ("slot", 1, T.TYPE_UINT64), ("cleared_bank_id", 2, T.TYPE_UINT64),
        ("parent_slot", 3, T.TYPE_UINT64), ("parent_block_id", 4, T.TYPE_BYTES),
    ):
        fld(entry_parent, n, i, t)
    transaction_payload = msg("Transaction")
    transaction_payload.field.add(
        name="signatures", number=1, type=T.TYPE_BYTES, label=T.LABEL_REPEATED
    )
    def repeated(m, name, number, kind, type_name=None):
        fld(m, name, number, kind, type_name)
        m.field[-1].label = T.LABEL_REPEATED

    header = msg("MessageHeader")
    fld(header, "num_required_signatures", 1, T.TYPE_UINT32)
    instruction = msg("CompiledInstruction")
    inner = msg("InnerInstruction")
    for item in (instruction, inner):
        fld(item, "program_id_index", 1, T.TYPE_UINT32)
        fld(item, "accounts", 2, T.TYPE_BYTES)
        fld(item, "data", 3, T.TYPE_BYTES)
    fld(inner, "stack_height", 4, T.TYPE_UINT32)
    inner_group = msg("InnerInstructions")
    fld(inner_group, "index", 1, T.TYPE_UINT32)
    repeated(inner_group, "instructions", 2, T.TYPE_MESSAGE, ".geyser.InnerInstruction")
    lookup = msg("MessageAddressTableLookup")
    fld(lookup, "writable_indexes", 2, T.TYPE_BYTES)
    fld(lookup, "readonly_indexes", 3, T.TYPE_BYTES)
    message = msg("Message")
    fld(message, "header", 1, T.TYPE_MESSAGE, ".geyser.MessageHeader")
    repeated(message, "account_keys", 2, T.TYPE_BYTES)
    repeated(message, "instructions", 4, T.TYPE_MESSAGE, ".geyser.CompiledInstruction")
    repeated(message, "address_table_lookups", 6, T.TYPE_MESSAGE, ".geyser.MessageAddressTableLookup")
    fld(transaction_payload, "message", 2, T.TYPE_MESSAGE, ".geyser.Message")
    error = msg("TransactionError")
    fld(error, "err", 1, T.TYPE_BYTES)
    token_amount = msg("UiTokenAmount")
    fld(token_amount, "decimals", 2, T.TYPE_UINT32)
    fld(token_amount, "amount", 3, T.TYPE_STRING)
    balance = msg("TokenBalance")
    fld(balance, "account_index", 1, T.TYPE_UINT32)
    fld(balance, "mint", 2, T.TYPE_STRING)
    fld(balance, "ui_token_amount", 3, T.TYPE_MESSAGE, ".geyser.UiTokenAmount")
    fld(balance, "owner", 4, T.TYPE_STRING)
    fld(balance, "program_id", 5, T.TYPE_STRING)
    transaction_meta = msg("TransactionStatusMeta")
    fld(transaction_meta, "err", 1, T.TYPE_MESSAGE, ".geyser.TransactionError")
    fld(transaction_meta, "fee", 2, T.TYPE_UINT64)
    repeated(transaction_meta, "pre_balances", 3, T.TYPE_UINT64)
    repeated(transaction_meta, "post_balances", 4, T.TYPE_UINT64)
    repeated(transaction_meta, "inner_instructions", 5, T.TYPE_MESSAGE, ".geyser.InnerInstructions")
    repeated(transaction_meta, "log_messages", 6, T.TYPE_STRING)
    repeated(transaction_meta, "pre_token_balances", 7, T.TYPE_MESSAGE, ".geyser.TokenBalance")
    repeated(transaction_meta, "post_token_balances", 8, T.TYPE_MESSAGE, ".geyser.TokenBalance")
    fld(transaction_meta, "inner_instructions_none", 10, T.TYPE_BOOL)
    fld(transaction_meta, "log_messages_none", 11, T.TYPE_BOOL)
    repeated(transaction_meta, "loaded_writable_addresses", 12, T.TYPE_BYTES)
    repeated(transaction_meta, "loaded_readonly_addresses", 13, T.TYPE_BYTES)
    transaction_info = msg("SubscribeUpdateTransactionInfo")
    fld(transaction_info, "signature", 1, T.TYPE_BYTES)
    fld(transaction_info, "is_vote", 2, T.TYPE_BOOL)
    fld(transaction_info, "transaction", 3, T.TYPE_MESSAGE, ".geyser.Transaction")
    fld(transaction_info, "meta", 4, T.TYPE_MESSAGE, ".geyser.TransactionStatusMeta")
    fld(transaction_info, "index", 5, T.TYPE_UINT64)
    transaction_update = msg("SubscribeUpdateTransaction")
    fld(transaction_update, "transaction", 1, T.TYPE_MESSAGE, ".geyser.SubscribeUpdateTransactionInfo")
    fld(transaction_update, "slot", 2, T.TYPE_UINT64)
    fld(transaction_update, "bank_id", 3, T.TYPE_UINT64)
    block = msg("SubscribeUpdateBlock")
    fld(block, "slot", 1, T.TYPE_UINT64)
    fld(block, "blockhash", 2, T.TYPE_STRING)
    repeated(block, "transactions", 6, T.TYPE_MESSAGE, ".geyser.SubscribeUpdateTransactionInfo")
    fld(block, "executed_transaction_count", 9, T.TYPE_UINT64)
    fld(block, "bank_id", 14, T.TYPE_UINT64)
    msg("SubscribeUpdatePing")
    request = msg("SubscribeRequest")
    ping_request = msg("SubscribeRequestPing")
    fld(ping_request, "id", 1, T.TYPE_INT32)
    fld(request, "ping", 9, T.TYPE_MESSAGE, ".geyser.SubscribeRequestPing")
    request_map = request.nested_type.add(name="SlotsEntry")
    request_map.options.map_entry = True
    slot_filter = msg("SubscribeRequestFilterSlots")
    fld(request_map, "key", 1, T.TYPE_STRING)
    fld(request_map, "value", 2, T.TYPE_MESSAGE, ".geyser.SubscribeRequestFilterSlots")
    repeated(request, "slots", 2, T.TYPE_MESSAGE, ".geyser.SubscribeRequest.SlotsEntry")
    update = msg("SubscribeUpdate")
    update.oneof_decl.add(name="update_oneof")
    update.field.add(name="filters", number=1, type=T.TYPE_STRING, label=T.LABEL_REPEATED)
    for n, i, typ in (
        ("account", 2, "SubscribeUpdateAccount"), ("slot", 3, "SubscribeUpdateSlot"),
        ("block_meta", 7, "SubscribeUpdateBlockMeta"),
        ("transaction", 4, "SubscribeUpdateTransaction"),
        ("block", 5, "SubscribeUpdateBlock"),
        ("entry_update_parent", 13, "SubscribeUpdateEntryUpdateParent"),
        ("ping", 6, "SubscribeUpdatePing"),
    ):
        fld(update, n, i, T.TYPE_MESSAGE, ".geyser." + typ, 0)
    pool = descriptor_pool.DescriptorPool()
    pool.Add(fd)
    return message_factory.GetMessageClass(
        pool.FindMessageTypeByName("geyser.SubscribeUpdate")
    )


_UPDATE = _protobuf_update_class()


def _parse(name):
    encoded, expected_sha = _FIXTURES[name]
    raw = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise AssertionError(f"fixture {name} hash mismatch")
    return _UPDATE.FromString(raw)


def _b58(raw):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    zeroes = len(raw) - len(raw.lstrip(b"\x00"))
    number = int.from_bytes(raw, "big")
    result = ""
    while number:
        number, remainder = divmod(number, 58)
        result = alphabet[remainder] + result
    return "1" * zeroes + result


class YellowstoneProtoAdapterTests(unittest.TestCase):
    def _adapt(self, name, sequence=1):
        return adapt_subscribe_update(
            _parse(name), source_id="yellowstone-validator-a",
            stream_id="connection-a", stream_sequence=sequence,
        )

    def test_account_binary_fields_and_ledger_metadata(self):
        item = self._adapt("account_update")
        self.assertEqual((item.slot, item.bank_id, item.write_version), (123456, 9001, 77))
        self.assertEqual(item.pubkey, _b58(bytes(range(1, 33))))
        self.assertEqual(item.owner, _b58(bytes(range(32, 64))))
        self.assertEqual(item.txn_signature, _b58(bytes(range(64))))
        self.assertEqual(item.data, b"\x01\x02\x00\xffaccount-data")
        self.assertEqual(item.source, "yellowstone-validator-a")

    def test_startup_is_unassigned_and_signature_absence_is_preserved(self):
        item = self._adapt("account_startup")
        self.assertTrue(item.is_startup)
        self.assertIsNone(item.bank_id)
        self.assertIsNone(item.txn_signature)

    def test_created_bank_and_dead_slot_enum_mapping(self):
        created = self._adapt("slot_created_bank")
        dead = self._adapt("slot_dead")
        self.assertEqual(
            (created.status, created.bank_id, created.parent_slot),
            ("SLOT_CREATED_BANK", 9001, 123455),
        )
        self.assertEqual((dead.status, dead.bank_id, dead.dead_error),
                         ("SLOT_DEAD", None, "dead fork"))

    def test_block_meta_and_opaque_entry_parent(self):
        block = self._adapt("block_meta")
        parent = self._adapt("entry_update_parent")
        self.assertEqual(
            (block.blockhash, block.parent_slot, block.parent_blockhash),
            ("blockhash-child", 123455, "blockhash-parent"),
        )
        self.assertEqual(parent.parent_block_id, b"\x00opaque-parent-id\xff")

    def test_transaction_update_uses_pinned_protobuf_shape_and_preserves_wire(self):
        message = _UPDATE()
        signature = bytes(range(64))
        update = message.transaction
        update.slot = 123457
        update.bank_id = 9001
        info = update.transaction
        info.signature = signature
        info.is_vote = True
        info.index = 19
        info.transaction.signatures.append(signature)
        info.transaction.message.SetInParent()
        info.meta.fee = 5000
        raw = message.SerializeToString(deterministic=True)

        # Field order may differ on the wire from deterministic serialization.
        raw += b"\x0a\x00"
        message.filters.append("")
        self.assertNotEqual(raw, message.SerializeToString(deterministic=True))

        item = adapt_subscribe_update(
            message, source_id="yellowstone-validator-a",
            stream_id="connection-a", ordering_domain_id="solana-ordering-a",
            stream_sequence=101, raw_message_bytes=raw,
        )
        self.assertEqual(item.transaction_signature, _b58(signature))
        self.assertEqual(item.slot, 123457)
        self.assertEqual(item.bank_id, 9001)
        self.assertEqual(item.transaction_index, 19)
        self.assertTrue(item.is_vote)
        self.assertEqual(item.transaction_payload, info.transaction.SerializeToString(deterministic=True))
        self.assertEqual(item.meta_payload, info.meta.SerializeToString(deterministic=True))
        self.assertEqual(item.raw_payload, raw)
        self.assertEqual(item.raw_payload_provenance, "WIRE")

    def test_transaction_update_rejects_unrelated_or_malformed_wire(self):
        message = _UPDATE()
        signature = bytes(range(64))
        message.transaction.slot = 10
        info = message.transaction.transaction
        info.signature = signature
        info.transaction.signatures.append(signature)
        raw = message.SerializeToString()
        message.transaction.slot = 11

        for payload, error in ((raw, "diverge"), (b"\xff", "protobuf válido")):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, error):
                adapt_subscribe_update(
                    message, source_id="validator", stream_id="connection",
                    ordering_domain_id="ordering", stream_sequence=1,
                    raw_message_bytes=payload,
                )

    def test_unhandled_or_empty_oneof_is_ignored(self):
        self.assertIsNone(adapt_subscribe_update(
            _UPDATE(), source_id="yellowstone-validator-a",
            stream_id="connection-a", stream_sequence=2,
        ))

    def test_malformed_pubkey_fails_closed(self):
        message = _UPDATE().account
        message.slot = 1
        message.account.pubkey = b"short"
        message.account.owner = bytes(range(32))
        with self.assertRaisesRegex(ValueError, "pubkey"):
            adapt_account_update(
                message, source_id="yellowstone-validator-a",
                stream_id="connection-a", stream_sequence=1,
            )


class YellowstoneFrameReceiverTests(unittest.TestCase):
    @staticmethod
    def receiver(store, *, stream="connection-a", domain="domain-a", source="validator-a"):
        return YellowstoneFrameReceiver(
            store, _UPDATE.FromString, source_id=source, stream_id=stream,
            ordering_domain_id=domain, initial_sequence=40,
        )

    @staticmethod
    def transaction_frame():
        message = _UPDATE()
        message.transaction.slot = 123457
        info = message.transaction.transaction
        info.signature = bytes(range(64))
        info.transaction.signatures.append(info.signature)
        return message.SerializeToString()

    def test_wire_replay_builds_shared_instruction_and_balance_evidence(self):
        from smart_money_radar.data_sources.solana_token_transfer_decoder import (
            SPL_TOKEN_PROGRAM_ID, _decode_base58,
        )

        frame = _UPDATE.FromString(self.transaction_frame())
        info = frame.transaction.transaction
        message = info.transaction.message
        message.header.num_required_signatures = 1
        signer, token_a, token_b, outer_program = (bytes([i]) * 32 for i in range(1, 5))
        message.account_keys.extend((signer, token_a, token_b, outer_program))
        message.address_table_lookups.add(readonly_indexes=b"\x00")
        message.instructions.add(program_id_index=3, accounts=b"\x01\x02", data=b"\x07")
        info.meta.loaded_readonly_addresses.append(_decode_base58(SPL_TOKEN_PROGRAM_ID))
        info.meta.pre_balances.extend([100] * 5)
        info.meta.post_balances.extend([100] * 5)
        info.meta.inner_instructions.add(index=0).instructions.add(
            program_id_index=4, accounts=b"\x01\x02\x00",
            data=b"\x03" + (9).to_bytes(8, "little"), stack_height=2,
        )
        for snapshots, amounts in (
            (info.meta.pre_token_balances, (20, 1)),
            (info.meta.post_token_balances, (11, 10)),
        ):
            for index, amount in enumerate(amounts, start=1):
                entry = snapshots.add(
                    account_index=index, mint=_b58(bytes([6]) * 32),
                    owner=_b58(signer), program_id=SPL_TOKEN_PROGRAM_ID,
                )
                entry.ui_token_amount.amount = str(amount)
                entry.ui_token_amount.decimals = 6

        store = SQLiteGeyserRawStore(":memory:")
        self.addCleanup(store.close)
        receiver = self.receiver(store)
        raw = frame.SerializeToString()
        receipt = receiver.receive(raw, stream_sequence=40)
        item, = receiver.replay_transaction_evidence()
        self.assertEqual(item.observation.payload_sha256, receipt.payload_sha256)
        self.assertNotEqual(item.bundle.identity.payload_sha256, receipt.payload_sha256)
        self.assertTrue(item.bundle.structurally_complete)
        transfer, = item.bundle.transfers
        self.assertEqual(transfer.amount_raw, 9)
        self.assertEqual([part.delta_raw for part in item.bundle.balance_deltas.deltas], [-9, 9])

        info.meta.inner_instructions_none = True
        info.meta.ClearField("inner_instructions")
        receiver.receive(frame.SerializeToString(), stream_sequence=41)
        self.assertFalse(list(receiver.replay_transaction_evidence())[-1].bundle.structurally_complete)

        info.ClearField("meta")
        receiver.receive(frame.SerializeToString(), stream_sequence=42)
        self.assertFalse(list(receiver.replay_transaction_evidence())[-1].bundle.structurally_complete)

        info.meta.err.err = b"failed"
        info.meta.loaded_readonly_addresses.append(_decode_base58(SPL_TOKEN_PROGRAM_ID))
        receiver.receive(frame.SerializeToString(), stream_sequence=43)
        failed = list(receiver.replay_transaction_evidence())[-1].bundle
        self.assertFalse(failed.structurally_complete)
        self.assertEqual(failed.transfers, ())

        info.meta.ClearField("loaded_readonly_addresses")
        receiver.receive(frame.SerializeToString(), stream_sequence=44)
        with self.assertRaisesRegex(ValueError, "divergem das tabelas"):
            list(receiver.replay_transaction_evidence())

    def test_transaction_links_only_finalized_account_writes_in_its_bank_and_session(self):
        account_frame = _parse("account_update")
        account = account_frame.account
        account.account.ClearField("txn_signature")
        transaction_frame = _UPDATE.FromString(self.transaction_frame())
        transaction = transaction_frame.transaction
        transaction.slot = account.slot
        transaction.bank_id = account.bank_id
        info = transaction.transaction
        info.transaction.message.header.num_required_signatures = 1
        info.transaction.message.account_keys.append(account.account.pubkey)
        info.meta.pre_balances.append(1)
        info.meta.post_balances.append(1)

        store = SQLiteGeyserRawStore(":memory:")
        self.addCleanup(store.close)
        receiver = self.receiver(store)
        receiver.receive(account_frame.SerializeToString(), stream_sequence=40)
        receiver.receive(transaction_frame.SerializeToString(), stream_sequence=41)
        account.account.txn_signature = info.signature
        account.account.write_version += 1
        receiver.receive(account_frame.SerializeToString(), stream_sequence=42)

        self.assertEqual(receiver.transaction_evidence_at(41).account_transitions, ())
        slot_frame = _UPDATE()
        slot_frame.slot.slot = account.slot
        slot_frame.slot.bank_id = account.bank_id
        slot_frame.slot.status = 2
        receiver.receive(slot_frame.SerializeToString(), stream_sequence=43)
        evidence = receiver.transaction_evidence_at(41)
        transition, = evidence.account_transitions
        self.assertEqual(transition.post_state.stream_sequence, 42)
        self.assertEqual(transition.pre_state.stream_sequence, 40)
        self.assertEqual(transition.evidence_classification, "BANK_PROVIDER_REPORTED_FINALIZED")

        for stream, domain, bank_id in (
            ("other-connection", "other-domain", transaction.bank_id),
            ("unscoped", "unscoped-domain", 0),
            ("sibling", "sibling-domain", transaction.bank_id + 1),
        ):
            isolated = self.receiver(store, stream=stream, domain=domain)
            transaction.bank_id = bank_id
            isolated.receive(transaction_frame.SerializeToString(), stream_sequence=40)
            if stream != "other-connection":
                account.account.ClearField("txn_signature")
                account.account.write_version += 1
                isolated.receive(account_frame.SerializeToString(), stream_sequence=41)
                account.account.txn_signature = info.signature
                account.account.write_version += 1
                isolated.receive(account_frame.SerializeToString(), stream_sequence=42)
                isolated.receive(slot_frame.SerializeToString(), stream_sequence=43)
            self.assertEqual(isolated.transaction_evidence_at(40).account_transitions, ())

        transaction.bank_id = account.bank_id
        receiver.receive(transaction_frame.SerializeToString(), stream_sequence=44)
        with self.assertRaisesRegex(ValueError, "assinatura Yellowstone ambígua"):
            receiver.transaction_evidence_at(41)

    def test_cli_inspects_archived_evidence_without_write_or_helius(self):
        descriptors = descriptor_pb2.FileDescriptorSet()
        _UPDATE.DESCRIPTOR.file.CopyToProto(descriptors.file.add())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "journal #1.sqlite"
            descriptor = root / "yellowstone.desc"
            descriptor.write_bytes(descriptors.SerializeToString())
            store = SQLiteGeyserRawStore(database)
            frame = _UPDATE.FromString(self.transaction_frame())
            info = frame.transaction.transaction
            info.transaction.message.header.num_required_signatures = 1
            info.transaction.message.account_keys.append(bytes([7]) * 32)
            info.meta.pre_balances.append(1)
            info.meta.post_balances.append(1)
            receiver = self.receiver(store)
            receipt = receiver.receive(frame.SerializeToString(), stream_sequence=40)
            store.close()
            before = hashlib.sha256(database.read_bytes()).hexdigest()
            args = [
                "geyser-evidence", str(database), "--descriptor", str(descriptor),
                "--source", "validator-a", "--stream", "connection-a", "--domain", "domain-a",
                "--sequence", "40",
            ]
            output = StringIO()
            with patch("smart_money_radar.cli.HeliusSettings.from_environment",
                       side_effect=AssertionError("offline")), redirect_stdout(output):
                main([*args, "--damm-wallet", "fixture-wallet"])
            report = json.loads(output.getvalue())
            self.assertEqual(report["wire_sha256"], receipt.payload_sha256)
            self.assertTrue(report["structurally_complete"])
            self.assertEqual(report["account_transitions"], [])
            self.assertEqual(report["damm_v2"]["status"], "INCOMPLETE")
            self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before)

            with self.assertRaisesRegex(SystemExit, "nenhuma transação"):
                main([*args[:-1], "41"])
            absent = root / "missing.sqlite"
            with self.assertRaises(SystemExit):
                main([args[0], str(absent), *args[2:]])
            self.assertFalse(absent.exists())

    def test_bounded_grpc_capture_sequences_ping_and_reconnects_under_fresh_domains(self):
        descriptors = descriptor_pb2.FileDescriptorSet()
        _UPDATE.DESCRIPTOR.file.CopyToProto(descriptors.file.add())
        descriptor_bytes = descriptors.SerializeToString()
        request_type = message_factory.GetMessageClassesForFiles(
            [_UPDATE.DESCRIPTOR.file.name], _UPDATE.DESCRIPTOR.file.pool
        )["geyser.SubscribeRequest"]
        ping = _UPDATE()
        ping.ping.SetInParent()
        ping_bytes = ping.SerializeToString()
        transaction = self.transaction_frame()
        channel = MagicMock()
        cancelled = MagicMock()

        def stream(requests, *, timeout, metadata):
            self.assertEqual(timeout, 17)
            self.assertEqual(metadata, (("x-token", "fixture-token"),))

            def frames():
                self.assertIn("audit", request_type.FromString(next(requests)).slots)
                yield ping_bytes
                self.assertEqual(request_type.FromString(next(requests)).ping.id, 1)
                yield transaction
                self.fail("frame limit should cancel before reading another delivery")

            return Call(frames())

        class Call:
            def __init__(self, generator):
                self.generator = generator

            def __iter__(self):
                return self.generator

            def cancel(self):
                cancelled()

        channel.stream_stream.return_value.side_effect = stream
        channel.__enter__.return_value = channel
        tls = object()
        grpc = SimpleNamespace(
            secure_channel=MagicMock(return_value=channel),
            ssl_channel_credentials=MagicMock(return_value=tls),
            RpcError=RuntimeError,
        )
        store = SQLiteGeyserRawStore(":memory:")
        self.addCleanup(store.close)
        with patch.dict("sys.modules", {"grpc": grpc}):
            first, second = [capture_yellowstone(
                store, target="provider.example:443", source_id="validator",
                descriptor=descriptor_bytes, subscription={"slots": {"audit": {}}},
                token="fixture-token", max_frames=2, timeout=17,
            ) for _ in range(2)]
        grpc.secure_channel.assert_called_with("provider.example:443", tls)
        channel.stream_stream.assert_called_with("/geyser.Geyser/Subscribe")
        self.assertEqual(cancelled.call_count, 2)
        self.assertNotEqual(first.ordering_domain_id, second.ordering_domain_id)
        self.assertNotEqual(first.stream_id, second.stream_id)
        for capture in (first, second):
            self.assertEqual((capture.frame_count, capture.outcome), (2, "frame_limit"))
            self.assertEqual(
                list(store.iter_wire_frames("validator", capture.stream_id, capture.ordering_domain_id)),
                [(0, ping_bytes), (1, transaction)],
            )

    def test_capture_retries_only_transient_failure_and_shares_budgets(self):
        first = YellowstoneCapture("stream-a", "domain-a", 3, "unavailable")
        second = YellowstoneCapture("stream-b", "domain-b", 2, "permission_denied")
        module = "smart_money_radar.data_sources.yellowstone_grpc"
        with (
            patch(f"{module}.capture_yellowstone", side_effect=(first, second)) as capture,
            patch(f"{module}.monotonic", side_effect=(0, 0, 2, 3)),
            patch(f"{module}.sleep") as wait,
        ):
            sessions = capture_yellowstone_sessions(
                None, target="provider.example:443", source_id="validator",
                descriptor=b"", subscription={}, max_frames=10, timeout=20, max_attempts=3,
            )
        self.assertEqual(sessions, (first, second))
        self.assertEqual([call.kwargs["max_frames"] for call in capture.call_args_list], [10, 7])
        self.assertEqual([call.kwargs["timeout"] for call in capture.call_args_list], [20, 17])
        wait.assert_called_once_with(1)

    def test_reconciles_damm_economics_only_after_finalized_wire_bank(self):
        self._reconcile_archived_damm_swap(referral=False)

    def test_reconciles_damm_referral_from_archived_mint_states(self):
        self._reconcile_archived_damm_swap(referral=True)

    def _reconcile_archived_damm_swap(self, *, referral):
        from smart_money_radar.data_sources.solana_token_transfer_decoder import _decode_base58
        from dataclasses import replace
        from test_damm_v2_economic_reconciliation import _mint_account_data, _withheld_account_data
        from test_solana_transaction_evidence_bundle import _damm_complete_transaction

        payload = _damm_complete_transaction(referral=referral)["result"]
        rpc_message = payload["transaction"]["message"]
        names = rpc_message["accountKeys"]
        unique = list(dict.fromkeys(names))
        addresses = {}
        for index, name in enumerate(unique, start=1):
            try:
                decoded = _decode_base58(name)
            except ValueError:
                decoded = b""
            addresses[name] = decoded if len(decoded) == 32 else bytes([index]) * 32

        frame = _UPDATE.FromString(self.transaction_frame())
        tx = frame.transaction
        tx.bank_id = 10
        info = tx.transaction
        info.index = 1
        message = info.transaction.message
        message.header.num_required_signatures = 1
        message.account_keys.extend(addresses.values())

        def indices(values):
            return bytes(unique.index(names[value]) for value in values)

        outer, = rpc_message["instructions"]
        message.instructions.add(
            program_id_index=unique.index(outer["programId"]),
            accounts=indices(outer["accounts"]), data=_decode_base58(outer["data"]),
        )
        inner = info.meta.inner_instructions.add(index=0)
        for item in payload["meta"]["innerInstructions"][0]["instructions"]:
            inner.instructions.add(
                program_id_index=unique.index(item["programId"]), accounts=indices(item["accounts"]),
                data=_decode_base58(item["data"]), stack_height=item["stackHeight"],
            )
        info.meta.pre_balances.extend([100] * len(unique))
        info.meta.post_balances.extend([100] * len(unique))
        wallet = _b58(bytes([99]) * 32)
        for field, rows in (
            (info.meta.pre_token_balances, payload["meta"]["preTokenBalances"]),
            (info.meta.post_token_balances, payload["meta"]["postTokenBalances"]),
        ):
            for row in rows:
                entry = field.add(
                    account_index=indices([row["accountIndex"]])[0], mint=_b58(addresses[row["mint"]]),
                    owner=wallet if row["owner"] == "wallet" else _b58(addresses[row["owner"]]),
                )
                entry.ui_token_amount.amount = row["uiTokenAmount"]["amount"]
                entry.ui_token_amount.decimals = row["uiTokenAmount"]["decimals"]

        slot = _UPDATE()
        slot.slot.slot = tx.slot
        slot.slot.bank_id = tx.bank_id
        slot.slot.status = 2
        store = SQLiteGeyserRawStore(":memory:")
        self.addCleanup(store.close)
        receiver = self.receiver(store)
        receiver.receive(frame.SerializeToString(), stream_sequence=40)
        evidence = receiver.transaction_evidence_at(40)
        self.assertEqual(evidence.reconcile_damm_v2(monitored_wallet=wallet).status, "INCOMPLETE")
        receiver.receive(slot.SerializeToString(), stream_sequence=41)
        evidence = receiver.transaction_evidence_at(40)
        result = evidence.reconcile_damm_v2(monitored_wallet=wallet)
        if referral:
            self.assertEqual(result.status, "INCOMPLETE")
            self.assertIn("mint prestate", result.reason)
        else:
            self.assertEqual(result.status, "RECONCILED", result.reason)
            self.assertEqual(result.operation_count, 1)
            self.assertEqual(result.withheld_fee_status, "EXPECTED_NOT_VERIFIED")
            self.assertEqual(result.mint_fee_config_status, "EXPECTED_NOT_VERIFIED")

        block_frame = _UPDATE()
        block = block_frame.block
        block.slot, block.bank_id = tx.slot, tx.bank_id
        block.blockhash = _b58(bytes([51]) * 32)
        block.executed_transaction_count = 2
        previous_signature = bytes([91]) * 64
        previous = block.transactions.add(signature=previous_signature, index=0)
        previous.transaction.signatures.append(previous_signature)
        block.transactions.add().CopyFrom(info)
        receiver.receive(block_frame.SerializeToString(), stream_sequence=42)
        meta = _UPDATE()
        meta.block_meta.slot, meta.block_meta.bank_id = tx.slot, tx.bank_id
        meta.block_meta.blockhash = block.blockhash
        meta.block_meta.parent_slot = tx.slot - 1
        meta.block_meta.parent_blockhash = _b58(bytes([52]) * 32)
        receiver.receive(meta.SerializeToString(), stream_sequence=43)

        if referral:
            for sequence, name, rate in ((44, names[6], 500), (45, names[7], 1000)):
                mint_frame = _parse("account_update")
                mint_frame.account.slot, mint_frame.account.bank_id = tx.slot, tx.bank_id
                mint = mint_frame.account.account
                mint.pubkey = addresses[name]
                mint.owner = _decode_base58(names[9])
                mint.txn_signature = previous_signature
                mint.write_version = sequence
                mint.data = _mint_account_data(basis_points=rate)
                receiver.receive(mint_frame.SerializeToString(), stream_sequence=sequence)
            evidence = receiver.transaction_evidence_at(40, block_sequence=42)
            self.assertEqual(evidence.reconcile_damm_v2(monitored_wallet=wallet).status, "INCOMPLETE")
            result = evidence.reconcile_damm_v2(monitored_wallet=wallet, transaction_epoch=0)
            self.assertEqual(result.status, "RECONCILED", result.reason)
            self.assertEqual(result.mint_fee_config_status, "VERIFIED")
            fee, = [item for item in result.expected_transfer_fees if item.fee_source == "MINT_PRESTATE"]
            self.assertEqual(fee.expected_fee_raw, 1)
            return

        sequence = 44
        balances = {item.token_account: item for item in evidence.bundle.balance_deltas.deltas}
        for expected in result.expected_withheld_fee_deltas:
            account_frame = _parse("account_update")
            account_frame.account.slot = tx.slot
            account_frame.account.bank_id = tx.bank_id
            account = account_frame.account.account
            account.pubkey = _decode_base58(expected.token_account)
            account.owner = _decode_base58(names[9])
            for offset, signature, amount in (
                (0, previous_signature, 2),
                (1, info.signature, 2 + expected.expected_withheld_delta_raw),
            ):
                account.write_version = sequence + offset
                account.txn_signature = signature
                balance = balances[expected.token_account]
                raw = bytearray(_withheld_account_data(amount))
                raw[:32] = _decode_base58(expected.mint)
                spendable = balance.pre_amount_raw if offset == 0 else balance.post_amount_raw
                raw[64:72] = spendable.to_bytes(8, "little")
                account.data = bytes(raw)
                receiver.receive(account_frame.SerializeToString(), stream_sequence=sequence + offset)
            sequence += 2

        evidence = receiver.transaction_evidence_at(40, block_sequence=42)
        verified = evidence.reconcile_damm_v2(monitored_wallet=wallet)
        self.assertEqual(verified.status, "RECONCILED", verified.reason)
        self.assertEqual(verified.withheld_fee_status, "VERIFIED")
        self.assertEqual(verified.mint_fee_config_status, "EXPECTED_NOT_VERIFIED")

        unproven = replace(evidence, block_order=replace(
            evidence.block_order, previous_transaction_signature=None,
        ))
        self.assertEqual(
            unproven.reconcile_damm_v2(monitored_wallet=wallet).withheld_fee_status,
            "EXPECTED_NOT_VERIFIED",
        )
        transition, *other_transitions = evidence.account_transitions
        changed = replace(transition.post_state, data=(
            transition.post_state.data[:-8] + transition.pre_state.data[-8:]
        ))
        inconsistent = replace(evidence, account_transitions=(
            replace(transition, post_state=changed), *other_transitions,
        ))
        mismatch = inconsistent.reconcile_damm_v2(monitored_wallet=wallet)
        self.assertEqual(mismatch.status, "INCOMPLETE")
        self.assertIn("withheld diverge", mismatch.reason)

        mint_frame = _parse("account_update")
        mint_frame.account.slot, mint_frame.account.bank_id = tx.slot, tx.bank_id
        mint = mint_frame.account.account
        mint.owner = _decode_base58(names[9])
        mint.txn_signature = previous_signature
        for name, rate in ((names[6], 500), (names[7], None)):
            mint.pubkey = addresses[name]
            mint.write_version = sequence
            mint.data = _mint_account_data(basis_points=rate, newer_basis_points=900 if rate else None)
            receiver.receive(mint_frame.SerializeToString(), stream_sequence=sequence)
            sequence += 1
        evidence = receiver.transaction_evidence_at(40, block_sequence=42)
        from smart_money_radar.data_sources.solana_transaction_evidence_bundle import (
            reconcile_solana_transaction_damm_v2_bundle,
        )

        with patch(
            "smart_money_radar.data_sources.yellowstone_transaction_evidence."
            "reconcile_solana_transaction_damm_v2_bundle",
            wraps=reconcile_solana_transaction_damm_v2_bundle,
        ) as reconcile:
            verified = evidence.reconcile_damm_v2(monitored_wallet=wallet, transaction_epoch=0)
        arguments = reconcile.call_args.kwargs
        self.assertEqual(arguments["transaction_epoch"], 0)
        self.assertEqual(arguments["transaction_order"], 2)
        self.assertEqual(len(arguments["mint_fee_snapshots"]), 2)
        self.assertEqual(arguments["transaction_ordering_domain_id"], "domain-a")
        self.assertEqual(verified.status, "RECONCILED", verified.reason)
        self.assertEqual(verified.mint_fee_config_status, "VERIFIED")
        wrong_epoch = evidence.reconcile_damm_v2(monitored_wallet=wallet, transaction_epoch=10)
        self.assertEqual(wrong_epoch.status, "INCOMPLETE")
        self.assertEqual(wrong_epoch.mint_fee_config_status, "EXPECTED_NOT_VERIFIED")
        self.assertEqual(verified.withheld_fee_status, "VERIFIED")

        slot.slot.status = 6
        receiver.receive(slot.SerializeToString(), stream_sequence=sequence)
        invalidated = receiver.transaction_evidence_at(40)
        self.assertEqual(invalidated.reconcile_damm_v2(monitored_wallet=wallet).status, "INCOMPLETE")

    def test_block_order_uses_membership_and_not_wire_sequence(self):
        frame = _UPDATE.FromString(self.transaction_frame())
        tx = frame.transaction
        tx.bank_id = 25
        info = tx.transaction
        info.index = 0
        info.transaction.message.header.num_required_signatures = 1
        info.transaction.message.account_keys.append(bytes([1]) * 32)
        info.meta.pre_balances.append(5)
        info.meta.post_balances.append(5)
        block_frame = _UPDATE()
        block = block_frame.block
        block.slot, block.bank_id = tx.slot, tx.bank_id
        block.blockhash = _b58(bytes([9]) * 32)
        block.executed_transaction_count = 1
        block.transactions.add().CopyFrom(info)

        meta = _UPDATE()
        meta.block_meta.slot, meta.block_meta.bank_id = tx.slot, tx.bank_id
        meta.block_meta.blockhash = block.blockhash
        meta.block_meta.parent_slot = tx.slot - 1
        meta.block_meta.parent_blockhash = _b58(bytes([8]) * 32)
        finalized = _UPDATE()
        finalized.slot.slot, finalized.slot.bank_id = tx.slot, tx.bank_id
        finalized.slot.status = 2

        store = SQLiteGeyserRawStore(":memory:")
        self.addCleanup(store.close)
        receiver = self.receiver(store)
        wire = receiver.receive(block_frame.SerializeToString(), stream_sequence=40)
        receiver.receive(frame.SerializeToString(), stream_sequence=41)
        receiver.receive(meta.SerializeToString(), stream_sequence=42)
        with self.assertRaisesRegex(ValueError, "sem finalidade"):
            receiver.transaction_evidence_at(41, block_sequence=40)
        receiver.receive(finalized.SerializeToString(), stream_sequence=43)

        evidence = receiver.transaction_evidence_at(41, block_sequence=40)
        self.assertEqual(evidence.block_order.transaction_index, 0)
        self.assertEqual(evidence.block_order.block_sequence, 40)
        self.assertEqual(evidence.block_order.block_wire_sha256, wire.payload_sha256)
        self.assertIsNone(receiver.transaction_evidence_at(41).block_order)

        block.executed_transaction_count = 2
        receiver.receive(block_frame.SerializeToString(), stream_sequence=44)
        with self.assertRaisesRegex(ValueError, "bloco Yellowstone incompleto"):
            receiver.transaction_evidence_at(41, block_sequence=44)

        block.executed_transaction_count = 1
        block.transactions[0].meta.fee = 9000
        receiver.receive(block_frame.SerializeToString(), stream_sequence=45)
        with self.assertRaisesRegex(ValueError, "conteúdo da transação diverge"):
            receiver.transaction_evidence_at(41, block_sequence=45)

        block.blockhash = _b58(bytes([6]) * 32)
        receiver.receive(block_frame.SerializeToString(), stream_sequence=46)
        with self.assertRaisesRegex(ValueError, "hash do bloco diverge"):
            receiver.transaction_evidence_at(41, block_sequence=46)

    def test_descriptor_loader_uses_the_supplied_subscribe_update_schema(self):
        descriptors = descriptor_pb2.FileDescriptorSet()
        _UPDATE.DESCRIPTOR.file.CopyToProto(descriptors.file.add())
        decode = load_yellowstone_decoder(descriptors.SerializeToString())
        raw = self.transaction_frame()
        self.assertEqual(decode(raw).WhichOneof("update_oneof"), "transaction")
        with self.assertRaisesRegex(ValueError, "SubscribeUpdate"):
            load_yellowstone_decoder(b"")

    def test_shared_sequence_replays_account_transaction_and_control_after_restart(self):
        account = _parse("account_update").SerializeToString()
        transaction = self.transaction_frame()
        ping = _UPDATE()
        ping.ping.SetInParent()
        control = ping.SerializeToString()

        with TemporaryDirectory() as directory:
            database = Path(directory) / "wire.sqlite3"
            store = SQLiteGeyserRawStore(database)
            receiver = self.receiver(store)
            first = receiver.receive(account, stream_sequence=40)
            self.assertFalse(first.interrupted)
            later = receiver.receive(control, stream_sequence=42)
            self.assertTrue(later.interrupted)
            self.assertEqual(later.contiguous_sequence, 40)
            with self.assertRaisesRegex(ValueError, "interrompido"):
                list(receiver.replay())
            store.close()

            store = SQLiteGeyserRawStore(database)
            receiver = self.receiver(store)
            recovered = receiver.receive(transaction, stream_sequence=41)
            self.assertEqual(recovered.contiguous_sequence, 42)
            self.assertFalse(recovered.interrupted)
            self.assertEqual(store.get_wire_frame(later.frame_id), control)
            self.assertEqual(recovered.payload_sha256, hashlib.sha256(transaction).hexdigest())
            self.assertEqual(receiver.receive(transaction, stream_sequence=41).status, "duplicate")
            events = list(receiver.replay())
            self.assertEqual([sequence for sequence, _ in events], [40, 41, 42])
            self.assertEqual(events[0][1].stream_sequence, 40)
            self.assertEqual(events[1][1].ordering_key, ("validator-a", "domain-a", 41))
            self.assertEqual(events[1][1].raw_payload, transaction)
            self.assertIsNone(events[2][1])

            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE geyser_wire_frames SET payload_bytes = ? WHERE frame_id = ?",
                    (b"tampered", recovered.frame_id),
                )
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                store.get_wire_frame(recovered.frame_id)
            with self.assertRaisesRegex(ValueError, "integridade"):
                list(receiver.replay())

    def test_collision_is_retained_and_reconnect_requires_fresh_domain(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "wire.sqlite3"
            store = SQLiteGeyserRawStore(database)
            receiver = self.receiver(store)
            raw = self.transaction_frame()
            first = receiver.receive(raw, stream_sequence=40)
            changed = _UPDATE.FromString(raw)
            changed.filters.append("another filter")
            other = changed.SerializeToString()
            collision = receiver.receive(other, stream_sequence=40)
            self.assertEqual(collision.status, "collision")
            self.assertTrue(collision.interrupted)
            self.assertEqual(store.get_wire_frame(first.frame_id), raw)
            self.assertEqual(store.get_wire_frame(collision.frame_id), other)
            store.close()

            store = SQLiteGeyserRawStore(database)
            receiver = self.receiver(store)
            self.assertTrue(receiver.receive(raw, stream_sequence=40).tainted)
            with self.assertRaisesRegex(ValueError, "anomalia histórica"):
                list(receiver.replay())
            with self.assertRaisesRegex(ValueError, "outro baseline"):
                self.receiver(store, stream="connection-b")
            with self.assertRaisesRegex(ValueError, "outro baseline"):
                self.receiver(store, domain="domain-b")
            reconnected = self.receiver(store, stream="connection-b", domain="domain-b")
            self.assertFalse(reconnected.receive(raw, stream_sequence=40).interrupted)
            self.assertEqual(list(reconnected.replay())[0][1].ordering_key,
                             ("validator-a", "domain-b", 40))
            separate_source = self.receiver(store, source="validator-b")
            self.assertFalse(separate_source.receive(raw, stream_sequence=40).interrupted)

    def test_timeline_replay_preserves_account_coordinates_across_non_account_frames(self):
        store = SQLiteGeyserRawStore(":memory:")
        self.addCleanup(store.close)
        receiver = self.receiver(store)
        message = _parse("account_update")
        receiver.receive(message.SerializeToString(), stream_sequence=40)

        ping = _UPDATE()
        ping.ping.SetInParent()
        receiver.receive(self.transaction_frame(), stream_sequence=41)
        receiver.receive(ping.SerializeToString(), stream_sequence=42)
        receiver.receive(_parse("slot_created_bank").SerializeToString(), stream_sequence=43)

        message.account.slot += 1
        message.account.account.write_version += 1
        receiver.receive(message.SerializeToString(), stream_sequence=44)
        timeline = receiver.rebuild_account_timeline()
        writes = timeline.timeline_records()
        self.assertEqual([record.update.stream_sequence for record in writes], [40, 44])
        self.assertEqual([record.continuity_epoch for record in writes], [0, 0])
        self.assertEqual(timeline.gaps, ())

        receiver.receive(message.SerializeToString(), stream_sequence=46)
        with self.assertRaisesRegex(ValueError, "interrompido"):
            receiver.rebuild_account_timeline()

        reconnected = self.receiver(store, stream="connection-b", domain="domain-b")
        reconnected.receive(message.SerializeToString(), stream_sequence=40)
        records = reconnected.rebuild_account_timeline().timeline_records()
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0].baseline)
        self.assertEqual(records[0].update.stream_id, "connection-b")

    def test_persistent_timeline_rebuild_is_atomic_and_isolated_by_connection(self):
        account = _parse("account_update").SerializeToString()
        with TemporaryDirectory() as directory:
            database = Path(directory) / "wire.sqlite3"
            store = SQLiteGeyserRawStore(database)
            first = self.receiver(store)
            written = first.receive(account, stream_sequence=40)
            second = self.receiver(store, stream="connection-b", domain="domain-b")
            second.receive(account, stream_sequence=40)
            projection = SQLiteGeyserAccountTimelineProjection(database)
            self.assertEqual(projection.rebuild_wire(first), 1)
            self.assertEqual(projection.rebuild_wire(second), 1)
            generation, rows = projection.list_wire_account_writes(*first.scope)
            self.assertEqual(generation, 1)
            self.assertEqual(rows[0]["frame_id"], written.frame_id)
            self.assertEqual(rows[0]["payload_sha256"], written.payload_sha256)

            with sqlite3.connect(database) as connection:
                connection.execute(
                    """CREATE TRIGGER reject_wire_projection BEFORE INSERT ON geyser_wire_timeline_writes
                       BEGIN SELECT RAISE(ABORT, 'forced projection failure'); END"""
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "forced projection failure"):
                projection.rebuild_wire(first)
            self.assertEqual(projection.list_wire_account_writes(*first.scope), (1, rows))
            with sqlite3.connect(database) as connection:
                connection.execute("DROP TRIGGER reject_wire_projection")

            changed = _UPDATE.FromString(account)
            changed.account.account.write_version += 1
            changed_wire = changed.SerializeToString()
            real_rebuild = first.rebuild_account_timeline

            def append_during_rebuild():
                timeline = real_rebuild()
                first.receive(changed_wire, stream_sequence=41)
                return timeline

            with patch.object(first, "rebuild_account_timeline", side_effect=append_during_rebuild):
                with self.assertRaisesRegex(RuntimeError, "journal mudou"):
                    projection.rebuild_wire(first)
            with self.assertRaisesRegex(ValueError, "desatualizada"):
                projection.list_wire_account_writes(*first.scope)
            self.assertEqual(projection.list_wire_account_writes(*second.scope)[0], 1)
            self.assertEqual(projection.rebuild_wire(first), 2)
            _, refreshed = projection.list_wire_account_writes(*first.scope)
            self.assertEqual([row["stream_sequence"] for row in refreshed], [40, 41])
            self.assertEqual(first.receive(account, stream_sequence=41).status, "collision")
            with self.assertRaisesRegex(ValueError, "desatualizada"):
                projection.list_wire_account_writes(*first.scope)
            with self.assertRaisesRegex(ValueError, "anomalia histórica"):
                projection.rebuild_wire(first)
            self.assertEqual(projection.list_wire_account_writes(*second.scope)[0], 1)

    def test_malformed_frame_remains_auditable_and_taints_domain(self):
        store = SQLiteGeyserRawStore(":memory:")
        self.addCleanup(store.close)
        receiver = self.receiver(store)
        item = receiver.receive(b"\xff", stream_sequence=40)
        self.assertEqual(item.status, "invalid")
        self.assertEqual(item.contiguous_sequence, 39)
        self.assertEqual(store.get_wire_frame(item.frame_id), b"\xff")
        self.assertTrue(receiver.receive(self.transaction_frame(), stream_sequence=40).tainted)
        with self.assertRaisesRegex(ValueError, "anomalia histórica"):
            list(receiver.replay())


if __name__ == "__main__":
    unittest.main()
