"""CM38H reprocessing: preserve evidence linkage and append-only history."""
import json
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.storage.event_store import SQLiteEventStore

class ReprocessingHistoryTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=SQLiteEventStore(Path(tmp.name)/"events.sqlite");self.addCleanup(self.store.close)
        self.wallet="wallet-test";self.sig="1"*64
        at=datetime.now(timezone.utc)-timedelta(minutes=2)
        self.tx={"slot":42,"transaction":{"signatures":[self.sig],"message":{"instructions":[]}},"meta":{"err":None}}
        raw=json.dumps({"jsonrpc":"2.0","result":self.tx}).encode()
        self.eid=RpcObservationJournal(self.store).append(
            radar="smart_money",signature=self.sig,source_id="helius-wallet-rpc",
            endpoint_host="provider.invalid",raw_payload=raw,observed_at=at,available_at=at,
            expected_slot=42,commitment_requested="confirmed")
        self.store.save_observation(self.wallet,self.sig,self.tx,[],parse_status="ok",advance_checkpoint=False)
    def rows(self):
        with self.store._connection_scope() as conn:
            return conn.execute("SELECT evidence_id,parser_version,previous_sha256,receipt_sha256 FROM cm38_reprocessing_history ORDER BY rowid").fetchall()
    def test_reparse_requires_original_link_when_raw_captured(self):
        with self.assertRaises(ValueError):
            self.store.reprocess_observation(self.wallet,self.sig,[],parse_status="ok",parser_version="2")
        with self.store._connection_scope() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm38_reprocessing_history'").fetchone())
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
    def test_reparse_linked_twice_preserves_chain(self):
        self.store.mark_processed(self.wallet,self.sig,evidence_id=self.eid)
        self.store.reprocess_observation(self.wallet,self.sig,[],parse_status="ok",parser_version="2")
        self.store.reprocess_observation(self.wallet,self.sig,[],parse_status="ok",parser_version="3")
        a,b=self.rows()
        self.assertEqual(a[0],self.eid)
        self.assertEqual(b[0],self.eid)
        self.assertIsNone(a[2])
        self.assertEqual(b[2],a[3])
        self.assertEqual(self.store.get_checkpoint(self.wallet),self.sig)
    def test_corrupted_rpc_blocks_reparse_without_history(self):
        self.store.mark_processed(self.wallet,self.sig,evidence_id=self.eid)
        with self.store._connection_scope() as conn,conn:
            conn.execute("UPDATE cm38_rpc_observations SET raw=? WHERE evidence_id=?",(b"corrupt",self.eid))
        with self.assertRaises(ValueError):
            self.store.reprocess_observation(self.wallet,self.sig,[],parse_status="ok",parser_version="2")
        with self.store._connection_scope() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm38_reprocessing_history'").fetchone())
    def test_reparse_crash_rolls_back_derived_and_history(self):
        self.store.mark_processed(self.wallet,self.sig,evidence_id=self.eid)
        with patch.object(SQLiteEventStore,"_cm38_link_in_connection",side_effect=RuntimeError("crash")):
            with self.assertRaisesRegex(RuntimeError,"crash"):
                self.store.reprocess_observation(self.wallet,self.sig,[],parse_status="ok",parser_version="3")
        self.assertEqual(self.store.get_observation_metadata(self.wallet,self.sig)["parser_version"],"1")
        with self.store._connection_scope() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm38_reprocessing_history'").fetchone())
    def test_uncaptured_legacy_reprocess_keeps_unknown_link(self):
        legacy="2"*64
        self.store.save_observation(self.wallet,legacy,{"slot":2},[],parse_status="legacy",advance_checkpoint=False)
        self.store.reprocess_observation(self.wallet,legacy,[],parse_status="ok",parser_version="2")
        self.assertEqual(self.rows()[0][0],None)
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
