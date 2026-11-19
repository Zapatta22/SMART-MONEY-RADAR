import hashlib
import tempfile
import unittest
from pathlib import Path

from smart_money_radar.storage.geyser_raw_store import (
    RawDeliveryInput,
    RawEventInput,
    SQLiteGeyserRawStore,
)


class SQLiteGeyserRawStoreTests(unittest.TestCase):
    def event(self, payload=b"wire-payload", *, event_id="event-1"):
        return RawEventInput(
            event_id=event_id,
            source_id="yellowstone-mainnet",
            event_kind="account",
            schema_version="geyser.proto@2026-09",
            payload_encoding="protobuf_wire",
            payload_bytes=payload,
        )

    def delivery(self, sequence=1, *, stream="stream-a", kind="live"):
        return RawDeliveryInput(
            stream_id=stream,
            stream_sequence=sequence,
            delivery_kind=kind,
            received_at="2026-11-19T05:00:00+00:00",
        )

    def test_first_event_persists_exact_bytes_and_sha256(self):
        store = SQLiteGeyserRawStore(":memory:")
        payload = b"\\x00protobuf\\xff"
        result = store.ingest(self.event(payload), self.delivery())
        stored = store.get_raw_event("event-1")
        self.assertEqual(result.status, "inserted")
        self.assertEqual(stored["payload_bytes"], payload)
        self.assertEqual(stored["payload_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(store.counts(), {
            "geyser_raw_events": 1, "geyser_raw_deliveries": 1, "geyser_raw_conflicts": 0
        })
        self.assertEqual(store.integrity_check(), ["ok"])
        store.close()

    def test_same_content_replay_adds_delivery_not_raw_event(self):
        store = SQLiteGeyserRawStore(":memory:")
        first = store.ingest(self.event(), self.delivery(1))
        replay = store.ingest(self.event(), self.delivery(8, stream="stream-b", kind="replay"))
        self.assertEqual(first.status, "inserted")
        self.assertEqual(replay.status, "duplicate")
        self.assertEqual(store.counts(), {
            "geyser_raw_events": 1, "geyser_raw_deliveries": 2, "geyser_raw_conflicts": 0
        })
        store.close()

    def test_reused_event_identity_with_different_bytes_is_preserved_as_conflict(self):
        store = SQLiteGeyserRawStore(":memory:")
        store.ingest(self.event(b"original"), self.delivery())
        result = store.ingest(self.event(b"tampered"), self.delivery(2))
        stored = store.get_raw_event("event-1")
        self.assertEqual(result.status, "conflict")
        self.assertIsNone(result.event_id)
        self.assertIsNotNone(result.conflict_id)
        self.assertEqual(stored["payload_bytes"], b"original")
        self.assertEqual(store.counts(), {
            "geyser_raw_events": 1, "geyser_raw_deliveries": 2, "geyser_raw_conflicts": 1
        })
        store.close()

    def test_conflict_also_detects_source_or_encoding_mismatch(self):
        store = SQLiteGeyserRawStore(":memory:")
        store.ingest(self.event(), self.delivery())
        mismatched = RawEventInput(
            event_id="event-1", source_id="other-source", event_kind="account",
            schema_version="geyser.proto@2026-09", payload_encoding="protobuf_wire",
            payload_bytes=b"wire-payload",
        )
        self.assertEqual(store.ingest(mismatched, self.delivery(2)).status, "conflict")
        store.close()

    def test_file_database_survives_reopen_and_keeps_deliveries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "smr_geyser.sqlite"
            store = SQLiteGeyserRawStore(path)
            store.ingest(self.event(), self.delivery())
            store.close()
            reopened = SQLiteGeyserRawStore(path)
            self.assertEqual(reopened.get_raw_event("event-1")["payload_bytes"], b"wire-payload")
            self.assertEqual(reopened.counts()["geyser_raw_deliveries"], 1)
            self.assertEqual(reopened.integrity_check(), ["ok"])
            reopened.close()

    def test_delivery_failure_rolls_back_new_raw_event(self):
        store = SQLiteGeyserRawStore(":memory:")
        with store._connection() as connection:
            connection.execute("""
                CREATE TRIGGER reject_delivery BEFORE INSERT ON geyser_raw_deliveries
                BEGIN SELECT RAISE(ABORT, 'forced delivery failure'); END
            """)
        with self.assertRaisesRegex(Exception, "forced delivery failure"):
            store.ingest(self.event(), self.delivery())
        self.assertIsNone(store.get_raw_event("event-1"))
        self.assertEqual(store.counts(), {
            "geyser_raw_events": 0, "geyser_raw_deliveries": 0, "geyser_raw_conflicts": 0
        })
        store.close()

    def test_invalid_event_or_delivery_is_rejected_before_write(self):
        store = SQLiteGeyserRawStore(":memory:")
        with self.assertRaises(TypeError):
            store.ingest(
                RawEventInput("event", "source", "account", "v1", "protobuf_wire", "not-bytes"),
                self.delivery(),
            )
        with self.assertRaises(ValueError):
            store.ingest(self.event(), RawDeliveryInput("", 1))
        self.assertEqual(store.counts(), {
            "geyser_raw_events": 0, "geyser_raw_deliveries": 0, "geyser_raw_conflicts": 0
        })
        store.close()


if __name__ == "__main__":
    unittest.main()
