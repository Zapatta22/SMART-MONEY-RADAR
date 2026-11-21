"""CM38D Geyser account frames are linked only as UNKNOWN temporal context."""
import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.services.geyser_rpc_context import link_geyser_rpc_context

class GeyserRpcContextTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        path=Path(tmp.name)/"shared.sqlite"
        self.store=SQLiteEventStore(path);self.addCleanup(self.store.close)
        self.geyser=SQLiteGeyserRawStore(path);self.addCleanup(self.geyser.close)
        self.geyser.register_frame_stream("ws","session","ordering-domain",0)
        receipt=self.geyser.append_wire_frame(source_id="ws",stream_id="session",
            ordering_domain_id="ordering-domain",stream_sequence=0,
            payload=b"account-state-not-transaction",frame_kind="account")
        self.frame_id=receipt.frame_id
        sig="1"*64;at=datetime.now(timezone.utc)-timedelta(minutes=1)
        raw=json.dumps({"jsonrpc":"2.0","result":{"slot":42,"transaction":{
            "signatures":[sig],"message":{"instructions":[]}},"meta":{"err":None}}}).encode()
        self.eid=RpcObservationJournal(self.store).append(radar="launch",signature=sig,
            source_id="rpc-provider",endpoint_host="provider.invalid",raw_payload=raw,
            observed_at=at,available_at=at,expected_slot=42)
    def test_context_is_idempotent_and_never_authorizes(self):
        args=dict(frame_id=self.frame_id,evidence_id=self.eid,cutoff=datetime.now(timezone.utc))
        a=link_geyser_rpc_context(self.store,self.geyser,**args)
        b=link_geyser_rpc_context(self.store,self.geyser,**args)
        self.assertEqual(a,b)
        self.assertEqual(a["relation"],"TEMPORAL_CONTEXT_ONLY")
        self.assertEqual(a["transaction_inclusion"],"UNKNOWN")
        self.assertFalse(a["prospective_paper_authorized"])
        with self.store._connection_scope() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM cm38_geyser_rpc_context").fetchone()[0],1)
    def test_hash_tamper_and_future_cutoff_rejected(self):
        with self.store._connection_scope() as conn,conn:
            conn.execute("UPDATE geyser_wire_frames SET payload_bytes=? WHERE frame_id=?",
                         (b"spoofed",self.frame_id))
        with self.assertRaises(ValueError):
            link_geyser_rpc_context(self.store,self.geyser,frame_id=self.frame_id,
                evidence_id=self.eid,cutoff=datetime.now(timezone.utc))
    def test_unavailable_frame_fails_without_link(self):
        with self.assertRaises(ValueError):
            link_geyser_rpc_context(self.store,self.geyser,frame_id=self.frame_id,
                evidence_id=self.eid,cutoff=datetime.now(timezone.utc)-timedelta(days=1))
        with self.store._connection_scope() as conn:
            self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm38_geyser_rpc_context'").fetchone())
