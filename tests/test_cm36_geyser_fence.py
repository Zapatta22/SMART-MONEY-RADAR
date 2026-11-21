"""CM36B: managed Geyser RAW writes share the supervisor's SQLite transaction."""
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime,timezone
from dataclasses import replace
import unittest

from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore,RawEventInput,RawDeliveryInput
from smart_money_radar.services.persistent_supervisor import PersistentSupervisor,SupervisorPolicy,AuthorityLost
from smart_money_radar.services.operational_controls import LocalOperationalControls


class CM36GeyserFence(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"shared.sqlite"
        self.events=SQLiteEventStore(self.path)
        self.raw=SQLiteGeyserRawStore(self.path)
        self.addCleanup(self.events.close)
        self.addCleanup(self.raw.close)
        self.now=1000.0
        self.key=b"fence-test-capability"*2
        self.controls=LocalOperationalControls(self.events,operator_capability=self.key)
        for radar in ("launch","smart_money"):
            self.controls.apply(capability=self.key,event_id=radar,action="START",
                actor="test",reason="offline",radar=radar,
                at=datetime.fromtimestamp(self.now,timezone.utc))
        self.sup=self.owner()
        self.sup.acquire()
        self.bound=self.raw.bind_collector(self.sup.collector_authority("launch"))

    def owner(self):
        return PersistentSupervisor(self.events,policy=SupervisorPolicy(lease_seconds=10,interval_seconds=1),
                                    clock=lambda:self.now)

    def event(self):
        return RawEventInput(event_id="event",source_id="source",event_kind="account",
            schema_version="fixture",payload_encoding="protobuf_wire",payload_bytes=b"fixture")

    def delivery(self):
        return RawDeliveryInput(stream_id="fixture",stream_sequence=1,delivery_kind="live",
            received_at="2026-11-21T00:00:00+00:00")

    def test_unbound_rejected_on_managed_database(self):
        with self.assertRaises(AuthorityLost):
            self.raw.ingest(self.event(),self.delivery())
        self.assertIsNone(self.raw.get_raw_event("event"))

    def test_takeover_blocks_old_raw_delivery(self):
        self.now+=11
        new=self.owner()
        new.acquire()
        fresh=self.raw.bind_collector(new.collector_authority("launch"))
        fresh.ingest(self.event(),self.delivery())
        with self.assertRaises(AuthorityLost):
            self.bound.ingest(self.event(),self.delivery())
        self.assertEqual(self.raw.counts()["geyser_raw_deliveries"],1)

    def test_expiry_during_raw_transaction_rolls_back(self):
        times=iter((self.now,self.now+11))
        writer=self.raw.bind_collector(replace(self.sup.collector_authority("launch"),clock=lambda:next(times)))
        with self.assertRaises(AuthorityLost):
            writer.ingest(self.event(),self.delivery())
        self.assertIsNone(self.raw.get_raw_event("event"))
        self.assertEqual(self.raw.counts()["geyser_raw_deliveries"],0)
        self.assertEqual(self.raw.integrity_check(),["ok"])

    def test_late_frame_stream_registration_is_rejected(self):
        self.now+=11
        with self.assertRaises(AuthorityLost):
            self.bound.register_frame_stream("source","stream","domain",0)

    def test_separate_db_cannot_bind_same_generation(self):
        other=SQLiteGeyserRawStore(self.path.with_name("other.sqlite"))
        self.addCleanup(other.close)
        with self.assertRaises(AuthorityLost):
            other.bind_collector(self.sup.collector_authority("launch"))

    def test_pause_only_blocks_target_radar(self):
        wallet=self.raw.bind_collector(self.sup.collector_authority("smart_money"))
        self.controls.apply(capability=self.key,event_id="pause-launch",action="PAUSE",
            actor="test",reason="offline",radar="launch",at=datetime.fromtimestamp(self.now,timezone.utc))
        with self.assertRaises(AuthorityLost):
            self.bound.ingest(self.event(),self.delivery())
        wallet.ingest(self.event(),self.delivery())
        self.assertEqual(self.raw.counts()["geyser_raw_deliveries"],1)

    def test_pause_then_resume_does_not_revive_old_generation_handle(self):
        for event,action in (("pause","PAUSE"),("resume","START")):
            self.controls.apply(capability=self.key,event_id=event,action=action,actor="test",
                reason="offline",radar="launch",at=datetime.fromtimestamp(self.now,timezone.utc))
        with self.assertRaises(AuthorityLost):
            self.bound.ingest(self.event(),self.delivery())
        fresh=self.sup.bind_collector_store(self.raw,"launch")
        fresh.ingest(self.event(),self.delivery())
        self.assertEqual(self.raw.counts()["geyser_raw_deliveries"],1)
