"""CM38A scope, first publication, integrity and fail-closed paper gates."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import json
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal

class RpcObservationJournalTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.s=SQLiteEventStore(Path(tmp.name)/"e.sqlite");self.addCleanup(self.s.close)
        self.j=RpcObservationJournal(self.s)
        self.at=datetime.now(timezone.utc)-timedelta(seconds=30)
        self.sig="1"*64
    def add(self,radar="launch",source="one",host="one.invalid",slot=42,at=None):
        point=at or self.at
        raw=json.dumps({"jsonrpc":"2.0","result":{"slot":slot,"transaction":{"signatures":[self.sig],"message":{"instructions":[]}},"meta":{"err":None}}}).encode()
        return self.j.append(radar=radar,signature=self.sig,source_id=source,endpoint_host=host,
            raw_payload=raw,observed_at=point,available_at=point,expected_slot=slot)
    def assess(self,radar="launch",cutoff=None):
        return self.j.assess(radar=radar,signature=self.sig,cutoff=cutoff or self.at)
    def test_dedup_and_first_publication(self):
        first=self.add();self.assertEqual(first,self.add(at=self.at+timedelta(seconds=2)))
        self.assertEqual(self.assess()["evidence_ids"],[first])
        self.assertEqual(self.assess(cutoff=self.at-timedelta(seconds=1))["evidence_ids"],[])
    def test_radar_scope_and_no_authorization(self):
        self.add();self.add("smart_money","two","two.invalid")
        self.assertEqual(len(self.assess()["evidence_ids"]),1)
        self.assertEqual(len(self.assess("smart_money")["evidence_ids"]),1)
        self.assertFalse(self.assess()["prospective_paper_authorized"])
    def test_source_corroboration_is_not_authenticated(self):
        self.add();self.add(source="two",host="two.invalid")
        result=self.assess()
        self.assertEqual(result["status"],"CROSS_SOURCE_CONSISTENT_UNATTESTED")
        self.assertFalse(result["independently_finalized"])
        self.assertFalse(result["provider_authenticated"])
        self.assertEqual(result["economic_qualification"],"UNKNOWN")
    def test_slot_conflict(self):
        self.add();self.add(source="two",host="two.invalid",slot=43)
        self.assertEqual(self.assess()["status"],"CONFLICTED")
    def test_payload_corruption(self):
        self.add()
        with self.s._connection_scope() as conn,conn:
            conn.execute("UPDATE cm38_rpc_observations SET raw=?", (b"tampered",))
        self.assertEqual(self.assess()["status"],"CONFLICTED")
    def test_future_rejected(self):
        with self.assertRaises(ValueError):self.add(at=datetime.now(timezone.utc)+timedelta(hours=1))
        with self.assertRaises(ValueError):self.assess(cutoff=datetime.now(timezone.utc)+timedelta(hours=1))
