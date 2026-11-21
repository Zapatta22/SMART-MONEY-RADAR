"""CM37H: enforce radar/strategy budget under shared SQLite transaction."""
from datetime import datetime,timezone
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
import unittest
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.synthetic_capital import SyntheticCapitalCoordinator,CapitalLimits
from smart_money_radar.services.operational_controls import LocalOperationalControls
from smart_money_radar.domain.paper_replay import PaperConfig
from smart_money_radar.domain.paper_entry_risk_policy import EntryRiskLimits

class ScopedBudgetTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"cap.sqlite"
        self.store=SQLiteEventStore(self.path);self.addCleanup(self.store.close)
        self.cap=SyntheticCapitalCoordinator(self.store)
        self.at=datetime(2026,1,1,tzinfo=timezone.utc)
        self.limits=CapitalLimits(*([D("1")]*8))
        self.config=PaperConfig(D("20"),D("5"),D(".5"))
        self.risk=EntryRiskLimits(D(".5"),D(".1"),D("100"),D("1"))
        self.cap.create(account_id="a",initial=D("100"),currency="USDC",radars=("launch","smart_money"),limits=self.limits)
        key=b"fixture"*8
        ctl=LocalOperationalControls(self.store,operator_capability=key)
        for eid,action,radar in (("l","START","launch"),("s","START","smart_money"),("e","RESUME_ENTRIES",None)):
            ctl.apply(capability=key,event_id=eid,action=action,actor="test",at=self.at,radar=radar,reason="offline")
        self.budgets={"launch":{"immediate":"20","confirmed":"0"},"smart_money":{"immediate":"20","confirmed":"20"}}
    def policy(self,budgets=None):
        return self.cap.update_future_policy("a",event_id="policy",limits=self.limits,config=self.config,risk_limits=self.risk,at=self.at,budgets=budgets or self.budgets)
    def reserve(self,rid,radar="launch",strategy="immediate",coordinator=None):
        return (coordinator or self.cap).reserve("a",event_id="r-"+rid,run_id=rid,radar=radar,pool="p",token="t",wallet="w",strategy=strategy,config=self.config,risk_limits=self.risk,at=self.at)
    def test_distinct_budgets_and_zero(self):
        self.policy()
        self.reserve("a1")
        with self.assertRaises(ValueError):self.reserve("a2")
        with self.assertRaises(ValueError):self.reserve("a3",strategy="confirmed")
        self.reserve("s1","smart_money")
        self.assertEqual(self.cap.snapshot("a")["capital_reserved"],"40")
    def test_sum_limit_and_persistence(self):
        with self.assertRaises(ValueError):self.policy({"launch":{"immediate":"101","confirmed":"0"},"smart_money":{"immediate":"0","confirmed":"0"}})
        self.policy()
        reopened=SQLiteEventStore(self.path,read_only=True)
        try:self.assertEqual(SyntheticCapitalCoordinator(reopened).snapshot("a")["strategy_budgets"],self.budgets)
        finally:reopened.close()
    def test_concurrent_reservations_cannot_double_spend_budget(self):
        self.policy()
        def attempt(rid):
            db=SQLiteEventStore(self.path)
            try:
                self.reserve(rid,coordinator=SyntheticCapitalCoordinator(db));return True
            except ValueError:return False
            finally:db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt,["r1","r2"])),[False,True])
        self.assertEqual(self.cap.snapshot("a")["capital_reserved"],"20")
