"""CM38I full SQLite audit from immutable transport to blocked virtual attempt."""
import json
import unittest
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.services.synthetic_capital import SyntheticCapitalCoordinator,CapitalLimits
from smart_money_radar.services.cm38i_decision_audit import record_blocked_virtual_entry,audit_blocked_entry
from smart_money_radar.storage.event_store import SQLiteEventStore

class Cm38iAudit(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/"audit.sqlite"
        self.store=SQLiteEventStore(self.path);self.addCleanup(self.store.close)
        self.at=datetime.now(timezone.utc)-timedelta(minutes=1)
        self.sig="1"*64;self.tx={"slot":42,"transaction":{"signatures":[self.sig],"message":{"instructions":[]}},"meta":{"err":None}}
        self.raw=json.dumps({"jsonrpc":"2.0","result":self.tx}).encode()
        self.eid=self.capture()
        cap=SyntheticCapitalCoordinator(self.store)
        cap.create(account_id="virtual",initial=D("100"),currency="USDC",radars=("launch","smart_money"),limits=CapitalLimits(*([D(".8")]*8)))
        self.before=cap.snapshot("virtual")
        self.req=dict(request_id="request1",account_id="virtual",radar="launch",
                      strategy="immediate",evidence_id=self.eid,
                      decision_at=self.at+timedelta(seconds=4),requested_notional=D("10"))
    def capture(self,radar="launch",source="public-rpc",slot=42,commitment="finalized"):
        tx=dict(self.tx,slot=slot)
        raw=json.dumps({"jsonrpc":"2.0","result":tx}).encode()
        return RpcObservationJournal(self.store).append(radar=radar,signature=self.sig,
            source_id=source,endpoint_host=source+".invalid",raw_payload=raw,
            observed_at=self.at,available_at=self.at,expected_slot=slot,
            commitment_requested=commitment)
    def record(self,**over):
        return record_blocked_virtual_entry(self.store,**dict(self.req,**over))
    def test_blocked_attempt_is_atomic_idempotent_and_survives_reopen(self):
        first=self.record();second=self.record()
        self.assertEqual(first["attempt_id"],second["attempt_id"])
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(second["idempotent_replay"])
        self.assertIn("independent_market_attestation_missing",first["reasons"])
        self.assertEqual(SyntheticCapitalCoordinator(self.store).snapshot("virtual"),self.before)
        reopened=SQLiteEventStore(self.path,read_only=True)
        try:
            self.assertEqual(audit_blocked_entry(reopened,"request1")["attempt_id"],first["attempt_id"])
        finally:reopened.close()
        with self.store._connection_scope() as c:
            self.assertEqual([c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in
                ("cm38i_opportunities","cm38i_risk_decisions","cm38i_virtual_entry_attempts")],[1,1,1])
    def test_duplicate_request_and_second_authorization_denied(self):
        self.record()
        with self.assertRaises(ValueError):self.record(requested_notional=D("11"))
        with self.assertRaises(ValueError):self.record(request_id="request2")
    def test_source_scope_and_future_time_denied(self):
        with self.assertRaises(ValueError):self.record(radar="smart_money")
        with self.assertRaises(ValueError):self.record(decision_at=self.at-timedelta(seconds=1))
        with self.assertRaises(ValueError):self.record(decision_at=datetime.now(timezone.utc)+timedelta(days=1))
    def test_corrupted_raw_denies_without_any_receipt(self):
        with self.store._connection_scope() as c,c:
            c.execute("UPDATE cm38_rpc_observations SET raw=?",(b"tampered",))
        with self.assertRaises(ValueError):self.record()
        with self.store._connection_scope() as c:
            self.assertFalse(c.execute("SELECT 1 FROM sqlite_master WHERE name='cm38i_virtual_entry_attempts'").fetchone())
    def test_expired_and_insufficient_virtual_capital_are_explicit(self):
        self.assertIn("opportunity_expired",self.record(max_age_seconds=1)["reasons"])
    def test_insufficient_capital_and_exposure(self):
        p=self.record(requested_notional=D("200"))
        self.assertIn("insufficient_virtual_capital",p["reasons"])
        self.assertIn("total_exposure_limit",p["reasons"])
    def test_divergent_source_slot_stays_blocked(self):
        self.capture(source="other-rpc",slot=43)
        self.assertIn("divergent_rpc_slot",self.record()["reasons"])
    def test_no_account_or_missing_evidence_cannot_create_orphan(self):
        with self.assertRaises(ValueError):self.record(account_id="nonexistent")
        with self.assertRaises(ValueError):self.record(evidence_id="a"*64)
    def test_replay_after_raw_mutation_not_promoted(self):
        self.record()
        with self.store._connection_scope() as c,c:
            c.execute("UPDATE cm38_rpc_observations SET raw=?",(b"invalid",))
        with self.assertRaises(ValueError):self.record()
        with self.assertRaises(ValueError):audit_blocked_entry(self.store,"request1")
    def test_critical_failure_after_first_insert_rolls_back(self):
        from smart_money_radar.services import cm38i_decision_audit as mod
        original=mod._schema
        def fail(conn):
            original(conn)
            raise RuntimeError("crash during schema")
        with patch.object(mod,"_schema",side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,"crash"):
                self.record()
        with self.store._connection_scope() as c:
            self.assertFalse(c.execute("SELECT 1 FROM sqlite_master WHERE name='cm38i_virtual_entry_attempts'").fetchone())
        self.assertEqual(SyntheticCapitalCoordinator(self.store).snapshot("virtual"),self.before)

    def test_retroactive_risk_change_rejected_by_immutable_trigger(self):
        import sqlite3
        self.record()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store._connection_scope() as c,c:
                c.execute("UPDATE cm38i_risk_decisions SET reasons_json='[]'")
        self.assertEqual(audit_blocked_entry(self.store,"request1")["status"],"BLOCKED")

    def test_integrity_digest_detects_tamper_even_if_trigger_was_disabled(self):
        self.record()
        with self.store._connection_scope() as c,c:
            c.execute("DROP TRIGGER cm38i_immut_cm38i_risk_decisions_update")
            c.execute("UPDATE cm38i_risk_decisions SET reasons_json='[]'")
        with self.assertRaisesRegex(ValueError,"integrity conflict"):
            audit_blocked_entry(self.store,"request1")
        with self.assertRaisesRegex(ValueError,"integrity conflict"):
            self.record()
    def test_cm39_preflight_reuses_persisted_blocked_decision_without_capital_change(self):
        from smart_money_radar.services.prospective_paper_plan import plan_prospective_paper
        receipt=self.record()
        result=plan_prospective_paper(self.store,account_id="virtual",radar="launch",
            as_of=self.at+timedelta(seconds=5),source_assessment={
                "radar":"launch","provider_authenticated":True,
                "independently_finalized":True},
            radar_qualification={"radar":"launch","qualified":True},
            audited_request_id="request1")
        self.assertEqual(result["audited_attempt_id"],receipt["attempt_id"])
        self.assertEqual(result["original_rpc_evidence_id"],self.eid)
        self.assertIn("persisted_opportunity_entry_remains_blocked",result["reasons"])
        self.assertFalse(result["prospective_authorized"])
        self.assertFalse(result["ledger_mutated"])
        self.assertEqual(SyntheticCapitalCoordinator(self.store).snapshot("virtual"),self.before)
        with self.assertRaises(ValueError):
            plan_prospective_paper(self.store,account_id="virtual",radar="smart_money",
                as_of=self.at+timedelta(seconds=5),
                source_assessment={"radar":"smart_money"},
                radar_qualification={"radar":"smart_money"},
                audited_request_id="request1")
    def test_cm39_cannot_reuse_missing_or_tampered_audit(self):
        from smart_money_radar.services.prospective_paper_plan import plan_prospective_paper
        def preflight():
            return plan_prospective_paper(self.store,account_id="virtual",radar="launch",
                as_of=self.at+timedelta(seconds=5),source_assessment={"radar":"launch"},
                radar_qualification={"radar":"launch"},audited_request_id="request1")
        with self.assertRaises(ValueError):preflight()
        self.record()
        with self.store._connection_scope() as c,c:
            c.execute("DROP TRIGGER cm38i_immut_cm38i_risk_decisions_update")
            c.execute("UPDATE cm38i_risk_decisions SET reasons_json='[]'")
        with self.assertRaises(ValueError):preflight()
    def test_strategies_and_radars_are_independent(self):
        e=self.capture(radar="smart_money",source="other")
        p=self.record(request_id="s2",radar="smart_money",strategy="confirmed",evidence_id=e)
        self.assertEqual(p["status"],"BLOCKED")
        self.assertNotEqual(p["opportunity_id"],self.record()["opportunity_id"])
