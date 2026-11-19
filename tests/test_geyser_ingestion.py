import json
import unittest

from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate
from smart_money_radar.data_sources.geyser_bank_lineage import (
    NormalizedBlockMeta,
    NormalizedEntryUpdateParent,
    NormalizedSlotUpdate,
)
from smart_money_radar.data_sources.geyser_ingestion import ingest_normalized_event
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore


class GeyserNormalizedIngestionTests(unittest.TestCase):
    def account(self, *, stream="stream-a", sequence=1, data=b"account-state"):
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
            stream_id=stream,
            stream_sequence=sequence,
            source="yellowstone-mainnet",
            bank_id=7,
            is_startup=False,
        )

    def test_account_ingestion_persists_deterministic_normalized_json_and_delivery(self):
        store = SQLiteGeyserRawStore(":memory:")
        event = self.account()
        result = ingest_normalized_event(
            store, event, schema_version="geyser-v16", delivery_kind="live"
        )
        raw = store.get_raw_event(result.event_id)
        payload = json.loads(raw["payload_bytes"])
        self.assertEqual(result.status, "inserted")
        self.assertEqual(raw["payload_encoding"], "normalized_json")
        self.assertEqual(payload["event_kind"], "account")
        self.assertEqual(payload["payload"]["data_base64"], "YWNjb3VudC1zdGF0ZQ==")
        self.assertNotIn("stream_id", payload)
        self.assertNotIn("stream_sequence", payload)
        checkpoint = store.get_transport_checkpoint("yellowstone-mainnet", "stream-a")
        self.assertEqual(checkpoint["contiguous_sequence"], 1)
        store.close()

    def test_reconnect_replay_keeps_event_id_and_adds_delivery(self):
        store = SQLiteGeyserRawStore(":memory:")
        first = ingest_normalized_event(
            store, self.account(), schema_version="geyser-v16", delivery_kind="live"
        )
        replay = ingest_normalized_event(
            store,
            self.account(stream="stream-b", sequence=20),
            schema_version="geyser-v16",
            delivery_kind="replay",
        )
        self.assertEqual(first.event_id, replay.event_id)
        self.assertEqual(first.status, "inserted")
        self.assertEqual(replay.status, "duplicate")
        self.assertEqual(store.counts()["geyser_raw_events"], 1)
        self.assertEqual(store.counts()["geyser_raw_deliveries"], 2)
        self.assertEqual(
            store.get_transport_checkpoint("yellowstone-mainnet", "stream-b")["contiguous_sequence"],
            20,
        )
        store.close()

    def test_same_identity_with_changed_normalized_content_is_conflict(self):
        store = SQLiteGeyserRawStore(":memory:")
        first = ingest_normalized_event(
            store, self.account(data=b"original"), schema_version="geyser-v16"
        )
        changed = ingest_normalized_event(
            store,
            self.account(stream="stream-b", sequence=2, data=b"changed"),
            schema_version="geyser-v16",
        )
        self.assertIsNone(changed.event_id)
        self.assertEqual(changed.status, "conflict")
        self.assertIsNotNone(changed.conflict_id)
        raw = store.get_raw_event(first.event_id)
        stored_payload = json.loads(raw["payload_bytes"])["payload"]
        self.assertEqual(stored_payload["data_base64"], "b3JpZ2luYWw=")
        self.assertNotEqual(stored_payload["data_base64"], "Y2hhbmdlZA==")
        store.close()

    def test_slot_block_meta_and_entry_parent_use_normalized_payloads(self):
        store = SQLiteGeyserRawStore(":memory:")
        events = [
            NormalizedSlotUpdate("source", "stream", 1, 50, 49, "SLOT_PROCESSED", 3, None),
            NormalizedBlockMeta("source", "stream", 2, 50, 3, "hash", 49, "parent-hash"),
            NormalizedEntryUpdateParent("source", "stream", 3, 50, 3, 49, b"opaque-parent"),
        ]
        results = [
            ingest_normalized_event(store, event, schema_version="geyser-v16")
            for event in events
        ]
        self.assertTrue(all(result.status == "inserted" for result in results))
        for result in results:
            raw = store.get_raw_event(result.event_id)
            self.assertEqual(raw["payload_encoding"], "normalized_json")
            self.assertTrue(json.loads(raw["payload_bytes"])["payload"])
        self.assertEqual(store.counts()["geyser_raw_events"], 3)
        store.close()

    def test_schema_version_changes_identity_and_payload_contract(self):
        store = SQLiteGeyserRawStore(":memory:")
        v16 = ingest_normalized_event(store, self.account(), schema_version="geyser-v16")
        v17 = ingest_normalized_event(store, self.account(), schema_version="geyser-v17")
        self.assertNotEqual(v16.event_id, v17.event_id)
        self.assertEqual(store.counts()["geyser_raw_events"], 2)
        store.close()


if __name__ == "__main__":
    unittest.main()
