"""Tests for normalized Yellowstone transaction observations."""
import hashlib
import unittest
from smart_money_radar.data_sources.geyser_transaction_updates import (
    NormalizedTransactionObservation, normalize_transaction_update,
)
from smart_money_radar.data_sources.geyser_proto_adapter import adapt_subscribe_update

class ProtoMessage:
    def __init__(self, payload, **fields):
        self.payload = payload
        for key, value in fields.items(): setattr(self, key, value)
    def SerializeToString(self, deterministic=False): return self.payload

class SubscribeUpdate:
    def __init__(self, transaction): self.transaction, self.slot = transaction, 123456
    def SerializeToString(self, deterministic=False): return b"serialized-update"
    def WhichOneof(self, name):
        if name != "update_oneof": raise ValueError(name)
        return "transaction"

def _signature(): return bytes(range(64))

def _valid_info(**overrides):
    values = {
        "signature": _signature(), "index": 17, "is_vote": False,
        "transaction": ProtoMessage(b"serialized-transaction", signatures=[_signature()]),
        "meta": ProtoMessage(b"serialized-meta"),
    }
    values.update(overrides)
    return ProtoMessage(b"serialized-info", **values)

class NormalizeTransactionUpdateTests(unittest.TestCase):
    def test_normalizes_transaction_and_preserves_metadata(self):
        item = normalize_transaction_update(SubscribeUpdate(_valid_info()), source_id="provider-a", stream_id="conn-a", stream_sequence=42)
        self.assertIsInstance(item, NormalizedTransactionObservation)
        self.assertEqual((item.slot, item.transaction_index), (123456, 17))
        self.assertEqual(item.transaction_payload, b"serialized-transaction")
        self.assertEqual(item.meta_payload, b"serialized-meta")
        self.assertEqual(item.raw_payload, b"serialized-update")
        self.assertEqual(item.raw_payload_provenance, "PROTOBUF_DETERMINISTIC_RESERIALIZATION")
        self.assertEqual(item.payload_sha256, hashlib.sha256(b"serialized-update").hexdigest())
        self.assertEqual(item.ordering_key, ("provider-a", "conn-a", 42))
        self.assertTrue(item.evidence_complete)

    def test_exact_wire_bytes_are_distinguished_from_reserialization(self):
        item = normalize_transaction_update(SubscribeUpdate(_valid_info()), source_id="provider-a", stream_id="conn-a", stream_sequence=1, raw_message_bytes=b"exact-wire-frame")
        self.assertEqual(item.raw_payload, b"exact-wire-frame")
        self.assertEqual(item.raw_payload_provenance, "WIRE")

    def test_missing_meta_is_preserved_and_marks_evidence_incomplete(self):
        item = normalize_transaction_update(SubscribeUpdate(_valid_info(meta=None)), source_id="provider-a", stream_id="conn-a", stream_sequence=2)
        self.assertIsNone(item.meta_payload)
        self.assertFalse(item.evidence_complete)

    def test_signature_mismatch_fails_closed(self):
        info = _valid_info(transaction=ProtoMessage(b"serialized-transaction", signatures=[bytes(reversed(range(64)))]))
        with self.assertRaisesRegex(ValueError, "diverge"):
            normalize_transaction_update(SubscribeUpdate(info), source_id="provider-a", stream_id="conn-a", stream_sequence=1)

    def test_rejects_invalid_slot_and_sequence(self):
        invalid_slot = SubscribeUpdate(_valid_info())
        invalid_slot.slot = True
        with self.assertRaisesRegex(ValueError, "slot"):
            normalize_transaction_update(invalid_slot, source_id="provider-a", stream_id="conn-a", stream_sequence=1)
        with self.assertRaisesRegex(ValueError, "stream_sequence"):
            normalize_transaction_update(SubscribeUpdate(_valid_info()), source_id="provider-a", stream_id="conn-a", stream_sequence=-1)

    def test_adapter_dispatches_transaction_update(self):
        item = adapt_subscribe_update(SubscribeUpdate(_valid_info()), source_id="provider-a", stream_id="conn-a", stream_sequence=9, raw_message_bytes=b"wire-transaction")
        self.assertEqual(item.transaction_index, 17)
        self.assertEqual(item.raw_payload, b"wire-transaction")
        self.assertEqual(item.raw_payload_provenance, "WIRE")

if __name__ == "__main__": unittest.main()
