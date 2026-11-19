import base64
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate
from smart_money_radar.data_sources.geyser_ingestion import ingest_normalized_event
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.storage.geyser_account_write_projection import (
    PROJECTION_NAME,
    PROJECTION_VERSION,
    SQLiteGeyserAccountWriteProjection,
)


class GeyserAccountWriteProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "smr_geyser.sqlite"
        self.raw = SQLiteGeyserRawStore(self.database)
        self.projection = SQLiteGeyserAccountWriteProjection(self.database)

    def tearDown(self):
        self.raw.close()
        self.temp_dir.cleanup()

    def add_account(self, *, pubkey="account-a", slot=10, write_version=1,
                    data=b"\x00\xffaccount", stream="stream-a", sequence=1,
                    schema="geyser-v16"):
        event = NormalizedAccountUpdate(
            pubkey=pubkey, slot=slot, write_version=write_version,
            txn_signature="signature-a", lamports=123, owner="owner-a",
            executable=False, rent_epoch=9, data=data, stream_id=stream,
            stream_sequence=sequence, source="yellowstone-mainnet",
            bank_id=77, is_startup=False,
        )
        return ingest_normalized_event(self.raw, event, schema_version=schema)

    def test_rebuild_materializes_lossless_account_write_fields(self):
        result = self.add_account()
        summary = self.projection.rebuild()
        self.assertEqual(summary["projected_count"], 1)
        write = self.projection.list_writes()[0]
        self.assertEqual(write["event_id"], result.event_id)
        self.assertEqual(write["pubkey"], "account-a")
        self.assertEqual((write["slot"], write["write_version"], write["bank_id"]), (10, 1, 77))
        self.assertEqual(base64.b64decode(write["data_base64"]), b"\x00\xffaccount")
        self.assertEqual(write["data_length"], len(b"\x00\xffaccount"))
        self.assertEqual(write["txn_signature"], "signature-a")
        self.assertEqual(write["is_startup"], 0)

    def test_rebuild_is_idempotent_and_increments_generation(self):
        self.add_account()
        first = self.projection.rebuild()
        second = self.projection.rebuild()
        self.assertEqual(first["projected_count"], second["projected_count"])
        self.assertEqual(second["generation"], first["generation"] + 1)
        self.assertEqual(len(self.projection.list_writes()), 1)

    def test_late_arriving_raw_event_is_included_by_full_rebuild(self):
        self.add_account(pubkey="later", slot=20, sequence=2)
        self.projection.rebuild()
        self.add_account(pubkey="earlier", slot=5, sequence=3)
        summary = self.projection.rebuild()
        self.assertEqual(summary["projected_count"], 2)
        self.assertEqual({row["pubkey"] for row in self.projection.list_writes()},
                         {"later", "earlier"})

    def test_non_account_normalized_events_are_counted_as_skipped(self):
        self.add_account()
        from smart_money_radar.data_sources.geyser_bank_lineage import NormalizedSlotUpdate
        slot = NormalizedSlotUpdate("yellowstone-mainnet", "stream-a", 2, 10, 9,
                                    "SLOT_PROCESSED", 77, None)
        ingest_normalized_event(self.raw, slot, schema_version="geyser-v16")
        summary = self.projection.rebuild()
        self.assertEqual(summary["source_event_count"], 2)
        self.assertEqual(summary["projected_count"], 1)
        self.assertEqual(summary["skipped_count"], 1)

    def test_malformed_normalized_account_aborts_without_replacing_projection(self):
        self.add_account()
        self.projection.rebuild()
        second = self.add_account(pubkey="account-b", slot=11, sequence=2)
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "SELECT payload_bytes FROM geyser_raw_events WHERE event_id=?",
                (second.event_id,),
            ).fetchone()
            payload = json.loads(row[0])
            payload["payload"]["data_base64"] = "not base64!"
            connection.execute(
                "UPDATE geyser_raw_events SET payload_bytes=? WHERE event_id=?",
                (json.dumps(payload).encode(), second.event_id),
            )
        previous = self.projection.get_checkpoint()
        with self.assertRaises(ValueError):
            self.projection.rebuild()
        self.assertEqual(len(self.projection.list_writes()), 1)
        self.assertEqual(self.projection.get_checkpoint()["generation"],
                         previous["generation"])

    def test_checkpoint_is_separate_from_transport_checkpoint(self):
        self.add_account()
        self.projection.rebuild()
        checkpoint = self.projection.get_checkpoint()
        transport = self.raw.get_transport_checkpoint("yellowstone-mainnet", "stream-a")
        self.assertEqual(checkpoint["projection_name"], PROJECTION_NAME)
        self.assertEqual(checkpoint["projection_version"], PROJECTION_VERSION)
        self.assertEqual(checkpoint["generation"], 1)
        self.assertEqual(transport["contiguous_sequence"], 1)


if __name__ == "__main__":
    unittest.main()
