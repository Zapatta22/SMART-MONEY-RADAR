import sqlite3
import tempfile
import unittest
from pathlib import Path

from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate
from smart_money_radar.data_sources.geyser_ingestion import ingest_normalized_event
from smart_money_radar.storage.geyser_raw_store import (
    RawDeliveryInput, RawEventInput, SQLiteGeyserRawStore,
)
from smart_money_radar.storage.geyser_recovery_store import SQLiteGeyserRecoveryStore
from smart_money_radar.storage.geyser_account_timeline_projection import (
    PROJECTION_NAME as TIMELINE_PROJECTION_NAME,
    PROJECTION_VERSION as TIMELINE_PROJECTION_VERSION,
    SQLiteGeyserAccountTimelineProjection,
)
from smart_money_radar.storage.geyser_unsequenced_delivery_audit import (
    POLICY_ID, SQLiteGeyserUnsequencedDeliveryAudit,
)


class GeyserUnsequencedDeliveryAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "smr_geyser.sqlite"
        self.raw = SQLiteGeyserRawStore(self.db)
        self.audit = SQLiteGeyserUnsequencedDeliveryAudit(self.db)

    def tearDown(self):
        self.raw.close()
        self.tmp.cleanup()

    def event(self, *, sequence=None, stream="stream-a", source="source-a", data=b"x",
              pubkey="account", slot=10):
        return NormalizedAccountUpdate(
            pubkey=pubkey, slot=slot, write_version=1, txn_signature=None,
            lamports=1, owner="owner", executable=False, rent_epoch=0, data=data,
            stream_id=stream, stream_sequence=sequence, source=source,
            bank_id=7, is_startup=False,
        )

    def ingest(self, **kwargs):
        return ingest_normalized_event(
            self.raw, self.event(**kwargs), schema_version="geyser-v16"
        )

    def test_unsequenced_delivery_without_witness_remains_unresolved(self):
        result = self.ingest()
        summary = self.audit.rebuild()
        item = self.audit.list_deliveries()[0]
        self.assertEqual(item["delivery_id"], result.delivery_id)
        self.assertEqual(item["classification"], "UNSEQUENCED_UNRESOLVED")
        self.assertEqual(item["witness_delivery_ids"], [])
        self.assertEqual(summary["unresolved_count"], 1)

    def test_later_sequenced_replay_reconciles_without_rewriting_delivery(self):
        first = self.ingest()
        initial = self.audit.rebuild()
        initial_row = self.audit.list_deliveries()[0]
        self.assertEqual(initial_row["classification"], "UNSEQUENCED_UNRESOLVED")
        self.assertEqual(initial["unresolved_count"], 1)
        second = self.ingest(sequence=20)
        summary = self.audit.rebuild()
        items = self.audit.list_deliveries()
        first_row = next(item for item in items if item["delivery_id"] == first.delivery_id)
        self.assertEqual(first_row["classification"], "UNSEQUENCED_RECONCILED")
        self.assertEqual(first_row["witness_delivery_ids"], [second.delivery_id])
        self.assertEqual(first_row["stream_sequence"], None)
        self.assertEqual(summary["reconciled_count"], 1)

    def test_sequenced_witness_from_another_stream_is_reference_only(self):
        first = self.ingest()
        second = self.ingest(sequence=30, stream="replay-stream")
        self.audit.rebuild()
        row = next(x for x in self.audit.list_deliveries() if x["delivery_id"] == first.delivery_id)
        self.assertEqual(row["classification"], "UNSEQUENCED_RECONCILED")
        self.assertEqual(row["witness_delivery_ids"], [second.delivery_id])
        self.assertIsNone(row["stream_sequence"])

    def test_raw_identity_conflict_blocks_reconciliation(self):
        self.ingest()
        self.ingest(sequence=10)
        conflict = self.ingest(sequence=11, data=b"changed")
        self.assertEqual(conflict.status, "conflict")
        self.audit.rebuild()
        rows = self.audit.list_deliveries()
        self.assertEqual(rows[0]["classification"], "IDENTITY_CONFLICT")
        self.assertEqual(rows[-1]["classification"], "IDENTITY_CONFLICT")

    def test_open_transport_anomaly_is_not_an_eligible_witness(self):
        self.raw.register_stream("source-a", "stream-a", 1)
        self.ingest(sequence=1)
        # Reusing the sequence for a different logical event opens an anomaly.
        other = NormalizedAccountUpdate(
            pubkey="other", slot=10, write_version=1, txn_signature=None,
            lamports=1, owner="owner", executable=False, rent_epoch=0, data=b"y",
            stream_id="stream-a", stream_sequence=1, source="source-a",
            bank_id=7, is_startup=False,
        )
        ingest_normalized_event(self.raw, other, schema_version="geyser-v16")
        self.ingest()
        self.audit.rebuild()
        rows = self.audit.list_deliveries()
        first = next(x for x in rows if x["event_id"] is not None and x["stream_sequence"] == 1)
        unsequenced = next(x for x in rows if x["classification"] == "UNSEQUENCED_UNRESOLVED")
        self.assertEqual(first["classification"], "SEQUENCE_ANOMALY")
        self.assertEqual(unsequenced["classification"], "UNSEQUENCED_UNRESOLVED")

    def test_rebuild_is_repeatable_and_versioned(self):
        self.ingest()
        first = self.audit.rebuild()
        second = self.audit.rebuild()
        self.assertEqual(second["generation"], first["generation"] + 1)
        checkpoint = self.audit.get_checkpoint()
        self.assertEqual(checkpoint["policy_id"], POLICY_ID)
        self.assertEqual(checkpoint["delivery_count"], 1)
        self.assertEqual(len(self.audit.list_deliveries()), 1)

    def test_failed_generation_rolls_back_previous_audit_and_checkpoint(self):
        self.ingest()
        self.audit.rebuild()
        previous = self.audit.get_checkpoint()
        with sqlite3.connect(self.db) as connection:
            connection.execute("""
                CREATE TRIGGER reject_audit_insert
                BEFORE INSERT ON geyser_unsequenced_delivery_audit
                BEGIN SELECT RAISE(ABORT, 'forced audit failure'); END
            """)
        with self.assertRaisesRegex(sqlite3.DatabaseError, "forced audit failure"):
            self.audit.rebuild()
        self.assertEqual(self.audit.get_checkpoint()["generation"], previous["generation"])
        self.assertEqual(len(self.audit.list_deliveries()), 1)

    def test_different_sources_never_reconcile_each_other(self):
        first = self.ingest(source="source-a")
        second = self.ingest(source="source-b")
        self.audit.rebuild()
        rows = self.audit.list_deliveries()
        self.assertNotEqual(first.event_id, second.event_id)
        self.assertEqual(
            [row["classification"] for row in rows],
            ["UNSEQUENCED_UNRESOLVED", "UNSEQUENCED_UNRESOLVED"],
        )
        self.assertEqual([row["witness_delivery_ids"] for row in rows], [[], []])

    def test_same_slot_and_adjacent_arrival_do_not_reconcile_distinct_events(self):
        self.ingest(pubkey="account-a", slot=10)
        self.ingest(pubkey="account-b", slot=10)
        self.audit.rebuild()
        rows = self.audit.list_deliveries()
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["event_id"], rows[1]["event_id"])
        self.assertEqual(
            [row["classification"] for row in rows],
            ["UNSEQUENCED_UNRESOLVED", "UNSEQUENCED_UNRESOLVED"],
        )
        self.assertEqual([row["witness_delivery_ids"] for row in rows], [[], []])

    def test_identical_received_timestamp_does_not_reconcile_distinct_raw_events(self):
        received_at = "2026-11-19T12:00:00+00:00"
        for event_id, payload in (("event-a", b"payload-a"), ("event-b", b"payload-b")):
            self.raw.ingest(
                RawEventInput(
                    event_id=event_id,
                    source_id="source-a",
                    event_kind="account",
                    schema_version="geyser-v16",
                    payload_encoding="normalized_json",
                    payload_bytes=payload,
                ),
                RawDeliveryInput(
                    stream_id="stream-a",
                    stream_sequence=None,
                    received_at=received_at,
                ),
            )
        self.audit.rebuild()
        rows = self.audit.list_deliveries()
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            [row["classification"] for row in rows],
            ["UNSEQUENCED_UNRESOLVED", "UNSEQUENCED_UNRESOLVED"],
        )
        self.assertEqual([row["witness_delivery_ids"] for row in rows], [[], []])

    def test_multiple_unsequenced_deliveries_are_preserved_individually(self):
        first = self.ingest()
        second = self.ingest()
        witness = self.ingest(sequence=45, stream="replay-stream")
        second_witness = self.ingest(sequence=46, stream="backup-stream")
        summary = self.audit.rebuild()
        rows = self.audit.list_deliveries()
        by_id = {row["delivery_id"]: row for row in rows}
        for delivery in (first, second):
            self.assertEqual(
                by_id[delivery.delivery_id]["classification"],
                "UNSEQUENCED_RECONCILED",
            )
            self.assertEqual(
                by_id[delivery.delivery_id]["witness_delivery_ids"],
                [witness.delivery_id, second_witness.delivery_id],
            )
            self.assertIsNone(by_id[delivery.delivery_id]["stream_sequence"])
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            {row["delivery_id"] for row in rows},
            {first.delivery_id, second.delivery_id, witness.delivery_id, second_witness.delivery_id},
        )
        self.assertEqual(summary["unsequenced_count"], 2)
        self.assertEqual(summary["reconciled_count"], 2)

    def test_unsequenced_event_is_not_projected_into_timeline_or_checkpoint(self):
        self.ingest()
        timeline = SQLiteGeyserAccountTimelineProjection(self.db)
        summary = timeline.rebuild()
        self.assertEqual(summary["account_write_count"], 0)
        self.assertEqual(timeline.list_account_writes(), [])
        checkpoint = SQLiteGeyserRecoveryStore(self.db).get_projection_checkpoint(
            TIMELINE_PROJECTION_NAME, TIMELINE_PROJECTION_VERSION, "source-a"
        )
        self.assertIsNotNone(checkpoint)
        self.assertEqual(checkpoint["projected_event_count"], 0)
        self.assertEqual(checkpoint["skipped_unsequenced_count"], 1)

    def test_schema_migration_version_is_recorded(self):
        with sqlite3.connect(self.db) as connection:
            versions = connection.execute(
                "SELECT version FROM geyser_unsequenced_delivery_audit_schema_migrations"
            ).fetchall()
        self.assertEqual(versions, [(1,)])

    def test_raw_and_transport_checkpoints_are_unchanged_by_audit_rebuild(self):
        self.raw.register_stream("source-a", "stream-a", 1)
        self.ingest(sequence=1)
        self.ingest()
        before_counts = self.raw.counts()
        before_checkpoint = self.raw.get_transport_checkpoint("source-a", "stream-a")
        self.audit.rebuild()
        self.assertEqual(self.raw.counts(), before_counts)
        self.assertEqual(
            self.raw.get_transport_checkpoint("source-a", "stream-a"), before_checkpoint
        )
        self.assertEqual(self.raw.integrity_check(), ["ok"])


if __name__ == "__main__":
    unittest.main()
