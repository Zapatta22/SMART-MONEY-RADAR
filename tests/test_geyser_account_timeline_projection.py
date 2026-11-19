import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate
from smart_money_radar.data_sources.geyser_bank_lineage import (
    NormalizedBlockMeta, NormalizedEntryUpdateParent, NormalizedSlotUpdate,
)
from smart_money_radar.data_sources.geyser_ingestion import ingest_normalized_event
from smart_money_radar.storage.geyser_raw_store import (
    RawDeliveryInput, RawEventInput, SQLiteGeyserRawStore,
)
from smart_money_radar.storage.geyser_recovery_store import SQLiteGeyserRecoveryStore
from smart_money_radar.storage.geyser_account_timeline_projection import (
    PROJECTION_NAME, PROJECTION_VERSION, SQLiteGeyserAccountTimelineProjection,
)


class GeyserAccountTimelineProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "smr_geyser.sqlite"
        self.raw = SQLiteGeyserRawStore(self.db)
        self.projection = SQLiteGeyserAccountTimelineProjection(self.db)
        self.source = "yellowstone-mainnet"
        self.stream = "stream-a"

    def tearDown(self):
        self.raw.close()
        self.tmp.cleanup()

    def add(self, event):
        return ingest_normalized_event(self.raw,event,schema_version="geyser-v16")

    def account(self, slot, version, seq, *, signature=None, bank=10, pubkey="acct"):
        return NormalizedAccountUpdate(
            pubkey=pubkey,slot=slot,write_version=version,txn_signature=signature,
            lamports=version,owner="owner",executable=False,rent_epoch=0,
            data=bytes([version]),stream_id=self.stream,stream_sequence=seq,
            source=self.source,bank_id=bank,is_startup=False,
        )

    def test_rebuild_persists_account_continuity_and_bank_lineage(self):
        self.add(NormalizedSlotUpdate(self.source,self.stream,1,100,99,"SLOT_CREATED_BANK",10,None))
        self.add(self.account(100,1,2))
        self.add(self.account(100,2,3,signature="sig"))
        summary=self.projection.rebuild()
        self.assertEqual(summary["account_write_count"],2)
        writes=self.projection.list_account_writes("acct")
        self.assertEqual([w["write_version"] for w in writes],[1,2])
        self.assertEqual(writes[0]["baseline"],1)
        self.assertEqual(writes[1]["baseline"],0)
        self.assertEqual(writes[1]["bank_observation_status"],"bank_observed_unfinalized")
        self.assertEqual(len(self.projection.list_banks()),1)

    def test_exact_blockhash_parent_link_is_persisted_not_slot_guess(self):
        self.add(NormalizedBlockMeta(self.source,self.stream,1,100,10,"parent-hash",99,"grand-hash"))
        self.add(NormalizedBlockMeta(self.source,self.stream,2,101,11,"child-hash",100,"parent-hash"))
        self.projection.rebuild()
        banks=self.projection.list_banks()
        child=next(b for b in banks if b["slot"]==101)
        self.assertEqual((child["parent_bank_slot"],child["parent_bank_id"]),(100,10))

    def test_entry_parent_keeps_opaque_bytes_and_invalidation(self):
        self.add(NormalizedSlotUpdate(self.source,self.stream,1,101,100,"SLOT_CREATED_BANK",10,None))
        self.add(NormalizedEntryUpdateParent(self.source,self.stream,2,101,10,100,b"opaque-id"))
        self.projection.rebuild()
        bank=self.projection.list_banks()[0]
        self.assertEqual(bank["parent_block_id_hex"],b"opaque-id".hex())
        self.assertEqual(bank["invalidated"],1)
        self.assertEqual(bank["cleared_by_parent_update"],1)

    def test_rebuild_preserves_invalidated_bank_and_marks_account_observation(self):
        self.add(NormalizedSlotUpdate(self.source,self.stream,1,101,100,"SLOT_CREATED_BANK",10,None))
        self.add(self.account(101,1,2,bank=10))
        self.add(NormalizedEntryUpdateParent(self.source,self.stream,3,101,10,100,b"opaque"))
        self.projection.rebuild()
        write=self.projection.list_account_writes()[0]
        self.assertEqual(write["bank_observation_status"],"bank_invalidated")
        self.assertEqual(len(self.projection.list_banks()),1)
        self.assertEqual(self.projection.list_banks()[0]["invalidated"],1)

    def test_rebuild_records_source_scoped_recovery_checkpoint_after_generation(self):
        self.raw.register_stream(self.source, self.stream, 1)
        self.add(self.account(100,1,1))
        result=self.projection.rebuild()
        recovery=SQLiteGeyserRecoveryStore(self.db)
        checkpoint=recovery.get_projection_checkpoint(PROJECTION_NAME,PROJECTION_VERSION,self.source)
        self.assertEqual(checkpoint["generation"],result["generation"])
        self.assertEqual(checkpoint["last_delivery_id"],1)
        self.assertEqual(checkpoint["projected_event_count"],1)
        self.assertEqual(checkpoint["skipped_unsequenced_count"],0)
        self.assertEqual(checkpoint["input_coverage_status"],"COMPLETE")
        self.assertFalse(checkpoint["continuity_interrupted"])
        self.assertEqual(result["source_checkpoint_count"],1)

    def test_rebuild_checkpoint_coverage_unknown_without_declared_stream_baseline(self):
        self.add(self.account(100,1,1))
        self.projection.rebuild()
        checkpoint=SQLiteGeyserRecoveryStore(self.db).get_projection_checkpoint(
            PROJECTION_NAME,PROJECTION_VERSION,self.source
        )
        self.assertEqual(checkpoint["input_coverage_status"],"UNKNOWN")
        self.assertFalse(checkpoint["continuity_interrupted"])

    def test_rebuild_checkpoint_is_partial_when_transport_gap_exists(self):
        self.raw.register_stream(self.source, self.stream, 1)
        self.add(self.account(100,1,1))
        self.add(self.account(101,2,3))
        self.projection.rebuild()
        checkpoint=SQLiteGeyserRecoveryStore(self.db).get_projection_checkpoint(
            PROJECTION_NAME,PROJECTION_VERSION,self.source
        )
        self.assertEqual(checkpoint["input_coverage_status"],"PARTIAL")
        self.assertTrue(checkpoint["continuity_interrupted"])

    def test_recovery_checkpoints_are_isolated_per_source(self):
        self.raw.register_stream(self.source, self.stream, 1)
        self.add(self.account(100,1,1,pubkey="source-a"))
        other=NormalizedAccountUpdate(
            pubkey="source-b",slot=100,write_version=1,txn_signature=None,
            lamports=1,owner="owner",executable=False,rent_epoch=0,data=b"x",
            stream_id="stream-b",stream_sequence=1,source="yellowstone-backup",
            bank_id=10,is_startup=False,
        )
        self.raw.register_stream("yellowstone-backup","stream-b",1)
        self.add(other)
        self.projection.rebuild()
        recovery=SQLiteGeyserRecoveryStore(self.db)
        first=recovery.get_projection_checkpoint(PROJECTION_NAME,PROJECTION_VERSION,self.source)
        second=recovery.get_projection_checkpoint(PROJECTION_NAME,PROJECTION_VERSION,"yellowstone-backup")
        self.assertEqual(first["input_coverage_status"],"COMPLETE")
        self.assertEqual(second["input_coverage_status"],"COMPLETE")
        self.assertNotEqual(first["source_id"],second["source_id"])

    def test_rebuild_is_repeatable_and_checkpoint_is_versioned(self):
        self.add(self.account(100,1,1))
        first=self.projection.rebuild()
        second=self.projection.rebuild()
        self.assertEqual(second["generation"],first["generation"]+1)
        checkpoint=self.projection.get_checkpoint()
        self.assertEqual(checkpoint["projection_name"],PROJECTION_NAME)
        self.assertEqual(checkpoint["projection_version"],PROJECTION_VERSION)
        self.assertEqual(len(self.projection.list_account_writes()),1)

    def test_late_arriving_sequence_is_replayed_in_stream_order(self):
        self.add(self.account(100,1,1))
        self.add(self.account(102,3,3,signature="third"))
        self.add(self.account(101,2,2,signature="second"))
        result=self.projection.rebuild()
        writes=self.projection.list_account_writes("acct")
        self.assertEqual(result["account_write_count"],3)
        self.assertEqual([row["slot"] for row in writes],[100,101,102])
        self.assertEqual([row["continuity_baseline"] for row in writes],[0,0,0])
        self.assertEqual(self.projection.list_gaps(),[])

    def test_stream_gap_is_persisted_and_breaks_predecessor_continuity(self):
        self.add(self.account(100,1,1))
        self.add(self.account(101,2,3,signature="after-gap"))
        self.projection.rebuild()
        writes=self.projection.list_account_writes("acct")
        self.assertEqual(len(writes),2)
        self.assertEqual(writes[1]["continuity_baseline"],1)
        gaps=self.projection.list_gaps()
        self.assertEqual(len(gaps),1)
        self.assertEqual((gaps[0]["expected_sequence"],gaps[0]["received_sequence"]),(2,3))

    def test_distinct_sources_do_not_create_false_reconnect_gap(self):
        self.add(self.account(100,1,1,pubkey="source-a"))
        second=NormalizedAccountUpdate(
            pubkey="source-b",slot=100,write_version=1,txn_signature=None,
            lamports=1,owner="owner",executable=False,rent_epoch=0,data=b"x",
            stream_id="stream-b",stream_sequence=1,source="yellowstone-backup",
            bank_id=10,is_startup=False,
        )
        self.add(second)
        self.projection.rebuild()
        self.assertEqual(len(self.projection.list_account_writes()),2)
        self.assertEqual(self.projection.list_gaps(),[])


    def test_resolved_transport_anomaly_still_taints_every_delivery_of_sequence(self):
        self.raw.register_stream(self.source,self.stream,1)
        self.add(self.account(100,1,1,pubkey="first"))
        self.add(self.account(101,1,1,pubkey="second"))
        anomalies=self.raw.list_transport_anomalies(self.source,self.stream,status="OPEN")
        self.assertEqual(len(anomalies),1)
        self.raw.resolve_transport_anomaly(anomalies[0]["anomaly_id"],"revisão administrativa")
        self.assertEqual(
            self.raw.list_transport_anomalies(self.source,self.stream,status="OPEN"),[]
        )
        result=self.projection.rebuild()
        self.assertEqual(result["account_write_count"],0)
        self.assertEqual(self.projection.list_account_writes(),[])

    def test_raw_identity_conflict_taints_original_event_from_timeline(self):
        original=self.add(self.account(100,1,1))
        conflict=self.raw.ingest(
            RawEventInput(
                event_id=original.event_id,
                source_id=self.source,
                event_kind="account",
                schema_version="geyser-v16",
                payload_encoding="normalized_json",
                payload_bytes=b'{"payload":"conflicting identity"}',
            ),
            RawDeliveryInput(
                stream_id=self.stream,stream_sequence=2,delivery_kind="live"
            ),
        )
        self.assertEqual(conflict.status,"conflict")
        result=self.projection.rebuild()
        self.assertEqual(result["account_write_count"],0)
        self.assertEqual(self.projection.list_account_writes(),[])

    def test_valid_json_payload_mutation_fails_raw_hash_and_rolls_back_generation(self):
        self.add(self.account(100,1,1))
        self.projection.rebuild()
        second=self.add(self.account(101,2,2))
        with sqlite3.connect(self.db) as connection:
            row=connection.execute(
                "SELECT payload_bytes,payload_sha256 FROM geyser_raw_events WHERE event_id=?",
                (second.event_id,),
            ).fetchone()
            original_digest=row[1]
            raw=json.loads(row[0])
            raw["payload"]["lamports"] += 1
            mutated=json.dumps(raw,separators=(",",":")).encode()
            self.assertNotEqual(hashlib.sha256(mutated).hexdigest(),original_digest)
            connection.execute(
                "UPDATE geyser_raw_events SET payload_bytes=? WHERE event_id=?",
                (mutated,second.event_id),
            )
        previous=self.projection.get_checkpoint()
        recovery=SQLiteGeyserRecoveryStore(self.db)
        previous_recovery=recovery.get_projection_checkpoint(
            PROJECTION_NAME,PROJECTION_VERSION,self.source
        )
        with self.assertRaisesRegex(ValueError,"SHA-256 RAW diverge"):
            self.projection.rebuild()
        self.assertEqual(len(self.projection.list_account_writes()),1)
        self.assertEqual(self.projection.get_checkpoint()["generation"],previous["generation"])
        self.assertEqual(
            recovery.get_projection_checkpoint(PROJECTION_NAME,PROJECTION_VERSION,self.source)["generation"],
            previous_recovery["generation"],
        )

    def test_bad_raw_payload_rolls_back_previous_generation(self):
        self.add(self.account(100,1,1))
        self.projection.rebuild()
        second=self.add(self.account(101,2,2))
        with sqlite3.connect(self.db) as connection:
            row=connection.execute("SELECT payload_bytes FROM geyser_raw_events WHERE event_id=?",(second.event_id,)).fetchone()
            raw=json.loads(row[0])
            raw["payload"]["data_base64"]="invalid!"
            connection.execute("UPDATE geyser_raw_events SET payload_bytes=? WHERE event_id=?",
                               (json.dumps(raw).encode(),second.event_id))
        previous=self.projection.get_checkpoint()
        recovery=SQLiteGeyserRecoveryStore(self.db)
        previous_recovery=recovery.get_projection_checkpoint(PROJECTION_NAME,PROJECTION_VERSION,self.source)
        with self.assertRaises(ValueError):
            self.projection.rebuild()
        self.assertEqual(len(self.projection.list_account_writes()),1)
        self.assertEqual(self.projection.get_checkpoint()["generation"],previous["generation"])
        self.assertEqual(
            recovery.get_projection_checkpoint(PROJECTION_NAME,PROJECTION_VERSION,self.source)["generation"],
            previous_recovery["generation"],
        )


if __name__ == "__main__":
    unittest.main()
