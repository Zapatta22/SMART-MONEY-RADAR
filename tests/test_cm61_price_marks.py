import unittest,json
from datetime import datetime,timezone,timedelta
import test_cm54_causal_economics as fixture
from smart_money_radar.services.cm38j_price_marks import persist_mark,read_mark

class PriceMarks(unittest.TestCase):
    def setUp(self):
        fixture.CausalEconomics.setUp(self)
        self.at=datetime.now(timezone.utc)-timedelta(seconds=2)
        self.raw=json.dumps(dict(asset="base",quote="quote",source="offline-fixture",market_at=self.at.isoformat(),available_at=self.at.isoformat(),bid="6",ask="7"))
    def test_temporal_and_idempotent(self):
        eid=persist_mark(self.store,self.raw)
        self.assertEqual(eid,persist_mark(self.store,self.raw))
        with self.store._connection_scope() as c:
            self.assertIsNone(read_mark(c,asset="base",quote="quote",cutoff=self.at-timedelta(seconds=1)))
            self.assertEqual(read_mark(c,asset="base",quote="quote",cutoff=self.at)["evidence_id"],eid)
            self.assertIsNone(read_mark(c,asset="base",quote="other",cutoff=self.at))
            self.assertIsNone(read_mark(c,asset="base",quote="quote",cutoff=datetime.now(timezone.utc),max_age_seconds=1))
    def test_causal_mark_does_not_authorize(self):
        persist_mark(self.store,self.raw)
        from smart_money_radar.services.cm38i_decision_audit import record_blocked_virtual_entry
        result=record_blocked_virtual_entry(self.store,**self.args)
        self.assertFalse(result["prospective_authorized"])
        with self.store._connection_scope() as c:
            p=json.loads(c.execute("SELECT payload FROM cm38i_causal_economics").fetchone()[0])
        self.assertEqual(p["fifo"]["valuation"]["status"],"NOT_COMPUTABLE")
        self.assertIsNotNone(p["fifo"]["valuation"]["mark"])
        self.assertEqual(self.cap.snapshot("virtual"),self.before)
