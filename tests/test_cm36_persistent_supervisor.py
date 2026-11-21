"""CM36 fencing and offline supervisor adversarial tests."""
import sqlite3
import unittest
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier,Event
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.persistent_supervisor import PersistentSupervisor,SupervisorPolicy,AuthorityLost,read_supervisor_status
from smart_money_radar.services.operational_controls import LocalOperationalControls
from smart_money_radar.services.dashboard_read import DashboardReadService

T=datetime(2026,11,21,tzinfo=timezone.utc)
KEY=b"t"*32
class CM36Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"smr.sqlite"
        self.store=SQLiteEventStore(self.db);self.addCleanup(self.store.close)
        self.now=T.timestamp()
        self.policy=SupervisorPolicy(lease_seconds=10,interval_seconds=1,max_backoff_seconds=4,max_failures=3)
        self.controls=LocalOperationalControls(self.store,operator_capability=KEY)
        for r in ("launch","smart_money"):
            self.control("start-"+r,"START",r)
    def control(self,eid,action,radar=None):
        return self.controls.apply(capability=KEY,event_id=eid,action=action,radar=radar,
            actor="fixture",reason="fixture",at=datetime.fromtimestamp(self.now,timezone.utc))
    def runner(self,store=None):
        return PersistentSupervisor(store or self.store,policy=self.policy,clock=lambda:self.now)
    def test_duplicate_process_and_expired_owner_fence(self):
        a=self.runner();b=self.runner()
        self.assertEqual(a.acquire(),1)
        with self.assertRaises(AuthorityLost):b.acquire()
        self.now+=10
        self.assertEqual(read_supervisor_status(self.store,now=self.now)["status"],"EXPIRED")
        self.assertEqual(b.acquire(),2)
        with self.assertRaises(AuthorityLost):a.heartbeat()
        with self.assertRaises(AuthorityLost):a.step("launch")
        with self.assertRaises(AuthorityLost):a.stop()
        self.assertEqual(b.cycle()["tasks"]["launch"]["status"],"READY")
        self.assertTrue(any(x["kind"]=="WATCHDOG_EXPIRED" for x in read_supervisor_status(self.store,now=self.now)["alerts"]))
    def test_concurrent_ownership(self):
        barrier=Barrier(2)
        def worker():
            s=SQLiteEventStore(self.db)
            try:
                r=self.runner(s);barrier.wait(timeout=5)
                try:return r.acquire()
                except AuthorityLost:return None
            finally:s.close()
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(worker);b=pool.submit(worker)
            self.assertCountEqual([a.result(timeout=20),b.result(timeout=20)],[None,1])
    def test_generation_lost_during_preparation_cannot_commit(self):
        a=self.runner();a.acquire();b=self.runner()
        original=a._prepare
        def interrupted(radar,now):
            result=original(radar,now)
            self.now+=10;b.acquire()
            return result
        with patch.object(a,"_prepare",side_effect=interrupted):
            with self.assertRaises(AuthorityLost):a.step("smart_money")
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM cm35_wallet_profiles").fetchone()[0],0)
            self.assertEqual(c.execute("SELECT count(*) FROM cm36_supervisor_tasks").fetchone()[0],0)
    def test_emergency_during_preparation_blocks_commit(self):
        a=self.runner();a.acquire()
        original=a._prepare
        def halt(radar,now):
            result=original(radar,now);self.control("halt","EMERGENCY_HALT");return result
        with patch.object(a,"_prepare",side_effect=halt):
            self.assertEqual(a.step("smart_money")["status"],"PAUSED")
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute("SELECT count(*) FROM cm35_wallet_profiles").fetchone()[0],0)
        a.stop();b=self.runner();b.acquire()
        self.assertEqual(b.step("launch")["status"],"PAUSED")
    def test_fault_isolated_and_backoff_bounded(self):
        a=self.runner();a.acquire();original=a._prepare
        def faulty(r,now):
            if r=="launch":raise ConnectionError("fixture")
            return original(r,now)
        with patch.object(a,"_prepare",side_effect=faulty):
            for _ in range(3):
                report=a.cycle();self.now+=4
            self.assertEqual(report["tasks"]["launch"]["status"],"FAULTED")
            self.assertEqual(report["tasks"]["smart_money"]["status"],"READY")
            self.assertEqual(a.step("launch")["failures"],3)
    def test_transaction_failure_rolls_back_profile_and_checkpoint(self):
        a=self.runner();a.acquire()
        with sqlite3.connect(self.db) as c:
            c.execute("CREATE TRIGGER fail_profile BEFORE INSERT ON cm35_wallet_profiles BEGIN SELECT RAISE(ABORT,'fixture'); END")
        bad=a.step("smart_money");self.assertEqual(bad["status"],"BACKOFF")
        self.assertIsNone(bad["checkpoint"])
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM cm35_wallet_profiles").fetchone()[0],0)
            c.execute("DROP TRIGGER fail_profile")
        self.now+=2
        good=a.step("smart_money");self.assertEqual(good["status"],"READY")
        self.assertEqual(good["failures"],0)
    def test_restart_due_time_and_read_only_panel(self):
        a=self.runner();a.acquire();a.cycle();a.stop()
        b=self.runner();self.assertEqual(b.acquire(),2)
        self.assertEqual(b.step("smart_money")["cycles"],1)
        self.now+=1
        self.assertEqual(b.step("smart_money")["cycles"],2)
        reader=SQLiteEventStore(self.db,read_only=True);self.addCleanup(reader.close)
        data=DashboardReadService(reader).get_overview()
        self.assertEqual(data["supervisor"]["generation"],2)
        self.assertFalse(data["supervisor"]["execution_enabled"])
        self.assertFalse(data["supervisor"]["autonomy_24h_verified"])
        self.assertEqual(data["radar_events"]["launch"],[])
        self.assertEqual(set(data["radars"]), {"launch", "smart_money"})
        self.assertEqual(data["radars"]["launch"]["offline_supervisor"]["cycles"], 1)
        self.assertEqual(data["radars"]["smart_money"]["offline_supervisor"]["cycles"], 2)
        for radar in data["radars"].values():
            self.assertEqual(radar["status"], "UNKNOWN")
            self.assertEqual(radar["evidence_coverage"], "UNKNOWN")
            self.assertFalse(radar["operational_authorized"])
    def test_dashboard_fails_closed_after_supervisor_lease_corruption(self):
        supervisor = self.runner()
        supervisor.acquire()
        supervisor.cycle()
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "UPDATE cm36_supervisor_lease SET generation = generation + 1"
            )
        reader = SQLiteEventStore(self.db, read_only=True)
        self.addCleanup(reader.close)
        data = DashboardReadService(reader).get_overview()
        self.assertEqual(data["supervisor"]["status"], "CONFLICTED")
        self.assertEqual(set(data["radars"]), {"launch", "smart_money"})
        for radar in data["radars"].values():
            self.assertEqual(radar["status"], "UNKNOWN")
            self.assertEqual(radar["offline_supervisor"]["task_status"], "UNKNOWN")
            self.assertEqual(radar["offline_supervisor"]["cycles"], 0)
            self.assertFalse(radar["operational_authorized"])

    def test_dashboard_malformed_supervisor_tasks_fail_closed(self):
        reader = SQLiteEventStore(self.db, read_only=True)
        self.addCleanup(reader.close)
        for tasks in (None, [], {"launch": None},
                      {"launch": {"status": "READY", "cycles": True}},
                      {"launch": {"status": "READY", "cycles": -1}}):
            with self.subTest(tasks=tasks), patch(
                "smart_money_radar.services.dashboard_read.read_supervisor_status",
                return_value={"status": "ACTIVE", "radars": tasks,
                              "live_authorized": False, "execution_enabled": False},
            ):
                data = DashboardReadService(reader).get_overview()
                for radar in data["radars"].values():
                    self.assertEqual(radar["offline_supervisor"]["cycles"], 0)
                    self.assertEqual(radar["offline_supervisor"]["task_status"], "UNKNOWN")
                    self.assertFalse(radar["operational_authorized"])
                    self.assertEqual(radar["evidence_coverage"], "UNKNOWN")

    def test_cm76_watchdog_history_recovery_and_radar_isolation(self):
        a = self.runner()
        a.acquire()
        a.cycle()
        self.now += 10
        b = self.runner()
        self.assertEqual(b.acquire(), 2)
        b.cycle()
        reader = SQLiteEventStore(self.db, read_only=True)
        self.addCleanup(reader.close)
        data = DashboardReadService(reader).get_overview()
        history = data["supervisor_history"]
        self.assertEqual(history["integrity"], "VERIFIED_LOCAL")
        self.assertEqual(history["restart_events"], 1)
        self.assertTrue(any(item["kind"] == "WATCHDOG_EXPIRED"
                            for item in history["watchdog_history"]))
        self.assertEqual(set(data["radars"]), {"launch", "smart_money"})
        self.assertFalse(history["execution_enabled"])
        self.assertFalse(history["live_authorized"])

    def test_cm76_corrupt_alert_digest_fences_history(self):
        a = self.runner()
        a.acquire()
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE cm36_supervisor_alerts SET payload_sha='invalid'")
        reader = SQLiteEventStore(self.db, read_only=True)
        self.addCleanup(reader.close)
        data = DashboardReadService(reader).get_overview()
        self.assertEqual(data["supervisor_history"]["integrity"], "CONFLICTED")
        self.assertEqual(data["supervisor_history"]["watchdog_history"], [])
        self.assertEqual(data["supervisor_history"]["availability"], "UNAVAILABLE")
        for radar in data["radars"].values():
            self.assertEqual(radar["status"], "UNKNOWN")
            self.assertFalse(radar["operational_authorized"])

    def test_cm76_invalid_heartbeat_temporal_order_fails_closed(self):
        history = DashboardReadService._supervisor_history({
            "status": "ACTIVE", "last_heartbeat": "2026-11-21T10:00:00+00:00",
            "expires_at": "2026-11-21T09:00:00+00:00",
            "alerts": [{"kind": "STARTED", "at": "2026-11-21T09:00:00+00:00"}],
        })
        self.assertEqual(history["integrity"], "CONFLICTED")
        self.assertEqual(history["watchdog_history"], [])
        self.assertEqual(history["availability"], "UNAVAILABLE")

    def test_cm77_recovery_after_expiry_and_clean_restart_are_distinct(self):
        a = self.runner()
        a.acquire()
        self.now += 10
        b = self.runner()
        b.acquire()
        b.stop()
        self.now += 1
        c = self.runner()
        c.acquire()
        reader = SQLiteEventStore(self.db, read_only=True)
        self.addCleanup(reader.close)
        history = DashboardReadService(reader).get_overview()["supervisor_history"]
        self.assertEqual(history["integrity"], "VERIFIED_LOCAL")
        self.assertEqual(history["recovery_count"], 1)
        self.assertIn(history["watchdog_state"], ("RUNNING_LOCAL", "HEARTBEAT_LOST"))
        kinds = [event["kind"] for event in history["recovery_history"]]
        self.assertEqual(kinds, ["INITIAL_START", "AUTOMATIC_AFTER_EXPIRY",
                                 "RESTART_AFTER_STOP"])

    def test_cm77_duplicate_owner_cannot_create_false_recovery(self):
        a = self.runner()
        a.acquire()
        with self.assertRaises(AuthorityLost):
            self.runner().acquire()
        reader = SQLiteEventStore(self.db, read_only=True)
        self.addCleanup(reader.close)
        history = DashboardReadService(reader).get_overview()["supervisor_history"]
        self.assertEqual(history["recovery_count"], 0)
        self.assertEqual(len(history["recovery_history"]), 1)

    def test_cm77_expired_heartbeat_is_not_live_readiness(self):
        a = self.runner()
        a.acquire()
        self.now += 10
        reader = SQLiteEventStore(self.db, read_only=True)
        self.addCleanup(reader.close)
        history = DashboardReadService(reader).get_overview()["supervisor_history"]
        self.assertIn(history["watchdog_state"], ("HEARTBEAT_LOST", "UNAVAILABLE"))
        self.assertFalse(history["live_authorized"])
        self.assertFalse(history["execution_enabled"])

    def test_corrupt_lease_fails_closed(self):
        a=self.runner();a.acquire()
        with sqlite3.connect(self.db) as c:c.execute("UPDATE cm36_supervisor_lease SET generation=99")
        with self.assertRaises(AuthorityLost):a.heartbeat()
        self.assertEqual(read_supervisor_status(self.store,now=self.now)["status"],"CONFLICTED")
    def test_bounded_execution_and_clean_shutdown(self):
        a=self.runner()
        stop=Event()
        with patch.object(stop,"wait",side_effect=lambda _:setattr(self,"now",self.now+1)):
            self.assertEqual(a.run(stop,max_cycles=20),20)
        status=read_supervisor_status(self.store,now=self.now)
        self.assertEqual(status["status"],"STOPPED")
        self.assertEqual(status["radars"]["launch"]["cycles"],20)
        self.assertEqual(status["radars"]["smart_money"]["cycles"],20)

    def test_cm69_launch_history_dependency_isolated_across_restart(self):
        from smart_money_radar.storage.cpmm_prospective_history import SQLiteCpmmProspectiveHistory
        from smart_money_radar.services.radar_intelligence import read_intelligence_reports
        history=SQLiteCpmmProspectiveHistory(Path(self.tmp.name)/"launch.sqlite")
        self.addCleanup(history.close)
        for generation in (1,2):
            a=PersistentSupervisor(self.store,policy=self.policy,clock=lambda:self.now,
                                   launch_history=history)
            self.assertEqual(a.acquire(),generation)
            with patch("smart_money_radar.services.persistent_supervisor.read_intelligence_reports",
                       wraps=read_intelligence_reports) as read:
                report=a.cycle()
                self.assertEqual(report["tasks"]["launch"]["status"],"READY")
                self.assertEqual(report["tasks"]["smart_money"]["status"],"READY")
                calls={next(iter(c.args[1])):c.kwargs["cpmm_history"] for c in read.call_args_list}
                self.assertIs(calls["launch"],history)
                self.assertIsNone(calls["smart_money"])
            a.stop()
            self.now+=2
