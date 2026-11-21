"""CM38D checks economic child linkage and atomic Launch cursor advancement."""
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from smart_money_radar.domain.models import (
    SwapObservation,SwapClassification,SwapEvidence,build_swap_operation_id,
)
from smart_money_radar.domain.swap_bundle_builder import SwapDomainBundle
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.storage.event_store import SQLiteEventStore,SwapReconciliationRecord

class EconomicChildEvidenceLinks(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=SQLiteEventStore(Path(temp.name)/"smr.sqlite");self.addCleanup(self.store.close)
        self.wallet="public-wallet"
        self.signature="1"*64
        self.at=datetime.now(timezone.utc)-timedelta(minutes=2)
        self.tx={"slot":42,"transaction":{"signatures":[self.signature],
                  "message":{"instructions":[]}},"meta":{"err":None}}
    def capture(self,*,radar,source,commitment="confirmed"):
        payload=json.dumps({"jsonrpc":"2.0","result":self.tx},separators=(",",":")).encode()
        return RpcObservationJournal(self.store).append(radar=radar,
            signature=self.signature,source_id=source,endpoint_host="public-endpoint.invalid",
            raw_payload=payload,observed_at=self.at,available_at=self.at,
            expected_slot=42,commitment_requested=commitment)
    def add_swap(self):
        self.store.save_observation(self.wallet,self.signature,self.tx,[],
            parse_status="ok",advance_checkpoint=False)
        with self.store._connection_scope() as conn,conn:
            conn.execute("UPDATE observed_transactions SET slot=? WHERE wallet_address=? AND signature=?",
                (42,self.wallet,self.signature))
        op=build_swap_operation_id("solana",self.signature,0)
        obs=SwapObservation(op,"solana",self.wallet,self.signature,
            "quote","base",Decimal("10"),Decimal("2"),self.at,"1")
        cls=SwapClassification(op,"BUY",Decimal(".95"),"fixture")
        ev=SwapEvidence(op,"dex",None,0,evidence=("pool_state:pool",))
        self.store.save_swap_bundle(obs,cls,ev)
        self.store.save_swap_reconciliation_attempt(self.wallet,self.signature,
            [SwapReconciliationRecord(op,0,None,(),"MATCHED","fixture")])
        return op,SwapDomainBundle(obs,cls,ev)
    def test_swap_classification_reconciliation_and_opportunity_share_raw(self):
        evidence=self.capture(radar="smart_money",source="helius-wallet-rpc")
        op,bundle=self.add_swap()
        self.store.mark_processed(self.wallet,self.signature,
                                  replay_bundles=(bundle,),evidence_id=evidence)
        with self.store._connection_scope() as conn:
            rows=conn.execute("""SELECT entity_type,entity_id,evidence_id FROM cm38_economic_evidence_links
                                  WHERE radar='smart_money' ORDER BY entity_type""").fetchall()
        self.assertEqual({x[0] for x in rows},{
            "wallet_transaction","swap_and_classification",
            "economic_reconciliation","replay_opportunity"})
        self.assertTrue(all(row[2]==evidence for row in rows))
        self.assertEqual(self.store.get_checkpoint(self.wallet),self.signature)
    def test_failed_checkpoint_does_not_publish_child_links(self):
        evidence=self.capture(radar="smart_money",source="helius-wallet-rpc")
        _,bundle=self.add_swap()
        with patch.object(SQLiteEventStore,"_mark_processed_in_connection",side_effect=RuntimeError("crash")):
            with self.assertRaises(RuntimeError):
                self.store.mark_processed(self.wallet,self.signature,
                    replay_bundles=(bundle,),evidence_id=evidence)
        with self.store._connection_scope() as conn:
            links=conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm38_economic_evidence_links'").fetchone()
            if links:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM cm38_economic_evidence_links").fetchone()[0],0)
        self.assertIsNone(self.store.get_checkpoint(self.wallet))
    def test_launch_archive_and_cursor_linked_in_one_transaction(self):
        eid=self.capture(radar="launch",source="monitored",commitment="finalized")
        raw=json.dumps({"result":self.tx},separators=(",",":")).encode()
        self.store.archive_cpmm_launch_rpc_batch([raw],source_id="monitored",
            first_sequence=0,expected_signature=None,latest_signature=self.signature,
            evidence_ids=[eid])
        self.assertEqual(self.store.get_cpmm_launch_rpc_cursor("monitored")["signature"],self.signature)
        with self.store._connection_scope() as conn:
            linked=conn.execute("SELECT evidence_id FROM cm38_economic_evidence_links WHERE radar='launch'").fetchall()
        self.assertEqual(linked,[(eid,)])
    def test_launch_confirmed_transport_cannot_pass_finalized_gate(self):
        eid=self.capture(radar="launch",source="monitored",commitment="confirmed")
        raw=json.dumps({"result":self.tx},separators=(",",":")).encode()
        with self.assertRaises(ValueError):
            self.store.archive_cpmm_launch_rpc_batch([raw],source_id="monitored",
                first_sequence=0,expected_signature=None,latest_signature=self.signature,
                evidence_ids=[eid])
        self.assertIsNone(self.store.get_cpmm_launch_rpc_cursor("monitored"))
    def test_launch_missing_required_batch_evidence_is_rejected(self):
        self.capture(radar="launch",source="monitored",commitment="finalized")
        raw=json.dumps({"result":self.tx},separators=(",",":")).encode()
        with self.assertRaises(ValueError):
            self.store.archive_cpmm_launch_rpc_batch([raw],source_id="monitored",
                first_sequence=0,expected_signature=None,latest_signature=self.signature,
                evidence_ids=[None])
        self.assertIsNone(self.store.get_cpmm_launch_rpc_cursor("monitored"))
