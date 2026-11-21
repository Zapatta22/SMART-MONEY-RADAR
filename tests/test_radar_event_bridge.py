"""CM30 - archived producer integration and provenance regression tests."""
import hashlib
import json
import unittest
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from smart_money_radar.services.radar_event_bridge import (
    launch_events_from_archive,smart_money_events_from_archive,
    read_archived_radar_events,
)
from smart_money_radar.storage.event_store import SQLiteEventStore

TIME="2026-11-20T23:30:00+00:00"
LAUNCH=Path(__file__).resolve().parents[1]/"data/fixtures/mainnet/raydium-cpmm-launch/response.json"
EXPECTED_POOL="BrRNVcivKs4kRqqbmksT6zXE6o7SAmWHYjrWgFn9JVNC"


def archived_launch():
    from dataclasses import asdict
    from smart_money_radar.data_sources.raydium_cpmm_launch import detect_cpmm_pool_initializations
    raw=LAUNCH.read_bytes()
    launch,=detect_cpmm_pool_initializations(json.loads(raw))
    return dict(pool=launch.pool,identity_json=json.dumps(asdict(launch),sort_keys=True),
                raw_sha256=hashlib.sha256(raw).hexdigest(),raw_bytes=raw,archived_at=TIME)


def receipt(**updates):
    raw=json.dumps({
        "result":{"slot":7,"transaction":{"signatures":["sig-1"]},"meta":{"err":None}}
    },sort_keys=True,separators=(",",":")).encode()
    obj=dict(operation_id="op-1",pool="pool",side="BUY",
             available_at=TIME,signature="sig-1",wallet="wallet",
             raw_bytes=raw,slot=7,observed_at=TIME,
             chain="solana",occurred_at=TIME)
    return dict(obj,**updates)


class RadarEventBridgeTests(unittest.TestCase):
    def test_captured_mainnet_fixture_is_explicitly_offline_not_live(self):
        row=archived_launch()
        event,=launch_events_from_archive([row],origin="FIXTURE_OFFLINE")
        self.assertEqual(event.radar,"launch")
        self.assertEqual(event.origin,"FIXTURE_OFFLINE")
        self.assertEqual(event.pool,EXPECTED_POOL)
        self.assertEqual(event.slot,471578450)
        self.assertEqual(event.raw_sha256,hashlib.sha256(row["raw_bytes"]).hexdigest())
        self.assertEqual(event.coverage,"UNKNOWN")
        self.assertFalse(event.operational_authorized)
        self.assertIn("derived_or_offline_origin",event.reasons)

    def test_archive_launch_is_not_misrepresented_as_live_notification(self):
        event,=launch_events_from_archive([archived_launch()])
        self.assertEqual(event.origin,"ARCHIVED_RPC")
        self.assertIsNone(event.provider)
        self.assertEqual(event.coverage,"UNKNOWN")
        self.assertNotEqual(event.evidence_quality,"VERIFIED")

    def test_original_launch_decoder_rejects_invalid_identity(self):
        row=archived_launch()
        data=json.loads(row["identity_json"])
        data["pool"]="different"
        row["identity_json"]=json.dumps(data)
        event,=launch_events_from_archive([row])
        self.assertEqual(event.evidence_quality,"CONFLICTED")
        self.assertIn("source_identity_conflict",event.reasons)

    def test_sha256_conflict_is_preserved(self):
        row=archived_launch()
        row["raw_bytes"]=row["raw_bytes"]+b" "
        event,=launch_events_from_archive([row])
        self.assertEqual(event.evidence_quality,"CONFLICTED")
        self.assertIn("raw_sha256_conflict",event.reasons)
        self.assertFalse(event.operational_authorized)

    def test_duplicate_launch_records_are_idempotent(self):
        row=archived_launch()
        self.assertEqual(len(launch_events_from_archive([row,row])),1)

    def test_regressive_slot_is_tainted(self):
        a=archived_launch()
        b=dict(a)
        # A different source reference with identical payload is allowed to be
        # displayed, but an archive inconsistency never warrants promotion.
        b["raw_sha256"]="a"*64
        a["identity_json"]=json.dumps({**json.loads(a["identity_json"]),"slot":471578451})
        events=launch_events_from_archive([a,b])
        self.assertTrue(events)
        self.assertTrue(all(x.verdict=="UNKNOWN" for x in events))

    def test_smart_money_swap_direction_is_derived_not_trade_permission(self):
        item,=smart_money_events_from_archive([receipt()])
        self.assertEqual(item.radar,"smart_money")
        self.assertEqual(item.event_type,"SWAP_CLASSIFIED")
        self.assertEqual(item.direction,"BUY")
        self.assertEqual(item.origin,"ARCHIVED_DERIVED")
        self.assertEqual(item.coverage,"UNKNOWN")
        self.assertFalse(item.operational_authorized)
        self.assertIn("derived_or_offline_origin",item.reasons)

    def test_smart_missing_signature_stays_unknown(self):
        item,=smart_money_events_from_archive([receipt(signature=None)])
        self.assertIsNone(item.signature)
        self.assertIn("signature_missing",item.reasons)

    def test_smart_conflicting_source_identity_blocked(self):
        item,=smart_money_events_from_archive([receipt(signature="other")])
        self.assertEqual(item.evidence_quality,"CONFLICTED")
        self.assertIn("source_identity_conflict",item.reasons)

    def test_temporal_conflict_blocked_without_ledger_order_assumptions(self):
        item,=smart_money_events_from_archive([receipt(
            observed_at="2026-11-21T00:00:00+00:00")])
        self.assertEqual(item.evidence_quality,"CONFLICTED")
        self.assertIn("observation_after_publication",item.reasons)

    def test_unknown_order_and_slot_do_not_promote(self):
        item,=smart_money_events_from_archive([receipt(
            slot=None,observed_at=None,side="UNKNOWN")])
        self.assertIsNone(item.slot)
        self.assertIn("slot_missing",item.reasons)
        self.assertIn("observation_time_unknown",item.reasons)
        self.assertEqual(item.verdict,"UNKNOWN")

    def test_two_independent_radar_channels_and_legacy_schema(self):
        with TemporaryDirectory() as d:
            store=SQLiteEventStore(Path(d)/"smr.sqlite")
            try:
                reports=read_archived_radar_events(store)
                self.assertEqual(set(reports),{"launch","smart_money"})
                self.assertEqual(reports["launch"],[])
                self.assertEqual(reports["smart_money"],[])
            finally:
                store.close()

    def test_legacy_and_archived_launch_row_join_read_only(self):
        with TemporaryDirectory() as d:
            store=SQLiteEventStore(Path(d)/"smr.sqlite")
            row=archived_launch()
            try:
                # Simulate the original Launch Radar journal schema by its
                # actual archived tables, without registering a fake live feed.
                with store._connection_scope() as conn:
                    with conn:
                        conn.execute("""CREATE TABLE cpmm_launch_raw
                            (sha256 TEXT PRIMARY KEY,payload BLOB NOT NULL,archived_at TEXT NOT NULL)""")
                        conn.execute("""CREATE TABLE cpmm_launch_evidence
                            (pool TEXT NOT NULL,identity TEXT NOT NULL,sha256 TEXT NOT NULL,
                             PRIMARY KEY(pool,identity,sha256))""")
                        conn.execute("INSERT INTO cpmm_launch_raw VALUES (?,?,?)",
                            (row["raw_sha256"],row["raw_bytes"],row["archived_at"]))
                        conn.execute("INSERT INTO cpmm_launch_evidence VALUES (?,?,?)",
                            (row["pool"],row["identity_json"],row["raw_sha256"]))
                got=read_archived_radar_events(store)
                self.assertEqual(len(got["launch"]),1)
                self.assertEqual(got["launch"][0]["slot"],471578450)
                self.assertEqual(got["launch"][0]["coverage"],"UNKNOWN")
            finally:
                store.close()


if __name__=="__main__":
    unittest.main()
