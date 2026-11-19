import base64
import sqlite3
import tempfile
import unittest
from pathlib import Path

from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate
from smart_money_radar.data_sources.geyser_bank_lineage import (
    NormalizedBlockMeta, NormalizedEntryUpdateParent, NormalizedSlotUpdate,
)
from smart_money_radar.data_sources.geyser_ingestion import ingest_normalized_event
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
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

    def test_rebuild_is_repeatable_and_checkpoint_is_versioned(self):
        self.add(self.account(100,1,1))
        first=self.projection.rebuild()
        second=self.projection.rebuild()
        self.assertEqual(second["generation"],first["generation"]+1)
        checkpoint=self.projection.get_checkpoint()
        self.assertEqual(checkpoint["projection_name"],PROJECTION_NAME)
        self.assertEqual(checkpoint["projection_version"],PROJECTION_VERSION)
        self.assertEqual(len(self.projection.list_account_writes()),1)

    def test_late_raw_event_is_included_on_full_rebuild(self):
        self.add(self.account(100,2,2,pubkey="later"))
        self.projection.rebuild()
        self.add(self.account(99,1,3,pubkey="earlier"))
        result=self.projection.rebuild()
        self.assertEqual(result["account_write_count"],2)

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
        with self.assertRaises(ValueError):
            self.projection.rebuild()
        self.assertEqual(len(self.projection.list_account_writes()),1)
        self.assertEqual(self.projection.get_checkpoint()["generation"],previous["generation"])


if __name__ == "__main__":
    unittest.main()
