"""CM33: explicit synthetic fixture prices only, no live connection."""
import sqlite3
import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from smart_money_radar.domain.paper_replay import PaperConfig,ReplayTick
from smart_money_radar.domain.paper_entry_risk_policy import EntryRiskLimits
from smart_money_radar.services.synthetic_paper_ledger import SyntheticPaperLedger,read_synthetic_paper,paper_preflight
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.dashboard_read import DashboardReadService
T=datetime(2026,11,21,tzinfo=timezone.utc)
def tick(n,side="NONE",price="10",depth="100",bid_depth=None,halt=False,allowed=True):
    p=D(price)
    t=T+timedelta(seconds=n)
    return ReplayTick(t,p,D("100"),side,allowed,halt,market_at=t,bid=p,ask=p,
        bid_size=D(bid_depth or depth),ask_size=D(depth),quote_id="q"+str(n))
def config(**kw):
    return PaperConfig(**dict(dict(initial_cash=D("1000"),max_entry_cash=D("100"),max_exposure=D(".5"),
        fee_bps=D("10"),slippage_bps=D("10"),stop_loss=D(".1"),take_profit=D(".2"),
        allow_partial_fills=True),**kw))
def limits(**kw):
    return EntryRiskLimits(**dict(dict(max_position_fraction=D(".5"),max_daily_loss_fraction=D(".1"),
        max_slippage_bps=D("100"),min_liquidity_quote=D("1")),**kw))
class CM33Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"smr.sqlite"
        self.store=SQLiteEventStore(self.db)
        self.addCleanup(self.store.close)
        self.ledger=SyntheticPaperLedger(self.store)
    def create(self,rid="l",radar="launch",c=None,lim=None):
        self.ledger.create(run_id=rid,radar=radar,pool="pool",strategy="immediate",config=c or config(),risk_limits=lim or limits())
    def test_buy_sell_partial_fills_fees_and_restart(self):
        self.create()
        self.ledger.append("l",tick=tick(0,"BUY"),signal_id="entry")
        buy=self.ledger.append("l",tick=tick(1,depth="2"))
        self.assertEqual(D(buy["open_quantity"]),D(2))
        self.assertEqual(buy["fills"][0]["side"],"BUY")
        self.ledger.append("l",tick=tick(2,"SELL"),signal_id="exit")
        part=self.ledger.append("l",tick=tick(3,bid_depth="1"))
        self.assertEqual(D(part["open_quantity"]),D(1))
        self.store.close()
        self.store=SQLiteEventStore(self.db)
        self.addCleanup(self.store.close)
        self.ledger=SyntheticPaperLedger(self.store)
        end=self.ledger.append("l",tick=tick(4))
        self.assertEqual(D(end["open_quantity"]),D(0))
        self.assertEqual([f["side"] for f in end["fills"]],["BUY","SELL","SELL"])
        self.assertGreater(D(end["total_fees"]),0)
        self.assertEqual(D(end["cash"])-D("1000"),D(end["realized_pnl"]))
    def test_idempotent_quote_and_duplicate_signal_and_conflicting_quote(self):
        self.create()
        a=self.ledger.append("l",tick=tick(0,"BUY"),signal_id="a")
        self.assertEqual(a,self.ledger.append("l",tick=tick(0,"BUY"),signal_id="a"))
        with self.assertRaises(ValueError): self.ledger.append("l",tick=tick(0,"BUY",price="20"),signal_id="a")
        with self.assertRaises(ValueError): self.ledger.append("l",tick=tick(1,"BUY"),signal_id="a")
    def test_risk_and_insufficient_liquidity_and_slippage(self):
        self.create(lim=limits(min_liquidity_quote=D("5000"),max_slippage_bps=D("5")))
        r=self.ledger.append("l",tick=tick(0,"BUY"),signal_id="a")
        self.assertEqual(r["fills"],[])
        self.assertTrue({"slippage_limit","liquidity_limit"}.issubset(r["risk_evaluations"][0]["reasons"]))
    def test_stop_and_take_profit(self):
        for rid,price,reason in (("s","8","stop_loss"),("t","13","take_profit")):
            self.create(rid)
            self.ledger.append(rid,tick=tick(0,"BUY"),signal_id="a")
            self.ledger.append(rid,tick=tick(1))
            self.ledger.append(rid,tick=tick(2,price=price))
            r=self.ledger.append(rid,tick=tick(3,price=price))
            self.assertEqual(r["fills"][-1]["reason"],reason)
            self.assertEqual(D(r["open_quantity"]),0)
    def test_independent_radars_and_read_only_dashboard_and_no_real_results(self):
        self.create()
        self.create("s","smart_money")
        self.ledger.append("l",tick=tick(0,"BUY"),signal_id="a")
        self.ledger.append("l",tick=tick(1))
        ro=SQLiteEventStore(self.db,read_only=True)
        self.addCleanup(ro.close)
        data=DashboardReadService(ro).get_overview()["synthetic_paper"]
        self.assertGreater(D(data["launch"][0]["report"]["open_quantity"]),0)
        self.assertEqual(D(data["smart_money"][0]["report"]["cash"]),1000)
        self.assertFalse(data["launch"][0]["report"]["operational_authorized"])
        self.assertFalse(data["launch"][0]["report"]["performance_evidence"])
        with self.assertRaises(ValueError):SyntheticPaperLedger(ro).append("l",tick=tick(2))
        for kind in ("HISTORICAL_REPLAY","PROSPECTIVE_SIMULATION","LIVE"):
            got=paper_preflight({"id":"d","radar":"launch","paper_modes":{"immediate":"SIMULATION_CANDIDATE"}},kind=kind)
            self.assertEqual(got["status"],"BLOCKED");self.assertEqual(got["fills"],[])
    def test_corrupted_journal_rejected(self):
        self.create()
        self.ledger.append("l",tick=tick(0))
        with sqlite3.connect(self.db) as con:con.execute("UPDATE cm33_paper_ticks SET payload='{}'")
        with self.assertRaises(ValueError):self.ledger.append("l",tick=tick(1))
        self.assertEqual(read_synthetic_paper(self.store)["launch"][0]["status"],"CONFLICTED")
    def test_halt_cancels_pending_buy_and_zero_depth_blocks(self):
        self.create()
        self.ledger.append("l",tick=tick(0,"BUY"),signal_id="a")
        got=self.ledger.append("l",tick=tick(1,halt=True))
        self.assertEqual(got["fills"],[])
        self.assertIn("emergency_halt",got["risk_evaluations"][-1]["reasons"])
        got=self.ledger.append("l",tick=tick(2,"BUY",depth="0"),signal_id="b")
        self.assertIn("insufficient_market_depth",got["risk_evaluations"][-1]["reasons"])
    def test_rejects_missing_quote_and_non_increasing_time(self):
        self.create()
        with self.assertRaises(ValueError):
            self.ledger.append("l",tick=ReplayTick(T,D(1),D(1)))
        self.ledger.append("l",tick=tick(2))
        with self.assertRaises(ValueError):self.ledger.append("l",tick=tick(1))
