"""CM36D4: alternate projection/checkpoint writer cannot bypass fencing."""
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime,timezone
from dataclasses import replace
import unittest
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.storage.geyser_account_write_projection import SQLiteGeyserAccountWriteProjection
from smart_money_radar.storage.geyser_unsequenced_delivery_audit import SQLiteGeyserUnsequencedDeliveryAudit
from smart_money_radar.storage.geyser_recovery_store import SQLiteGeyserRecoveryStore
from smart_money_radar.services.operational_controls import LocalOperationalControls
from smart_money_radar.services.persistent_supervisor import PersistentSupervisor,SupervisorPolicy,AuthorityLost


class AlternateWriters(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"managed.db"
        self.events=SQLiteEventStore(self.path);self.addCleanup(self.events.close)
        self.raw=SQLiteGeyserRawStore(self.path);self.addCleanup(self.raw.close)
        self.projection=SQLiteGeyserAccountWriteProjection(self.path)
        self.audit=SQLiteGeyserUnsequencedDeliveryAudit(self.path)
        self.now=1000.
        cap=b"fixture"*8
        LocalOperationalControls(self.events,operator_capability=cap).apply(
            capability=cap,event_id="start",action="START",actor="test",reason="fixture",
            radar="launch",at=datetime.fromtimestamp(self.now,timezone.utc))
        self.sup=PersistentSupervisor(self.events,policy=SupervisorPolicy(lease_seconds=10,interval_seconds=1),
            clock=lambda:self.now)
        self.sup.acquire()
        self.authority=self.sup.collector_authority("launch")

    def test_unbound_projection_and_audit_rejected(self):
        for store in (self.projection,self.audit):
            with self.assertRaises(AuthorityLost): store.rebuild()
            self.assertIsNone(store.get_checkpoint())

    def test_bound_projection_expiry_rolls_back(self):
        ticks=iter((self.now,self.now+11))
        store=self.projection.bind_collector(replace(self.authority,clock=lambda:next(ticks)))
        with self.assertRaises(AuthorityLost): store.rebuild()
        self.assertIsNone(self.projection.get_checkpoint())
        self.assertEqual(self.events.integrity_check(),["ok"])

    def test_valid_authority_then_expired_cannot_rebuild(self):
        store=self.audit.bind_collector(self.authority)
        first=store.rebuild()
        self.assertEqual(first["generation"],1)
        self.now+=11
        with self.assertRaises(AuthorityLost): store.rebuild()
        self.assertEqual(self.audit.get_checkpoint()["generation"],1)
