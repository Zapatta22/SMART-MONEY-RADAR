import unittest
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from smart_money_radar.services.cm38j_controlled_math import controlled_drawdown,controlled_valuation
import test_cm54_causal_economics as fixture

class ControlledEconomicMath(unittest.TestCase):
    def test_mark_and_future(self):
        t=datetime.now(timezone.utc)-timedelta(seconds=2)
        args=dict(quantity=D("2"),cost=D("10"),price=D("7"),market_at=t,available_at=t,cutoff=t)
        self.assertEqual(controlled_valuation(**args)["unrealized_pnl"],D("4"))
        with self.assertRaises(ValueError):
            controlled_valuation(**{**args,"available_at":t+timedelta(seconds=1)})
    def test_drawdown(self):
        t=datetime.now(timezone.utc)-timedelta(seconds=10)
        points=[(t+timedelta(seconds=i),t+timedelta(seconds=i),D(v)) for i,v in enumerate(("100","125","75","110"))]
        self.assertEqual(controlled_drawdown(points,cutoff=t+timedelta(seconds=5))["drawdown"],D(".4"))
        with self.assertRaises(ValueError):
            controlled_drawdown(points[::-1],cutoff=t+timedelta(seconds=5))
    def test_persisted_decision_all_indicators_unknown(self):
        f=fixture.CausalEconomics()
        f.setUp()
        try:
            f.record()
            import json
            with f.store._connection_scope() as c:
                payload=json.loads(c.execute("SELECT payload FROM cm38i_causal_economics").fetchone()[0])
            self.assertEqual(len(payload["metrics"]),9)
            self.assertTrue(all(m["value"] is None for m in payload["metrics"]))
            self.assertFalse(payload["qualification"]["complete_economic_evidence"])
            self.assertEqual(f.cap.snapshot("virtual"),f.before)
        finally:f.doCleanups()
