"""CM38G coverage audit uses persisted RAW, bounded intervals and UNKNOWN."""
import json,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from smart_money_radar.services.rpc_coverage_audit import assess_rpc_coverage
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.storage.event_store import SQLiteEventStore

class CoverageAuditTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=SQLiteEventStore(Path(temp.name)/"events.sqlite");self.addCleanup(self.store.close)
        self.at=datetime.now(timezone.utc)-timedelta(minutes=2)
        self.sig="1"*64
        self.window=dict(start=self.at-timedelta(seconds=20),
                         end=self.at+timedelta(seconds=20))
    def capture(self,radar="launch",source="provider-one",commitment="finalized",slot=42):
        raw=json.dumps({"jsonrpc":"2.0","result":{"slot":slot,"transaction":{
            "signatures":[self.sig],"message":{"instructions":[]}},"meta":{"err":None}}}).encode()
        return RpcObservationJournal(self.store).append(radar=radar,signature=self.sig,
            source_id=source,endpoint_host=source+".invalid",raw_payload=raw,
            observed_at=self.at,available_at=self.at,expected_slot=slot,
            commitment_requested=commitment)
    def audit(self,radar="launch",**kwargs):
        return assess_rpc_coverage(self.store,radar=radar,**dict(self.window,**kwargs))
    def test_empty_never_reports_full_coverage(self):
        report=self.audit()
        self.assertEqual(report["historical_coverage"],"UNKNOWN")
        self.assertEqual(report["verified_local_receipts"],0)
        self.assertIn("no_observations_in_interval",report["reasons"])
    def test_sources_and_commitments_do_not_prove_independent_finality(self):
        self.capture()
        self.capture(source="provider-two",commitment="confirmed")
        report=self.audit()
        self.assertEqual(report["distinct_signatures"],1)
        self.assertEqual(len(report["sources"]),2)
        self.assertEqual(report["historical_coverage"],"UNKNOWN")
        self.assertFalse(report["prospective_paper_authorized"])
        self.assertEqual(sum(s["requested_commitments"]["confirmed"] for s in report["sources"]),1)
        self.assertEqual(sum(s["requested_commitments"]["finalized"] for s in report["sources"]),1)
    def test_radar_and_source_isolation(self):
        self.capture()
        self.capture(radar="smart_money",source="provider-two",commitment="confirmed")
        self.assertEqual(self.audit(source_id="provider-two")["verified_local_receipts"],0)
        self.assertEqual(self.audit("smart_money")["verified_local_receipts"],1)
    def test_integrity_conflict_never_promotes_unknown(self):
        self.capture()
        with self.store._connection_scope() as conn,conn:
            conn.execute("UPDATE cm38_rpc_observations SET raw=?",(b"tampered",))
        report=self.audit()
        self.assertEqual(report["state"],"CONFLICTED")
        self.assertEqual(len(report["corrupt_evidence_ids"]),1)
    def test_truncated_or_future_intervals_fail_closed(self):
        self.capture()
        self.capture(source="second-provider")
        report=self.audit(limit=1)
        self.assertTrue(report["bounded_archive_truncated"])
        with self.assertRaises(ValueError):
            self.audit(end=datetime.now(timezone.utc)+timedelta(days=1))
