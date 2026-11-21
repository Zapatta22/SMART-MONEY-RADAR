"""Offline supervisor causal writer integration using existing RPC fixture."""
import unittest
from datetime import datetime,timezone
from decimal import Decimal as D
import test_cm54_causal_economics as fixture
from smart_money_radar.services.persistent_supervisor import PersistentSupervisor

class SupervisorEconomicCycle(unittest.TestCase):
    def setUp(self):
        fixture.CausalEconomics.setUp(self)

    def test_unconfigured_scope_is_blocked(self):
        s=PersistentSupervisor(self.store)
        with self.store._connection_scope() as c:
            self.assertEqual(s._economic_attempt(c,None,{},datetime.now(timezone.utc))["status"],"BLOCKED")
        self.assertEqual(self.cap.snapshot("virtual"),self.before)

    def test_configuration_requires_both_values(self):
        with self.assertRaises(ValueError):
            PersistentSupervisor(self.store,economic_account_id="virtual")


    def test_full_cycle_and_restart(self):
        import json,time
        from smart_money_radar.storage.event_store import SQLiteEventStore
        s=PersistentSupervisor(self.store,economic_account_id="virtual",economic_notional=D("10"))
        s.acquire()
        try:
            outcome=s.cycle()
            self.assertFalse(outcome["execution_enabled"])
            self.assertEqual(outcome["tasks"]["smart_money"]["status"],"READY")
            with self.store._connection_scope() as c:
                row=c.execute("SELECT payload FROM cm38i_causal_economics").fetchone()
                self.assertIsNotNone(row)
                payload=json.loads(row[0])
                self.assertEqual(payload["fifo"]["status"],"NOT_COMPUTABLE")
                self.assertEqual(payload["radar"],"smart_money")
                self.assertEqual(c.execute("SELECT COUNT(*) FROM cm38i_virtual_entry_attempts").fetchone()[0],1)
                path=c.execute("PRAGMA database_list").fetchone()[2]
            self.assertEqual(self.cap.snapshot("virtual"),self.before)
        finally:s.stop()
        reopened=SQLiteEventStore(path)
        try:
            from smart_money_radar.services.synthetic_capital import SyntheticCapitalCoordinator
            from smart_money_radar.services.persistent_supervisor import SupervisorPolicy
            # Wait for the persisted due time, not a fabricated future cutoff.
            delay=max(0,outcome["tasks"]["smart_money"]["next_due"]-time.time())
            time.sleep(delay+0.01)
            again=PersistentSupervisor(reopened,economic_account_id="virtual",economic_notional=D("10"))
            again.acquire()
            try:
                resumed=again.cycle()
                self.assertEqual(resumed["tasks"]["smart_money"]["status"],"READY")
                self.assertEqual(resumed["tasks"]["smart_money"]["checkpoint"],outcome["tasks"]["smart_money"]["checkpoint"])
                with reopened._connection_scope() as c:
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM cm38i_causal_economics").fetchone()[0],1)
                self.assertEqual(SyntheticCapitalCoordinator(reopened).snapshot("virtual"),self.before)
            finally:again.stop()
        finally:reopened.close()

    def test_journal_failure_rolls_back_causal_and_checkpoint(self):
        s=PersistentSupervisor(self.store,economic_account_id="virtual",economic_notional=D("10"))
        s.acquire()
        try:
            with self.store._connection_scope() as c,c:
                c.execute("""CREATE TRIGGER cm57_fail BEFORE INSERT ON cm36_decision_journal
                    WHEN NEW.radar='smart_money' BEGIN SELECT RAISE(ABORT,'injected'); END""")
            result=s.cycle()
            self.assertEqual(result["tasks"]["smart_money"]["status"],"BACKOFF")
            self.assertIsNone(result["tasks"]["smart_money"]["checkpoint"])
            self.assertEqual(result["tasks"]["launch"]["status"],"READY")
            with self.store._connection_scope() as c,c:
                exists=c.execute("SELECT 1 FROM sqlite_master WHERE name='cm38i_causal_economics'").fetchone()
                if exists:self.assertEqual(c.execute("SELECT COUNT(*) FROM cm38i_causal_economics").fetchone()[0],0)
                c.execute("DROP TRIGGER cm57_fail")
            self.assertEqual(self.cap.snapshot("virtual"),self.before)
        finally:s.stop()
