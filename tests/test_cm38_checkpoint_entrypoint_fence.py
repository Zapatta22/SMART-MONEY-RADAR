"""CM38G: all wallet checkpoint entrypoints reject captured RPC bypass."""
import json
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal

class CheckpointEntrypointGates(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=SQLiteEventStore(Path(self.tmp.name)/"events.sqlite");self.addCleanup(self.store.close)
        self.wallet="offline-wallet";self.sig="1"*64
        self.at=datetime.now(timezone.utc)-timedelta(minutes=3)
        self.tx={"slot":42,"transaction":{"signatures":[self.sig],"message":{"instructions":[]}},"meta":{"err":None}}
        raw=json.dumps({"jsonrpc":"2.0","result":self.tx}).encode()
        self.eid=RpcObservationJournal(self.store).append(radar="smart_money",
            signature=self.sig,source_id="helius-wallet-rpc",endpoint_host="provider.invalid",
            raw_payload=raw,observed_at=self.at,available_at=self.at,expected_slot=42,
            commitment_requested="confirmed")
    def test_save_observation_default_cannot_bypass_capture(self):
        with self.assertRaises(ValueError):
            self.store.save_observation(self.wallet,self.sig,self.tx,[],parse_status="ok")
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
        with self.store._connection_scope() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM observed_transactions WHERE signature=?",(self.sig,)).fetchone())
    def test_save_checkpoint_cannot_bypass_capture(self):
        self.store.save_observation(self.wallet,self.sig,self.tx,[],parse_status="ok",advance_checkpoint=False)
        with self.assertRaises(ValueError):
            self.store.save_checkpoint(self.wallet,self.sig)
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
        self.store.mark_processed(self.wallet,self.sig,evidence_id=self.eid)
        self.store.save_checkpoint(self.wallet,self.sig)
        self.assertEqual(self.store.get_checkpoint(self.wallet),self.sig)
    def test_uncaptured_legacy_observation_keeps_unknown_status(self):
        other="2"*64
        self.store.save_observation(self.wallet,other,{"slot":1},[],parse_status="legacy")
        self.assertEqual(self.store.get_checkpoint(self.wallet),other)
        self.store.save_checkpoint(self.wallet,other)
        self.assertEqual(self.store.get_checkpoint(self.wallet),other)
    def test_legacy_bootstrap_without_observed_parent_remains_valid(self):
        self.store.save_checkpoint("legacy-bootstrap","unobserved-signature")
        self.assertEqual(self.store.get_checkpoint("legacy-bootstrap"),"unobserved-signature")
        self.assertIsNone(self.store.get_checkpoint(self.wallet))

    def test_reprocessing_does_not_advance_cursor(self):
        self.store.save_observation(self.wallet,self.sig,self.tx,[],parse_status="ok",advance_checkpoint=False)
        self.store.reprocess_observation(self.wallet,self.sig,[],parse_status="ok",parser_version="2")
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
    def test_failure_after_link_rolls_back(self):
        self.store.save_observation(self.wallet,self.sig,self.tx,[],parse_status="ok",advance_checkpoint=False)
        with patch.object(SQLiteEventStore,"_mark_processed_in_connection",side_effect=RuntimeError("crash")):
            with self.assertRaisesRegex(RuntimeError,"crash"):
                self.store.mark_processed(self.wallet,self.sig,evidence_id=self.eid)
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
        with self.store._connection_scope() as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm38_economic_evidence_links'").fetchone():
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM cm38_economic_evidence_links").fetchone()[0],0)
