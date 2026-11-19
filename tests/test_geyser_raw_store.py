import hashlib
import sqlite3
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

    def test_declared_baseline_records_gap_and_does_not_advance_across_it(self):
        store = SQLiteGeyserRawStore(":memory:")
        store.register_stream("yellowstone-mainnet", "stream-a", 100)
        store.ingest(self.event(b"100", event_id="event-100"), self.delivery(100))
        store.ingest(self.event(b"102", event_id="event-102"), self.delivery(102))
        checkpoint = store.get_transport_checkpoint("yellowstone-mainnet", "stream-a")
        self.assertEqual(checkpoint["initial_sequence"], 100)
        self.assertEqual(checkpoint["contiguous_sequence"], 100)
        self.assertEqual(checkpoint["last_seen_sequence"], 102)
        self.assertTrue(checkpoint["interrupted"])
        gaps = store.list_transport_gaps("yellowstone-mainnet", "stream-a", status="OPEN")
        self.assertEqual([(gap["missing_from"], gap["missing_to"]) for gap in gaps], [(101, 101)])
        store.close()

    def test_out_of_order_delivery_closes_gap_only_after_contiguous_recovery(self):
        store = SQLiteGeyserRawStore(":memory:")
        store.register_stream("yellowstone-mainnet", "stream-a", 100)
        store.ingest(self.event(b"102", event_id="event-102"), self.delivery(102))
        first = store.get_transport_checkpoint("yellowstone-mainnet", "stream-a")
        self.assertEqual(first["contiguous_sequence"], 99)
        self.assertTrue(first["interrupted"])
        store.ingest(self.event(b"100", event_id="event-100"), self.delivery(100))
        middle = store.get_transport_checkpoint("yellowstone-mainnet", "stream-a")
        self.assertEqual(middle["contiguous_sequence"], 100)
        self.assertTrue(middle["interrupted"])
        store.ingest(self.event(b"101", event_id="event-101"), self.delivery(101))
        final = store.get_transport_checkpoint("yellowstone-mainnet", "stream-a")
        self.assertEqual(final["contiguous_sequence"], 102)
        self.assertFalse(final["interrupted"])
        gaps = store.list_transport_gaps("yellowstone-mainnet", "stream-a")
        self.assertEqual([gap["status"] for gap in gaps], ["SUPERSEDED", "RESOLVED"])
        store.close()

    def test_first_observed_baseline_is_explicitly_unverified(self):
        store = SQLiteGeyserRawStore(":memory:")
        store.ingest(self.event(b"55", event_id="event-55"), self.delivery(55))
        checkpoint = store.get_transport_checkpoint("yellowstone-mainnet", "stream-a")
        self.assertEqual(checkpoint["baseline_kind"], "first_observed_unverified")
        self.assertEqual(checkpoint["contiguous_sequence"], 55)
        self.assertFalse(checkpoint["interrupted"])
        store.close()

    def test_replay_of_same_event_and_sequence_is_not_a_sequence_collision(self):
        store = SQLiteGeyserRawStore(":memory:")
        store.register_stream("yellowstone-mainnet", "stream-a", 1)
        store.ingest(self.event(), self.delivery(1))
        store.ingest(self.event(), self.delivery(1, kind="replay"))
        self.assertEqual(
            store.list_transport_anomalies("yellowstone-mainnet", "stream-a"), []
        )
        self.assertFalse(
            store.get_transport_checkpoint("yellowstone-mainnet", "stream-a")["interrupted"]
        )
        store.close()

    def test_raw_identity_conflict_interrupts_transport_checkpoint(self):
        store = SQLiteGeyserRawStore(":memory:")
        store.register_stream("yellowstone-mainnet", "stream-a", 1)
        store.ingest(self.event(b"original"), self.delivery(1))
        store.ingest(self.event(b"changed"), self.delivery(2))
        checkpoint = store.get_transport_checkpoint("yellowstone-mainnet", "stream-a")
        anomalies = store.list_transport_anomalies("yellowstone-mainnet", "stream-a", status="OPEN")
        self.assertTrue(checkpoint["interrupted"])
        self.assertEqual(anomalies[0]["reason"], "raw_identity_conflict")
        store.close()

    def test_different_events_reusing_sequence_create_resolvable_anomaly(self):
        store = SQLiteGeyserRawStore(":memory:")
        store.register_stream("yellowstone-mainnet", "stream-a", 1)
        store.ingest(self.event(b"first", event_id="event-first"), self.delivery(1))
        store.ingest(self.event(b"second", event_id="event-second"), self.delivery(1))
        checkpoint = store.get_transport_checkpoint("yellowstone-mainnet", "stream-a")
        anomalies = store.list_transport_anomalies("yellowstone-mainnet", "stream-a", status="OPEN")
        self.assertTrue(checkpoint["interrupted"])
        self.assertEqual(anomalies[0]["reason"], "sequence_reused_for_different_event")
        store.resolve_transport_anomaly(anomalies[0]["anomaly_id"], "Conferido em fixture offline")
        resolved = store.list_transport_anomalies(
            "yellowstone-mainnet", "stream-a", status="RESOLVED"
        )
        self.assertEqual(len(resolved), 1)
        # Administrative resolution does not rehabilitate a colliding sequence.
        self.assertTrue(
            store.get_transport_checkpoint("yellowstone-mainnet", "stream-a")["interrupted"]
        )
        store.close()

    def test_gap_checkpoint_and_raw_delivery_roll_back_together(self):
        store = SQLiteGeyserRawStore(":memory:")
        store.register_stream("yellowstone-mainnet", "stream-a", 10)
        with store._connection() as connection:
            connection.execute("""
                CREATE TRIGGER reject_gap BEFORE INSERT ON geyser_transport_gaps
                BEGIN SELECT RAISE(ABORT, 'forced gap failure'); END
            """)
        with self.assertRaisesRegex(Exception, "forced gap failure"):
            store.ingest(self.event(b"11", event_id="event-11"), self.delivery(11))
        self.assertIsNone(store.get_raw_event("event-11"))
        self.assertEqual(store.counts()["geyser_raw_deliveries"], 0)
        checkpoint = store.get_transport_checkpoint("yellowstone-mainnet", "stream-a")
        self.assertEqual(checkpoint["contiguous_sequence"], 9)
        self.assertEqual(checkpoint["last_seen_sequence"], 9)
        self.assertFalse(checkpoint["interrupted"])
        self.assertEqual(store.list_transport_gaps("yellowstone-mainnet", "stream-a"), [])
        store.close()

    def test_cannot_register_stream_baseline_after_first_delivery(self):
        store = SQLiteGeyserRawStore(":memory:")
        store.ingest(self.event(), self.delivery(5))
        with self.assertRaisesRegex(ValueError, "após ingestão"):
            store.register_stream("yellowstone-mainnet", "stream-a", 1)
        store.close()

    def test_schema_v3_is_readable_and_migrates_without_inventing_capture_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.sqlite"
            store = SQLiteGeyserRawStore(path)
            scope = ("provider", "stream", "domain")
            store.register_frame_stream(*scope, 0)
            store.close()
            with sqlite3.connect(path) as connection:
                connection.execute("DROP TABLE geyser_capture_sessions")
                connection.execute("DELETE FROM geyser_schema_migrations WHERE version = 4")
            read_only = SQLiteGeyserRawStore(path, read_only=True)
            self.assertEqual(list(read_only.iter_wire_frames(*scope)), [])
            self.assertIsNone(read_only.get_capture_session(*scope[:2]))
            session, = read_only.list_wire_sessions(limit=1)
            self.assertIsNone(session["capture"])
            self.assertEqual(session["counts"], [])
            read_only.close()

            store = SQLiteGeyserRawStore(path)
            self.assertIsNone(store.get_capture_session(*scope[:2]))
            store.start_capture_session(*scope[:2])
            active = store.get_capture_session(*scope[:2])
            self.assertIsNone(active["outcome"])
            self.assertIsNone(active["finished_at"])
            self.assertEqual(store.finish_capture_session(*scope[:2], "deadline_exceeded"), 0)
            with self.assertRaisesRegex(ValueError, "já finalizada"):
                store.append_wire_frame(
                    source_id=scope[0], stream_id=scope[1], ordering_domain_id=scope[2],
                    stream_sequence=0, payload=b"frame", frame_kind="ping",
                )
            store.close()

            read_only = SQLiteGeyserRawStore(path, read_only=True)
            self.assertEqual(read_only.get_capture_session(*scope[:2])["outcome"], "deadline_exceeded")
            read_only.close()

    def test_schema_v2_migration_preserves_logical_raw_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "smr_geyser.sqlite"
            store = SQLiteGeyserRawStore(path)
            original = self.event()
            store.register_stream(original.source_id, "stream-a", 7)
            store.ingest(original, self.delivery(7))
            checkpoint = store.get_transport_checkpoint(original.source_id, "stream-a")
            store.close()
            with sqlite3.connect(path) as connection:
                connection.execute("DROP TABLE geyser_capture_sessions")
                connection.execute("DROP TABLE geyser_wire_frames")
                connection.execute("DROP TABLE geyser_frame_streams")
                connection.execute("DELETE FROM geyser_schema_migrations WHERE version >= 3")

            upgraded = SQLiteGeyserRawStore(path)
            self.assertEqual(upgraded.get_transport_checkpoint(original.source_id, "stream-a"), checkpoint)
            self.assertEqual(upgraded.get_raw_event(original.event_id)["payload_bytes"], original.payload_bytes)
            upgraded.register_frame_stream(original.source_id, "stream-b", "domain-b", 0)
            self.assertEqual(list(upgraded.iter_wire_frames(original.source_id, "stream-b", "domain-b")), [])
            self.assertEqual(upgraded.integrity_check(), ["ok"])
            upgraded.close()

    def test_existing_schema_v1_database_upgrades_to_current(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "smr_geyser.sqlite"
            store = SQLiteGeyserRawStore(path)
            store.close()
            connection = sqlite3.connect(path)
            try:
                connection.execute("DROP TABLE geyser_transport_anomalies")
                connection.execute("DROP TABLE geyser_transport_gaps")
                connection.execute("DROP TABLE geyser_transport_checkpoints")
                connection.execute("DROP TABLE geyser_capture_sessions")
                connection.execute("DROP TABLE geyser_wire_frames")
                connection.execute("DROP TABLE geyser_frame_streams")
                connection.execute("DELETE FROM geyser_schema_migrations WHERE version > 1")
                connection.commit()
            finally:
                connection.close()
            upgraded = SQLiteGeyserRawStore(path)
            checkpoint = upgraded.register_stream("yellowstone-mainnet", "stream-v1", 7)
            self.assertEqual(checkpoint["initial_sequence"], 7)
            with upgraded._connection() as connection:
                version = connection.execute(
                    "SELECT MAX(version) FROM geyser_schema_migrations"
                ).fetchone()[0]
            self.assertEqual(version, SQLiteGeyserRawStore.SCHEMA_VERSION)
            self.assertEqual(upgraded.integrity_check(), ["ok"])
            upgraded.close()

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
