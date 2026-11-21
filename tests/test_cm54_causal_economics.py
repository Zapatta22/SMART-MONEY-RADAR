"""CM54 causal economic snapshot: actual persisted synthetic RPC fixture."""
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal as D
import test_cm38k_fifo_end_to_end as fixtures
from smart_money_radar.services.synthetic_capital import SyntheticCapitalCoordinator, CapitalLimits
from smart_money_radar.services.cm38i_decision_audit import record_blocked_virtual_entry, audit_blocked_entry

class CausalEconomics(unittest.TestCase):
    def setUp(self):
        fixtures.PersistedEconomicFixture.setUp(self)
        self.cap=SyntheticCapitalCoordinator(self.store)
        self.cap.create(account_id="virtual",initial=D("100"),currency="USDC",
            radars=("smart_money",),limits=CapitalLimits(*([D(".8")]*8)))
        self.before=self.cap.snapshot("virtual")
        self.args=dict(request_id="causal",account_id="virtual",radar="smart_money",
            strategy="confirmed",evidence_id=self.eid,decision_at=datetime.now(timezone.utc),
            requested_notional=D("10"),economic_scope=(self.wallet,"base","quote"))

    def record(self,**kwargs):
        return record_blocked_virtual_entry(self.store,**{**self.args,**kwargs})

    def test_atomic_causal_replay_and_capital(self):
        first=self.record()
        self.assertEqual(first["status"],"BLOCKED")
        self.assertTrue(self.record()["idempotent_replay"])
        self.assertEqual(self.cap.snapshot("virtual"),self.before)
        import json
        with self.store._connection_scope() as c:
            payload=json.loads(c.execute("SELECT payload FROM cm38i_causal_economics").fetchone()[0])
        self.assertEqual(payload["fifo"]["status"],"NOT_COMPUTABLE")
        self.assertEqual(payload["metrics"][0]["source_integrity_sha256"],payload["fifo"]["sha256"])
        self.assertFalse(audit_blocked_entry(self.store,"causal")["prospective_authorized"])
        with self.assertRaises(ValueError):
            self.record(economic_scope=(self.wallet,"other","quote"))

    def test_scope_and_future_rejected(self):
        with self.assertRaises(ValueError):
            self.record(radar="launch")
        with self.assertRaises(ValueError):
            self.record(decision_at=datetime.now(timezone.utc)+timedelta(seconds=30))
        with self.assertRaises(ValueError):
            self.record(economic_scope=("other","base","quote"))
        self.assertIsNone(audit_blocked_entry(self.store,"causal"))
        self.assertEqual(self.cap.snapshot("virtual"),self.before)

    def test_tampered_snapshot_detected(self):
        self.record()
        with self.store._connection_scope() as c,c:
            c.execute("DROP TRIGGER cm38i_causal_no_update")
            c.execute("UPDATE cm38i_causal_economics SET payload='{}'")
        with self.assertRaises(ValueError):
            audit_blocked_entry(self.store,"causal")
