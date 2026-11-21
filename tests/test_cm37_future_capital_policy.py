"""CM37F: transactional synthetic policy, preserving existing reservations."""
from datetime import datetime,timezone
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.synthetic_capital import SyntheticCapitalCoordinator,CapitalLimits
from smart_money_radar.services.operational_controls import LocalOperationalControls
from smart_money_radar.domain.paper_replay import PaperConfig
from smart_money_radar.domain.paper_entry_risk_policy import EntryRiskLimits

class FutureCapitalPolicy(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=SQLiteEventStore(Path(tmp.name)/"eval.sqlite");self.addCleanup(self.store.close)
        self.cap=SyntheticCapitalCoordinator(self.store)
        self.limits=CapitalLimits(*([D(".8")]*8))
        self.config=PaperConfig(D("20"),D("5"),D(".5"))
        self.risk=EntryRiskLimits(D(".5"),D(".1"),D("100"),D("1"))
        self.at=datetime(2026,11,21,tzinfo=timezone.utc)
        self.cap.create(account_id="virtual",initial=D("100"),currency="USDC",radars=("launch","smart_money"),limits=self.limits)
        capability=b"local-eval-only"*3
        ctl=LocalOperationalControls(self.store,operator_capability=capability)
        for aid,action,radar in (("start","START","launch"),("entries","RESUME_ENTRIES",None)):
            ctl.apply(capability=capability,event_id=aid,action=action,actor="fixture",at=self.at,radar=radar,reason="offline")
    def apply(self,config=None):
        return self.cap.update_future_policy("virtual",event_id="policy1",limits=self.limits,
            config=config or self.config,risk_limits=self.risk,at=self.at)
    def reserve(self,config=None):
        return self.cap.reserve("virtual",event_id="reserve1",run_id="run1",radar="launch",
            pool="fixture-pool",token="fixture-token",wallet="fixture-wallet",strategy="immediate",
            config=config or self.config,risk_limits=self.risk,at=self.at)
    def test_policy_is_audited_idempotent_and_preserves_principal(self):
        first=self.apply();second=self.apply()
        self.assertEqual(first,second)
        self.assertEqual(first["equity"],"100")
        self.assertEqual(first["event_count"],1)
        self.assertEqual(first["future_run_config"]["stop_loss"],"0.10")
        with self.assertRaises(ValueError):self.apply(PaperConfig(D("30"),D("5"),D(".5")))
    def test_policy_rejects_changes_while_reserved(self):
        self.reserve()
        before=self.cap.snapshot("virtual")
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.cap.snapshot("virtual"),before)
    def test_new_allocation_must_match_audited_policy(self):
        self.apply()
        with self.assertRaises(ValueError):self.reserve(PaperConfig(D("30"),D("5"),D(".5")))
        self.assertEqual(self.reserve()["capital_reserved"],"20")
    def test_reject_unfunded_virtual_allocation(self):
        with self.assertRaises(ValueError):self.apply(PaperConfig(D("101"),D("5"),D(".5")))
        self.assertEqual(self.cap.snapshot("virtual")["event_count"],0)
