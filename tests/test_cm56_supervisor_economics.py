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
