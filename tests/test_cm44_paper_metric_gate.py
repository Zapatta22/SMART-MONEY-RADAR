"""CM44 CM39: receipt integrity gate on existing synthetic capital, no trades."""
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from pathlib import Path

from smart_money_radar.services.cm38j_metric_provenance import describe_metric
from smart_money_radar.services.prospective_paper_plan import plan_prospective_paper
from smart_money_radar.services.synthetic_capital import (
    SyntheticCapitalCoordinator, CapitalLimits,
)
from smart_money_radar.storage.event_store import SQLiteEventStore

class TestCm44PaperEconomicPreflight(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=SQLiteEventStore(Path(tmp.name)/"test.sqlite")
        self.addCleanup(self.store.close)
        self.at=datetime.now(timezone.utc)-timedelta(minutes=1)
        SyntheticCapitalCoordinator(self.store).create(
            account_id="virtual",initial=Decimal("100"),currency="USDC",
            radars=("launch",),limits=CapitalLimits(*([Decimal("1")]*8)))
        self.before=SyntheticCapitalCoordinator(self.store).snapshot("virtual")

    def receipt(self):
        return describe_metric(name="liquidity",value=None,
            start=self.at,end=self.at,available_at=self.at,decision_at=self.at,
            unavailable_reason="liquidity_not_authenticated",radar="launch")

    def plan(self, receipts):
        return plan_prospective_paper(self.store,account_id="virtual",radar="launch",
            as_of=self.at,source_assessment={"radar":"launch",
                "provider_authenticated":True,"independently_finalized":True},
            radar_qualification={"radar":"launch","qualified":True,
                "economic_receipts":receipts})

    def test_incomplete_economics_remains_blocked_without_capital_mutation(self):
        result=self.plan([self.receipt()])
        self.assertEqual(result["status"],"BLOCKED")
        self.assertIn("cm38j_economic_evidence_incomplete",result["reasons"])
        self.assertIn("cm38j_receipts_information_only",result["reasons"])
        self.assertFalse(result["prospective_authorized"])
        self.assertEqual(result["eligible_ticks"],0)
        self.assertEqual(SyntheticCapitalCoordinator(self.store).snapshot("virtual"),self.before)

    def test_tampered_indicator_fails_closed_without_mutation(self):
        item=self.receipt()
        item["quality"]="VERIFIED"
        item["value"]="99999"
        with self.assertRaisesRegex(ValueError,"integrity"):
            self.plan([item])
        self.assertEqual(SyntheticCapitalCoordinator(self.store).snapshot("virtual"),self.before)

    def test_cross_radar_evidence_fails_closed(self):
        receipt=describe_metric(name="realized_pnl",value=None,start=self.at,
            end=self.at,available_at=self.at,decision_at=self.at,
            unavailable_reason="cost_basis_missing")
        with self.assertRaises(ValueError):
            self.plan([receipt])
        self.assertEqual(SyntheticCapitalCoordinator(self.store).snapshot("virtual"),self.before)

    def test_duplicate_economic_evidence_fails_closed(self):
        r=self.receipt()
        with self.assertRaisesRegex(ValueError,"duplicate"):
            self.plan([r,r])
        self.assertEqual(SyntheticCapitalCoordinator(self.store).snapshot("virtual"),self.before)

if __name__=="__main__":
    unittest.main()
