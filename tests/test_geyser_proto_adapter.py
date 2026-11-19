"""Wire-level adapter tests against a pinned Yellowstone schema subset."""
import base64
import hashlib
import json
from pathlib import Path
import unittest

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from smart_money_radar.data_sources.geyser_proto_adapter import (
    adapt_account_update,
    adapt_subscribe_update,
)

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
    fld(transaction_payload, "message", 2, T.TYPE_BYTES)
    transaction_meta = msg("TransactionStatusMeta")
    fld(transaction_meta, "fee", 1, T.TYPE_UINT64)
    transaction_info = msg("SubscribeUpdateTransactionInfo")
    fld(transaction_info, "signature", 1, T.TYPE_BYTES)
    fld(transaction_info, "is_vote", 2, T.TYPE_BOOL)
    fld(transaction_info, "transaction", 3, T.TYPE_MESSAGE, ".geyser.Transaction")
    fld(transaction_info, "meta", 4, T.TYPE_MESSAGE, ".geyser.TransactionStatusMeta")
    fld(transaction_info, "index", 5, T.TYPE_UINT64)
    transaction_update = msg("SubscribeUpdateTransaction")
    fld(transaction_update, "transaction", 1, T.TYPE_MESSAGE, ".geyser.SubscribeUpdateTransactionInfo")
    fld(transaction_update, "slot", 2, T.TYPE_UINT64)
    update = msg("SubscribeUpdate")
    update.oneof_decl.add(name="update_oneof")
    for n, i, typ in (
        ("account", 2, "SubscribeUpdateAccount"), ("slot", 3, "SubscribeUpdateSlot"),
        ("block_meta", 7, "SubscribeUpdateBlockMeta"),
        ("transaction", 4, "SubscribeUpdateTransaction"),
        ("entry_update_parent", 13, "SubscribeUpdateEntryUpdateParent"),
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
        info = update.transaction
        info.signature = signature
        info.is_vote = True
        info.index = 19
        info.transaction.signatures.append(signature)
        info.transaction.message = b"solana-message"
        info.meta.fee = 5000
        raw = message.SerializeToString(deterministic=True)

        item = adapt_subscribe_update(
            message, source_id="yellowstone-validator-a",
            stream_id="connection-a", ordering_domain_id="solana-ordering-a",
            stream_sequence=101, raw_message_bytes=raw,
        )
        self.assertEqual(item.transaction_signature, _b58(signature))
        self.assertEqual(item.slot, 123457)
        self.assertEqual(item.transaction_index, 19)
        self.assertTrue(item.is_vote)
        self.assertEqual(item.transaction_payload, info.transaction.SerializeToString(deterministic=True))
        self.assertEqual(item.meta_payload, info.meta.SerializeToString(deterministic=True))
        self.assertEqual(item.raw_payload, raw)
        self.assertEqual(item.raw_payload_provenance, "WIRE")

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


if __name__ == "__main__":
    unittest.main()
