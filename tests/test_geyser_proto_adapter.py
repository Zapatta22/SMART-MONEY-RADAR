"""Wire-level adapter tests against a pinned Yellowstone schema subset."""
import base64
import hashlib
import json
import sqlite3
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path
import unittest

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from smart_money_radar.data_sources.geyser_proto_adapter import (
    adapt_account_update,
    adapt_subscribe_update,
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
    msg("Message")
    fld(transaction_payload, "message", 2, T.TYPE_MESSAGE, ".geyser.Message")
    transaction_meta = msg("TransactionStatusMeta")
    fld(transaction_meta, "fee", 2, T.TYPE_UINT64)
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
    msg("SubscribeUpdatePing")
    update = msg("SubscribeUpdate")
    update.oneof_decl.add(name="update_oneof")
    update.field.add(name="filters", number=1, type=T.TYPE_STRING, label=T.LABEL_REPEATED)
    for n, i, typ in (
        ("account", 2, "SubscribeUpdateAccount"), ("slot", 3, "SubscribeUpdateSlot"),
        ("block_meta", 7, "SubscribeUpdateBlockMeta"),
        ("transaction", 4, "SubscribeUpdateTransaction"),
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
