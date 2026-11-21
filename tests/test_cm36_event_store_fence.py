"""CM36A: real EventStore transactions, no network."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import replace
import unittest

from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.persistent_supervisor import PersistentSupervisor, SupervisorPolicy, AuthorityLost
from smart_money_radar.services.operational_controls import LocalOperationalControls


class CM36EventStoreFence(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/"managed.sqlite"
        self.store=SQLiteEventStore(self.path)
        self.addCleanup(self.store.close)
        self.now=1000.0
        self.key=b"offline-test-capability"*2
        self.ctl=LocalOperationalControls(self.store,operator_capability=self.key)
        for radar in ("launch","smart_money"):
            self.ctl.apply(capability=self.key,event_id="start-"+radar,action="START",
                actor="test",reason="offline fixture",radar=radar,
                at=datetime.fromtimestamp(self.now,timezone.utc))
        self.supervisor=self.new_owner()
        self.supervisor.acquire()
        self.wallet=self.store.bind_collector(self.supervisor.collector_authority("smart_money"))
        self.launch=self.store.bind_collector(self.supervisor.collector_authority("launch"))

    def new_owner(self):
        return PersistentSupervisor(self.store,policy=SupervisorPolicy(lease_seconds=10,interval_seconds=1),
                                    clock=lambda:self.now)

    def test_unbound_existing_and_reopened_writer_cannot_bypass(self):
        with self.assertRaises(AuthorityLost):
            self.store.save_checkpoint("wallet","old")
        reopened=SQLiteEventStore(self.path)
        self.addCleanup(reopened.close)
        with self.assertRaises(AuthorityLost):
            reopened.mark_processed("wallet","old")
        self.assertIsNone(self.store.get_checkpoint("wallet"))
        self.assertFalse(self.store.has_processed_signature("wallet","old"))

    def test_takeover_rejects_old_handles(self):
        self.wallet.save_checkpoint("wallet","first")
        self.now+=11
        new=self.new_owner()
        new.acquire()
        current=self.store.bind_collector(new.collector_authority("smart_money"))
        current.save_checkpoint("wallet","second")
        with self.assertRaises(AuthorityLost):
            self.wallet.save_checkpoint("wallet","late")
        with self.assertRaises(AuthorityLost):
            self.wallet.mark_processed("wallet","late")
        self.assertEqual(self.store.get_checkpoint("wallet"),"second")
        self.assertFalse(self.store.has_processed_signature("wallet","late"))

    def test_radar_scope_isolated(self):
        with self.assertRaises(AuthorityLost):
            self.launch.save_checkpoint("wallet","wrong")
        self.wallet.save_checkpoint("wallet","valid")
        self.assertEqual(self.store.get_checkpoint("wallet"),"valid")

    def test_expiry_between_write_and_commit_rolls_back(self):
        calls=iter((self.now,self.now+11))
        writer=self.store.bind_collector(replace(self.supervisor.collector_authority("smart_money"),
            clock=lambda:next(calls)))
        with self.assertRaises(AuthorityLost):
            writer.save_checkpoint("wallet","rolled-back")
        self.assertIsNone(self.store.get_checkpoint("wallet"))
        self.assertEqual(self.store.integrity_check(),["ok"])

    def test_emergency_blocks_bound_writes(self):
        self.wallet.save_checkpoint("wallet","before")
        self.ctl.apply(capability=self.key,event_id="halt",action="EMERGENCY_HALT",
            actor="test",reason="offline halt test",at=datetime.fromtimestamp(self.now,timezone.utc))
        with self.assertRaises(AuthorityLost):
            self.wallet.save_checkpoint("wallet","after")
        self.assertEqual(self.store.get_checkpoint("wallet"),"before")

    def test_stopped_lease_does_not_reenable_legacy_writer(self):
        self.supervisor.stop()
        for writer in (self.store,self.wallet):
            with self.assertRaises(AuthorityLost):
                writer.save_checkpoint("wallet","stopped")
