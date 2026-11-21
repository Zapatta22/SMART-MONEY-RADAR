"""CM32 offline intelligence regressions; no network or execution."""
import json
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from smart_money_radar.domain.paper_entry_risk_policy import EntryRiskLimits, EntryRiskSnapshot
from smart_money_radar.services.radar_intelligence import IntelligenceScope, evaluate_archived_event, read_intelligence_reports
from smart_money_radar.services.radar_event_bridge import read_archived_radar_events
from smart_money_radar.services.dashboard_read import DashboardReadService
from smart_money_radar.storage.event_store import SQLiteEventStore

AT=datetime(2026,11,21,0,0,tzinfo=timezone.utc)
def event(radar="smart_money",**kwargs):
    return dict(dict(id=radar+":1",radar=radar,pool="p",source_id="archive",
        origin="ARCHIVED_DERIVED",available_at=AT.isoformat(),evidence_quality="UNKNOWN",
        operational_authorized=False,source_reference="archive:1",raw_sha256="a"*64,
        direction="BUY",program="dex",input_mint="q",output_mint="b",
        token_mints=("b","q"),wallet_address="w1",reasons=("source_not_authenticated",)),**kwargs)
def scope(**kwargs):
    return IntelligenceScope(**dict(dict(token_mint="b",quote_mint="q",min_liquidity_quote=Decimal("100"),
        max_concentration_fraction=Decimal(".5"),wallets=("w1","w2")),**kwargs))
def receipts(wallet):
    return [dict(signature=wallet+str(i),operation_id=wallet+str(i),input_mint="q",output_mint="b",
        side="BUY",confidence="0.95",available_at=(AT-timedelta(seconds=10+i)).isoformat(),
        occurred_at=(AT-timedelta(seconds=20+i)).isoformat()) for i in range(2)]
class CM32Tests(unittest.TestCase):
    def test_consensus_uses_existing_wallet_service_without_promoting_confidence(self):
        store=Mock()
        store.list_wallet_signal_receipts.side_effect=lambda **kw: receipts(kw["wallet"])
        got=evaluate_archived_event(event(),store=store,as_of=AT,scope=scope())
        self.assertEqual(got["consensus"]["direction"],"BUY")
        self.assertEqual(got["consensus"]["eligible_wallets"],2)
        self.assertEqual(got["consensus"]["supporting_signatures"],4)
        self.assertEqual(got["verdict"],"UNKNOWN")
        self.assertEqual(got["confidence"],"UNKNOWN")
        self.assertFalse(got["operational_authorized"])
        self.assertEqual(got["paper_modes"]["immediate"],"BLOCKED")
        self.assertEqual(got["id"],evaluate_archived_event(event(),store=store,as_of=AT,scope=scope())["id"])
    def test_future_event_never_consults_wallet_history(self):
        store=Mock()
        got=evaluate_archived_event(event(),store=store,as_of=AT-timedelta(seconds=1),scope=scope())
        store.list_wallet_signal_receipts.assert_not_called()
        self.assertIn("event_unavailable_at_cutoff",got["reasons"])
    def test_launch_never_uses_wallet_consensus(self):
        store=Mock()
        got=evaluate_archived_event(event("launch"),store=store,as_of=AT,scope=scope(wallets=()))
        store.list_wallet_signal_receipts.assert_not_called()
        self.assertIsNone(got["consensus"])
        self.assertEqual(got["market"]["token_safety"],"UNKNOWN")
        self.assertEqual(got["verdict"],"UNKNOWN")
    def test_invalid_scope_and_wallet_duplicates_fail_closed(self):
        store=Mock()
        with self.assertRaises(ValueError):
            evaluate_archived_event(event("launch"),store=store,as_of=AT,scope=scope())
        with self.assertRaises(ValueError):
            evaluate_archived_event(event(),store=store,as_of=AT,scope=scope(wallets=("w1","w1")))
        with self.assertRaises(ValueError):
            evaluate_archived_event(event(),store=store,as_of=AT,scope=scope(token_mint="other"))
    def test_risk_policy_applies_existing_limits_and_emergency_halt(self):
        got=evaluate_archived_event(event(),store=Mock(),as_of=AT,
            risk_limits=EntryRiskLimits(Decimal(".1"),Decimal(".05"),Decimal("20"),Decimal("100")),
            risk_snapshot=EntryRiskSnapshot(Decimal("1000"),Decimal("200"),Decimal("-60"),
                Decimal("25"),Decimal("500"),True,True))
        self.assertEqual(got["risk_status"],"BLOCKED")
        self.assertTrue({"position_limit","daily_loss_limit","slippage_limit","liquidity_limit",
            "emergency_halt","evidence_unverified"}.issubset(got["risk_reasons"]))
    def test_conflict_and_duplicate_inputs_do_not_emit_positive_signals(self):
        a=event(evidence_quality="CONFLICTED")
        result=read_intelligence_reports(Mock(),{"launch":[event("launch")],"smart_money":[a,a]})
        self.assertEqual(len(result["smart_money"]),1)
        self.assertEqual(result["smart_money"][0]["verdict"],"REJECTED")
        self.assertEqual(result["launch"][0]["verdict"],"UNKNOWN")
    def test_actual_persisted_launch_to_dashboard_decision(self):
        raw=(Path(__file__).resolve().parents[1]/"data/fixtures/mainnet/raydium-cpmm-launch/response.json").read_bytes()
        with TemporaryDirectory() as tmp:
            db=Path(tmp)/"smr.sqlite"
            writer=SQLiteEventStore(db)
            writer.archive_cpmm_launches([raw])
            writer.close()
            store=SQLiteEventStore(db,read_only=True)
            try:
                events=read_archived_radar_events(store)
                ev,=events["launch"]
                a,b=ev["token_mints"]
                payload=DashboardReadService(store,intelligence_scopes={("launch",ev["pool"]):
                    scope(token_mint=a,quote_mint=b,wallets=())}).get_overview()
                report,=payload["radar_opportunities"]["launch"]
                self.assertEqual(report["event_id"],ev["id"])
                self.assertEqual(report["origin"],"ARCHIVED_UNATTESTED")
                self.assertEqual(report["verdict"],"UNKNOWN")
                self.assertEqual(payload["radar_opportunities"]["smart_money"],[])
                economic=report["economic_qualification"]
                self.assertEqual(set(economic),{"immediate","confirmed"})
                for mode, receipt in economic.items():
                    self.assertEqual(receipt["strategy"],mode)
                    self.assertEqual(receipt["status"],"NOT_COMPUTABLE")
                    self.assertEqual(receipt["token_mint"],a)
                    self.assertEqual(receipt["quote_mint"],b)
                    self.assertFalse(receipt["operational_authorized"])
                reopened=evaluate_archived_event(ev,store=store,
                    as_of=datetime.fromisoformat(report["as_of"]),
                    scope=scope(token_mint=a,quote_mint=b,wallets=()))
                self.assertEqual(reopened["economic_qualification"],economic)
            finally:
                store.close()
