"""CM38D atomic checkpoint and immutable transport evidence integration.

These are offline tests using real SQLite transactions, not attestations of
live provider authenticity.
"""
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.storage.event_store import SQLiteEventStore

class Cm38EvidenceCheckpoint(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"journal.sqlite"
        self.store=SQLiteEventStore(self.path);self.addCleanup(self.store.close)
        self.sig="1"*64
        self.wallet="fixture-public-wallet"
        self.at=datetime.now(timezone.utc)-timedelta(minutes=2)
        self.tx={"slot":42,"transaction":{"signatures":[self.sig],"message":{"instructions":[]}},
                 "meta":{"err":None}}
    def observe(self):
        self.store.save_observation(self.wallet,self.sig,self.tx,[],
            parse_status="processed",advance_checkpoint=False)
    def evidence(self,*,radar="smart_money",commitment="confirmed",signature=None,slot=42):
        sig=signature or self.sig
        tx=dict(self.tx,slot=slot,transaction={"signatures":[sig],"message":{"instructions":[]}})
        raw=json.dumps({"jsonrpc":"2.0","result":tx},separators=(",",":")).encode()
        return RpcObservationJournal(self.store).append(radar=radar,signature=sig,
            source_id="helius-wallet-rpc",endpoint_host="public-rpc.invalid",
            raw_payload=raw,observed_at=self.at,available_at=self.at,
            expected_slot=slot,commitment_requested=commitment)
    def links(self):
        with self.store._connection_scope() as conn:
            exists=conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm38_economic_evidence_links'").fetchone()
            if exists is None:return []
            return conn.execute("SELECT entity_type,evidence_id FROM cm38_economic_evidence_links ORDER BY entity_type").fetchall()
    def test_capture_must_link_before_checkpoint(self):
        eid=self.evidence();self.observe()
        with self.assertRaises(ValueError):
            self.store.mark_processed(self.wallet,self.sig)
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
        self.assertEqual(self.links(),[])
        self.store.mark_processed(self.wallet,self.sig,evidence_id=eid)
        self.assertEqual(self.store.get_checkpoint(self.wallet),self.sig)
        self.assertEqual(self.links(),[("wallet_transaction",eid)])
    def test_repeated_checkpoint_is_idempotent_across_restart(self):
        eid=self.evidence();self.observe()
        self.store.mark_processed(self.wallet,self.sig,evidence_id=eid)
        self.store.mark_processed(self.wallet,self.sig,evidence_id=eid)
        reopened=SQLiteEventStore(self.path,read_only=True)
        try:
            self.assertEqual(reopened.get_checkpoint(self.wallet),self.sig)
        finally:reopened.close()
        self.assertEqual(self.links(),[("wallet_transaction",eid)])
    def test_wrong_commitment_and_wrong_radar_rejected(self):
        self.observe()
        eid=self.evidence(commitment="finalized")
        with self.assertRaises(ValueError):
            self.store.mark_processed(self.wallet,self.sig,evidence_id=eid)
        with self.assertRaises(ValueError):
            self.store.mark_processed(self.wallet,self.sig,evidence_id=self.evidence(radar="launch"))
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
        self.assertEqual(self.links(),[])
    def test_slot_and_signature_divergence_block_commit(self):
        self.observe()
        with self.store._connection_scope() as conn,conn:
            conn.execute("UPDATE observed_transactions SET slot=43 WHERE signature=?",(self.sig,))
        eid=self.evidence()
        with self.assertRaises(ValueError):
            self.store.mark_processed(self.wallet,self.sig,evidence_id=eid)
        with self.assertRaises(ValueError):
            self.store.mark_processed(self.wallet,self.sig,evidence_id=self.evidence(signature="2"*64))
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
    def test_corrupted_raw_rejected_without_advancing(self):
        eid=self.evidence();self.observe()
        with self.store._connection_scope() as conn,conn:
            conn.execute("UPDATE cm38_rpc_observations SET raw=? WHERE evidence_id=?",(b"divergent",eid))
        with self.assertRaises(ValueError):
            self.store.mark_processed(self.wallet,self.sig,evidence_id=eid)
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
    def test_interruption_after_link_rolls_back_everything(self):
        eid=self.evidence();self.observe()
        with patch.object(SQLiteEventStore,"_mark_processed_in_connection",side_effect=RuntimeError("crash after evidence link")):
            with self.assertRaisesRegex(RuntimeError,"crash after evidence link"):
                self.store.mark_processed(self.wallet,self.sig,evidence_id=eid)
        self.assertEqual(self.links(),[])
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
        self.store.mark_processed(self.wallet,self.sig,evidence_id=eid)
        self.assertEqual(self.links(),[("wallet_transaction",eid)])
    def test_legacy_uncaptured_observation_keeps_unknown_semantics(self):
        self.observe()
        self.store.mark_processed(self.wallet,self.sig)
        self.assertEqual(self.links(),[])
        self.assertEqual(self.store.get_checkpoint(self.wallet),self.sig)
