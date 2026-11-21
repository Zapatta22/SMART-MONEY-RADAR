"""CM34 synthetic transactions, control gates and capital race tests."""
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from smart_money_radar.domain.paper_replay import PaperConfig,ReplayTick
from smart_money_radar.domain.paper_entry_risk_policy import EntryRiskLimits
from smart_money_radar.services.synthetic_capital import CapitalLimits,SyntheticCapitalCoordinator,read_capital_accounts
from smart_money_radar.services.operational_controls import LocalOperationalControls,read_operational_status
from smart_money_radar.services.synthetic_paper_ledger import SyntheticPaperLedger
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.dashboard_read import DashboardReadService
T=datetime(2026,11,21,tzinfo=timezone.utc)
KEY=b"x"*32
def cap(**kw):
    return CapitalLimits(**dict(dict(total_exposure=D("1"),per_radar=D("1"),per_strategy=D("1"),
        per_token=D("1"),per_pool=D("1"),per_wallet=D("1"),max_daily_loss=D(".1"),max_drawdown=D(".2")),**kw))
def config(budget):
    return PaperConfig(D(budget),D(budget)/D("2"),D("1"),fee_bps=D("10"),slippage_bps=D("10"),allow_partial_fills=True)
def risk():
    return EntryRiskLimits(D("1"),D(".1"),D("100"),D("1"))
def q(n,side="NONE",price="10",depth="100"):
    t=T+timedelta(seconds=n);p=D(price)
    return ReplayTick(t,p,D("100"),side,True,False,market_at=t,bid=p,ask=p,bid_size=D(depth),ask_size=D(depth),quote_id="q"+str(n))
class CM34Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"smr.sqlite"
        self.store=SQLiteEventStore(self.db);self.addCleanup(self.store.close)
        self.coord=SyntheticCapitalCoordinator(self.store)
        self.ctl=LocalOperationalControls(self.store,operator_capability=KEY)
        for i,r in enumerate(("launch","smart_money")):
            self.ctl.apply(capability=KEY,event_id="start"+r,action="START",actor="fixture",at=T,radar=r,reason="test")
        self.control("resume","RESUME_ENTRIES")
    def control(self,eid,action,radar=None,key=KEY,at=T):
        return self.ctl.apply(capability=key,event_id=eid,action=action,actor="fixture",at=at,radar=radar,reason="test")
    def create(self,limits=None,radars=("launch","smart_money")):
        self.coord.create(account_id="a",initial=D("1000"),currency="TEST_QUOTE",radars=radars,limits=limits or cap())
    def reserve(self,rid="l",budget="400",radar="launch",token=None,coord=None):
        return (coord or self.coord).reserve("a",event_id="reserve"+rid,run_id=rid,radar=radar,pool="p"+rid,
            token=token or rid,wallet="w"+rid,strategy="immediate",config=config(budget),risk_limits=risk(),at=T)
    def test_two_concurrent_reservations_cannot_double_spend(self):
        self.create()
        gate=Barrier(2)
        def worker(rid):
            store=SQLiteEventStore(self.db)
            try:
                gate.wait(timeout=5)
                self.reserve(rid,"700",coord=SyntheticCapitalCoordinator(store))
                return "accepted"
            except ValueError: return "blocked"
            finally:store.close()
        with ThreadPoolExecutor(2) as e:
            a=e.submit(worker,"x");b=e.submit(worker,"y")
            self.assertCountEqual([a.result(timeout=20),b.result(timeout=20)],["accepted","blocked"])
        s=self.coord.snapshot("a")
        self.assertEqual(D(s["capital_reserved"]),700)
        self.assertEqual(D(s["capital_available"]),300)
    def test_two_open_positions_reopen_partial_exit_and_settlement(self):
        self.create();self.reserve();self.reserve("s",radar="smart_money")
        for rid in ("l","s"):
            self.coord.tick("a",run_id=rid,tick=q(1,"BUY"),signal_id="entry"+rid)
        for rid in ("l","s"):
            self.coord.tick("a",run_id=rid,tick=q(2,depth="2"))
        snapshot=self.coord.snapshot("a")
        self.assertEqual(len(snapshot["positions"]),2)
        self.assertTrue(all(D(p["report"]["open_quantity"])>0 for p in snapshot["positions"]))
        self.store.close();self.store=SQLiteEventStore(self.db);self.addCleanup(self.store.close)
        self.coord=SyntheticCapitalCoordinator(self.store)
        self.assertEqual(self.coord.snapshot("a"),snapshot)
        with self.assertRaises(ValueError): self.coord.settle("a",run_id="l",event_id="early",at=T+timedelta(seconds=3))
        self.coord.tick("a",run_id="l",tick=q(3,"SELL"),signal_id="exit")
        self.coord.tick("a",run_id="l",tick=q(4,depth="1"))
        self.coord.tick("a",run_id="l",tick=q(5))
        s=self.coord.settle("a",run_id="l",event_id="settle",at=T+timedelta(seconds=5))
        self.assertEqual(D(s["capital_reserved"]),400)
        self.assertEqual(len(s["positions"]),1)
        self.assertEqual(s["positions"][0]["radar"],"smart_money")
        self.assertEqual(s["settled_runs"],1)
        self.assertEqual(D(s["equity"]),D(s["initial_capital"])+D(s["realized_pnl"])+D(s["unrealized_pnl"]))
    def test_aggregate_token_and_independent_radar_limits(self):
        self.create(cap(per_token=D(".5")),radars=("launch",))
        self.reserve(token="same")
        with self.assertRaises(ValueError): self.reserve("x","200",token="same")
        with self.assertRaises(ValueError): self.reserve("s","100",radar="smart_money")
        self.assertEqual(D(self.coord.snapshot("a")["capital_reserved"]),400)
    def test_atomic_reserve_rollback(self):
        self.create()
        with sqlite3.connect(self.db) as c:
            c.execute("CREATE TRIGGER fail_alloc BEFORE INSERT ON cm34_capital_journal BEGIN SELECT RAISE(ABORT,'forced'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.reserve()
        self.assertEqual(D(self.coord.snapshot("a")["capital_available"]),1000)
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM cm33_paper_runs").fetchone()[0],0)
    def test_unauthorized_control_and_fault_isolation_and_sticky_halt(self):
        self.create()
        with self.assertRaises(PermissionError):self.control("bad","EMERGENCY_HALT",key=b"wrong")
        self.reserve();self.reserve("s",radar="smart_money")
        self.control("fault","RADAR_FAULT","launch",at=T+timedelta(seconds=1))
        self.coord.tick("a",run_id="l",tick=q(1,"BUY"),signal_id="entry_l")
        self.coord.tick("a",run_id="s",tick=q(1,"BUY"),signal_id="entry_s")
        self.coord.tick("a",run_id="l",tick=q(2))
        self.coord.tick("a",run_id="s",tick=q(2))
        s=self.coord.snapshot("a")
        self.assertEqual(D(s["positions"][0]["report"]["open_quantity"]),0)
        self.assertGreater(D(s["positions"][1]["report"]["open_quantity"]),0)
        self.control("halt","EMERGENCY_HALT",at=T+timedelta(seconds=3))
        with self.assertRaises(ValueError):self.control("restart","START","launch",at=T+timedelta(seconds=4))
        with self.assertRaises(ValueError):self.control("live","LIVE",at=T+timedelta(seconds=4))
        self.assertTrue(read_operational_status(self.store)["emergency_halt"])
    def test_duplicate_quote_signal_bypass_and_corruption(self):
        self.create();self.reserve();self.reserve("x")
        first=self.coord.tick("a",run_id="l",tick=q(1,"BUY"),signal_id="same")
        self.assertEqual(first,self.coord.tick("a",run_id="l",tick=q(1,"BUY"),signal_id="same"))
        with self.assertRaises(ValueError):self.coord.tick("a",run_id="x",tick=q(1,"BUY"),signal_id="same")
        with self.assertRaises(ValueError):SyntheticPaperLedger(self.store).append("l",tick=q(2))
        with sqlite3.connect(self.db) as c:c.execute("UPDATE cm34_capital_journal SET payload='{}' WHERE seq=0")
        self.assertEqual(read_capital_accounts(self.store)[0]["status"],"CONFLICTED")
        with self.assertRaises(ValueError):self.coord.tick("a",run_id="l",tick=q(2))
    def test_read_only_dashboard_and_alert_idempotence(self):
        self.create();self.reserve()
        a=self.control("pause","PAUSE_ENTRIES")
        self.assertEqual(a,self.control("pause","PAUSE_ENTRIES"))
        ro=SQLiteEventStore(self.db,read_only=True);self.addCleanup(ro.close)
        data=DashboardReadService(ro).get_overview()
        self.assertEqual(data["capital_accounts"][0]["kind"],"SYNTHETIC_TEST")
        self.assertTrue(data["operational_controls"]["entries_paused"])
        self.assertFalse(data["operational_controls"]["remote_writes_enabled"])
        self.assertFalse(data["operational_controls"]["live_authorized"])
        with self.assertRaises(ValueError):SyntheticCapitalCoordinator(ro).create(account_id="z",initial=D(1),currency="X",radars=("launch",),limits=cap())
    def test_loss_and_drawdown_block_new_entries(self):
        self.create(cap(max_drawdown=D(".01"),max_daily_loss=D(".01")))
        self.reserve()
        self.coord.tick("a",run_id="l",tick=q(1,"BUY"),signal_id="entry")
        self.coord.tick("a",run_id="l",tick=q(2))
        self.coord.tick("a",run_id="l",tick=q(3,price="1"))
        self.coord.tick("a",run_id="l",tick=q(4,price="1"))
        self.assertLess(D(self.coord.snapshot("a")["realized_pnl"]),0)
        # Reserve at current cutoff, not an earlier time.
        with self.assertRaises(ValueError):
            self.coord.reserve("a",event_id="reserve-late",run_id="late",radar="launch",pool="p",token="t",wallet="w",
                strategy="immediate",config=config("50"),risk_limits=risk(),at=T+timedelta(seconds=4))
