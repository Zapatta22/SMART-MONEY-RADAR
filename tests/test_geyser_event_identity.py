import unittest

from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate
from smart_money_radar.data_sources.geyser_bank_lineage import (
    NormalizedBlockMeta,
    NormalizedEntryUpdateParent,
    NormalizedSlotUpdate,
)
from smart_money_radar.data_sources.geyser_event_identity import (
    IDENTITY_VERSION,
    derive_event_identity,
)
from smart_money_radar.storage.geyser_raw_store import (
    RawDeliveryInput,
    RawEventInput,
    SQLiteGeyserRawStore,
)


class GeyserEventIdentityTests(unittest.TestCase):
    def account(self, *, stream_id="stream-a", sequence=1, data=b"state", bank_id=7):
        return NormalizedAccountUpdate(
            pubkey="account-pubkey",
            slot=100,
            write_version=900,
            txn_signature="signature",
            lamports=10,
            owner="owner",
            executable=False,
            rent_epoch=5,
            data=data,
            stream_id=stream_id,
            stream_sequence=sequence,
            source="yellowstone-mainnet",
            bank_id=bank_id,
            is_startup=False,
        )

    def test_account_identity_ignores_transport_and_payload_content(self):
        first = derive_event_identity(self.account(), schema_version="geyser-v16")
        replay = derive_event_identity(
            self.account(stream_id="reconnected-stream", sequence=44, data=b"changed"),
            schema_version="geyser-v16",
        )
        self.assertEqual(first.event_id, replay.event_id)
        self.assertEqual(first.identity_version, IDENTITY_VERSION)
        self.assertEqual(first.event_kind, "account")

    def test_account_identity_changes_for_different_ledger_write_or_bank(self):
        first = derive_event_identity(self.account(), schema_version="geyser-v16")
        changed_bank = derive_event_identity(
            self.account(bank_id=8), schema_version="geyser-v16"
        )
        changed_write = NormalizedAccountUpdate(
            **{**self.account().__dict__, "write_version": 901}
        )
        changed_write_id = derive_event_identity(
            changed_write, schema_version="geyser-v16"
        )
        self.assertNotEqual(first.event_id, changed_bank.event_id)
        self.assertNotEqual(first.event_id, changed_write_id.event_id)

    def test_schema_version_is_part_of_identity(self):
        first = derive_event_identity(self.account(), schema_version="geyser-v16")
        second = derive_event_identity(self.account(), schema_version="geyser-v17")
        self.assertNotEqual(first.event_id, second.event_id)

    def test_slot_identity_ignores_transport_but_not_status_or_bank(self):
        first = NormalizedSlotUpdate("source", "s1", 1, 50, 49, "SLOT_PROCESSED", 3, None)
        replay = NormalizedSlotUpdate("source", "s2", 9, 50, 48, "SLOT_PROCESSED", 3, "late metadata")
        other_status = NormalizedSlotUpdate("source", "s1", 2, 50, 49, "SLOT_CONFIRMED", 3, None)
        self.assertEqual(
            derive_event_identity(first, schema_version="v1").event_id,
            derive_event_identity(replay, schema_version="v1").event_id,
        )
        self.assertNotEqual(
            derive_event_identity(first, schema_version="v1").event_id,
            derive_event_identity(other_status, schema_version="v1").event_id,
        )

    def test_block_meta_identity_uses_source_slot_and_bank(self):
        first = NormalizedBlockMeta("source", "s1", 1, 50, 3, "hash-a", 49, "parent-a")
        changed_content = NormalizedBlockMeta("source", "s2", 2, 50, 3, "hash-b", 48, "parent-b")
        other_bank = NormalizedBlockMeta("source", "s1", 3, 50, 4, "hash-a", 49, "parent-a")
        self.assertEqual(
            derive_event_identity(first, schema_version="v1").event_id,
            derive_event_identity(changed_content, schema_version="v1").event_id,
        )
        self.assertNotEqual(
            derive_event_identity(first, schema_version="v1").event_id,
            derive_event_identity(other_bank, schema_version="v1").event_id,
        )

    def test_entry_update_parent_identity_uses_cleared_bank(self):
        first = NormalizedEntryUpdateParent("source", "s1", 1, 50, 3, 49, b"parent-a")
        replay = NormalizedEntryUpdateParent("source", "s2", 2, 50, 3, 48, b"parent-b")
        other_bank = NormalizedEntryUpdateParent("source", "s1", 3, 50, 4, 49, b"parent-a")
        self.assertEqual(
            derive_event_identity(first, schema_version="v1").event_id,
            derive_event_identity(replay, schema_version="v1").event_id,
        )
        self.assertNotEqual(
            derive_event_identity(first, schema_version="v1").event_id,
            derive_event_identity(other_bank, schema_version="v1").event_id,
        )

    def test_same_logical_identity_with_changed_raw_payload_is_a_store_conflict(self):
        store = SQLiteGeyserRawStore(":memory:")
        first = self.account(data=b"original-state")
        changed = self.account(data=b"changed-state", stream_id="stream-b", sequence=9)
        first_id = derive_event_identity(first, schema_version="geyser-v16")
        changed_id = derive_event_identity(changed, schema_version="geyser-v16")
        self.assertEqual(first_id.event_id, changed_id.event_id)
        first_result = store.ingest(
            RawEventInput(first_id.event_id, first.source, "account", "geyser-v16",
                          "protobuf_decoded", b"original-state"),
            RawDeliveryInput("stream-a", 1, "live"),
        )
        conflict_result = store.ingest(
            RawEventInput(changed_id.event_id, changed.source, "account", "geyser-v16",
                          "protobuf_decoded", b"changed-state"),
            RawDeliveryInput("stream-b", 9, "replay"),
        )
        self.assertEqual(first_result.status, "inserted")
        self.assertEqual(conflict_result.status, "conflict")
        self.assertEqual(
            store.get_raw_event(first_id.event_id)["payload_bytes"], b"original-state"
        )
        store.close()

    def test_invalid_schema_and_unsupported_event_are_rejected(self):
        with self.assertRaises(ValueError):
            derive_event_identity(self.account(), schema_version=" ")
        with self.assertRaises(TypeError):
            derive_event_identity(object(), schema_version="v1")


if __name__ == "__main__":
    unittest.main()
