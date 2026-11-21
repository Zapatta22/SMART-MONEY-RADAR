"""CM31: actual SQLite producers to dashboard, no live RPC."""
import asyncio
import hashlib
import json
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

from smart_money_radar.services.dashboard_read import DashboardReadService
from smart_money_radar.services.launch_live_backfill import FinalizedLaunchBackfill, LaunchBackfillGap
from smart_money_radar.storage.event_store import SQLiteEventStore

RAW=(Path(__file__).resolve().parents[1]/"data/fixtures/mainnet/raydium-cpmm-launch/response.json").read_bytes()
TX=json.loads(RAW)["result"]
SIG=TX["transaction"]["signatures"][0]
SLOT=TX["slot"]

def synthetic(sig, slot):
    tx=json.loads(json.dumps(TX))
    tx["transaction"]["signatures"][0]=sig
    tx["slot"]=slot
    tx["meta"]["err"]={"InstructionError":[4,"Custom"]}
    return tx

class RPC:
    def __init__(self):
        self.txs=[TX]
        self.stop=None
    async def get_finalized_signatures_for_address_async(self,address,*,limit,before):
        entries=[{"signature":t["transaction"]["signatures"][0],"slot":t["slot"],"err":t["meta"]["err"]} for t in self.txs]
        return entries[:limit] if before is None else entries[next(i+1 for i,e in enumerate(entries) if e["signature"]==before):][:limit]
    async def get_finalized_transaction_async(self,sig):
        tx=next(t for t in self.txs if t["transaction"]["signatures"][0]==sig)
        if self.stop is not None:
            self.stop.set()
        return tx

class CM31Integration(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"smr.sqlite"
        self.store=SQLiteEventStore(self.db)
        self.addCleanup(self.store.close)
        self.rpc=RPC()
    def sync(self,stop=None):
        return asyncio.run(FinalizedLaunchBackfill(self.rpc,self.store,source_id="fixture",page_size=2,max_pages=3).synchronize("address",stop_event=stop))
    def cursor(self):
        return self.store.get_cpmm_launch_rpc_cursor("fixture:address")
    def test_finalized_fixture_writer_restart_dashboard_and_radar_isolation(self):
        self.store.save_checkpoint("fixture:address","smart-wallet-checkpoint")
        self.assertEqual(self.sync().new_deliveries,1)
        self.assertEqual(self.cursor(),{"signature":SIG,"last_sequence":0})
        self.store.close()
        self.store=SQLiteEventStore(self.db)
        self.assertEqual(self.sync().new_deliveries,0)
        self.assertEqual(self.store.get_checkpoint("fixture:address"),"smart-wallet-checkpoint")
        with sqlite3.connect(self.db) as conn:
            raw,sha=conn.execute("SELECT payload,sha256 FROM cpmm_launch_raw").fetchone()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),sha)
        reader=SQLiteEventStore(self.db,read_only=True)
        self.addCleanup(reader.close)
        data=DashboardReadService(reader).get_overview()
        event,=data["radar_events"]["launch"]
        self.assertEqual(event["signature"],SIG)
        self.assertEqual(event["slot"],SLOT)
        self.assertEqual(event["raw_sha256"],sha)
        self.assertEqual(event["coverage"],"UNKNOWN")
        self.assertEqual(event["origin"],"ARCHIVED_UNATTESTED")
        self.assertFalse(event["operational_authorized"])
        self.assertEqual(data["radar_events"]["smart_money"],[])
    def test_concurrent_writers_only_one_rpc_checkpoint_wins(self):
        gate=Barrier(2)
        def writer():
            s=SQLiteEventStore(self.db)
            try:
                gate.wait(timeout=5)
                s.archive_cpmm_launch_rpc_batch([RAW],source_id="race",first_sequence=0,expected_signature=None,latest_signature=SIG)
                return "committed"
            except ValueError:
                return "rejected"
            finally:
                s.close()
        with ThreadPoolExecutor(max_workers=2) as executor:
            a=executor.submit(writer)
            b=executor.submit(writer)
            self.assertCountEqual([a.result(timeout=20),b.result(timeout=20)],["committed","rejected"])
        self.assertEqual(self.store.get_cpmm_launch_rpc_cursor("race")["last_sequence"],0)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cpmm_launch_stream_delivery").fetchone()[0],1)
    def test_forged_checkpoint_and_corrupt_replay_rejected(self):
        with self.assertRaises(ValueError):
            self.store.archive_cpmm_launch_rpc_batch([RAW],source_id="x",first_sequence=0,expected_signature=None,latest_signature="forged")
        self.assertIsNone(self.store.get_cpmm_launch_rpc_cursor("x"))
        self.store.archive_cpmm_launches([RAW],source_id="stream",first_sequence=0)
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE cpmm_launch_raw SET payload=?",(b"corrupted",))
        with self.assertRaises(ValueError):
            self.store.archive_cpmm_launches([RAW],source_id="stream",first_sequence=0)
    def test_interruption_after_last_rpc_fetch_then_safe_resume(self):
        self.sync()
        self.rpc.txs.insert(0,synthetic("next",SLOT+1))
        stop=asyncio.Event()
        self.rpc.stop=stop
        with self.assertRaises(LaunchBackfillGap):
            self.sync(stop)
        self.assertEqual(self.cursor()["signature"],SIG)
        self.rpc.stop=None
        self.assertEqual(self.sync().new_deliveries,1)
        self.assertEqual(self.cursor(),{"signature":"next","last_sequence":1})
    def test_rollback_at_rpc_cursor_keeps_other_radar_intact(self):
        self.store.save_checkpoint("wallet","safe")
        with sqlite3.connect(self.db) as conn:
            conn.execute("""CREATE TRIGGER fail_rpc BEFORE INSERT ON cpmm_launch_rpc_cursor
                BEGIN SELECT RAISE(ABORT,'forced rollback'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.sync()
        self.assertIsNone(self.cursor())
        self.assertEqual(self.store.get_checkpoint("wallet"),"safe")
        with sqlite3.connect(self.db) as conn:
            for table in ("cpmm_launch_raw","cpmm_launch_evidence","cpmm_launch_stream_delivery","cpmm_launch_stream_cursor"):
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM "+table).fetchone()[0],0)
    def test_conflict_detected_beyond_dashboard_limit(self):
        self.store.archive_cpmm_launches([RAW])
        alternate=json.loads(RAW)
        alternate["result"]["transaction"]["signatures"][0]="1"*64
        self.store.archive_cpmm_launches([json.dumps(alternate).encode()])
        from smart_money_radar.services.radar_event_bridge import read_archived_radar_events
        event,=read_archived_radar_events(self.store,limit=1)["launch"]
        self.assertEqual(event["evidence_quality"],"CONFLICTED")

