"""Independent safety regressions for finalized Solana Launch Radar backfill.

Requires the implementation branch to be merged into a temporary integration
branch before execution. The safety PR intentionally modifies tests only.
"""
import asyncio
import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from smart_money_radar.services.launch_live_backfill import (
    FinalizedLaunchBackfill, LaunchBackfillGap,
)
from smart_money_radar.storage.event_store import SQLiteEventStore


class FixtureRPC:
    def __init__(self, entries, raw, *, page_limit=None):
        self.entries = list(entries)
        self.raw = dict(raw)
        self.page_limit = page_limit
        self.fail_on = set()
        self.calls = []

    async def get_finalized_signatures_for_address_async(
        self, address, *, limit=100, before=None, until=None,
    ):
        self.calls.append(("page", before))
        offset = next(
            (i + 1 for i, entry in enumerate(self.entries)
             if entry["signature"] == before),
            len(self.entries),
        ) if before is not None else 0
        size = min(limit, self.page_limit) if self.page_limit else limit
        return self.entries[offset:offset + size]

    async def get_finalized_transaction_async(self, signature):
        self.calls.append(("transaction", signature))
        if signature in self.fail_on:
            return None
        return self.raw.get(signature)


class LaunchLiveSafetyTests(unittest.TestCase):
    fixture = (Path(__file__).resolve().parents[1] /
               "data/fixtures/mainnet/raydium-cpmm-launch/response.json")

    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "launch.sqlite"
        self.store = SQLiteEventStore(self.db)
        self.addCleanup(self.store.close)
        original = json.loads(self.fixture.read_bytes())["result"]
        self.fixture_tx = original
        self.entries = []
        self.transactions = {}
        for suffix, slot in (("a", 471578450), ("b", 471578451), ("c", 471578452)):
            signature = suffix * 64
            tx = json.loads(json.dumps(original))
            tx["transaction"]["signatures"][0] = signature
            tx["slot"] = slot
            self.entries.append({"signature": signature, "slot": slot, "err": None})
            self.transactions[signature] = tx
        self.entries.reverse()

    def sync(self, rpc, *, source="public-rpc"):
        consumer = FinalizedLaunchBackfill(
            rpc, self.store, source_id=source, page_size=2, max_pages=4,
        )
        return asyncio.run(consumer.synchronize("public-address"))

    def saved(self):
        with sqlite3.connect(self.db) as conn:
            return tuple(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (
                "cpmm_launch_stream_delivery", "cpmm_launch_rpc_cursor", "cpmm_launch_raw",
            ))

    def test_initial_baseline_replay_and_backfill_after_restart(self):
        rpc = FixtureRPC(self.entries, self.transactions)
        first = self.sync(rpc)
        self.assertEqual(first.new_deliveries, 2)
        self.assertEqual(first.coverage, "UNKNOWN")
        again = self.sync(rpc)
        self.assertEqual(again.new_deliveries, 0)
        self.assertEqual(again.latest_signature, first.latest_signature)
        # New finalized signature appears at head of listing.
        entry = {"signature": "d" * 64, "slot": 471578453, "err": None}
        tx = json.loads(json.dumps(self.fixture_tx))
        tx["transaction"]["signatures"][0] = entry["signature"]
        tx["slot"] = entry["slot"]
        rpc.entries.insert(0, entry)
        rpc.raw[entry["signature"]] = tx
        following = self.sync(rpc)
        self.assertEqual(following.new_deliveries, 1)
        self.assertEqual(self.saved(), (3, 1, 3))

    def test_unavailable_transaction_never_moves_signature_or_raw_cursor(self):
        rpc = FixtureRPC(self.entries, self.transactions)
        initial = self.sync(rpc)
        entry = {"signature": "d" * 64, "slot": 471578453, "err": None}
        rpc.entries.insert(0, entry)
        rpc.fail_on.add(entry["signature"])
        with self.assertRaises(LaunchBackfillGap):
            self.sync(rpc)
        self.assertEqual(self.saved(), (2, 1, 2))
        self.assertEqual(self.store.get_cpmm_launch_rpc_cursor("public-rpc:public-address")["signature"],
                         initial.latest_signature)

    def test_page_limit_before_checkpoint_fails_closed(self):
        rpc = FixtureRPC(self.entries, self.transactions)
        self.sync(rpc)
        extra = []
        for index in range(20):
            extra.append({"signature": str(index).zfill(64), "slot": 1000 + index})
        rpc.entries = extra + rpc.entries
        with self.assertRaises(LaunchBackfillGap):
            self.sync(rpc)
        self.assertEqual(self.saved(), (2, 1, 2))

    def test_sqlite_failure_rolls_back_raw_and_finalized_signature(self):
        rpc = FixtureRPC(self.entries, self.transactions)
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                """CREATE TRIGGER refuse_delivery BEFORE INSERT ON cpmm_launch_stream_delivery
                   BEGIN SELECT RAISE(ABORT, 'forced write failure'); END"""
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.sync(rpc)
        self.assertEqual(self.saved(), (0, 0, 0))

    def test_mismatched_transaction_identity_rejected(self):
        rpc = FixtureRPC(self.entries, self.transactions)
        rpc.raw[self.entries[0]["signature"]] = self.fixture_tx
        with self.assertRaises(LaunchBackfillGap):
            self.sync(rpc)
        self.assertEqual(self.saved(), (0, 0, 0))

    def test_stop_before_commit_preserves_state(self):
        rpc = FixtureRPC(self.entries, self.transactions)
        consumer = FinalizedLaunchBackfill(
            rpc, self.store, source_id="public-rpc", page_size=2, max_pages=4,
        )
        stop = asyncio.Event()
        stop.set()
        with self.assertRaises(LaunchBackfillGap):
            asyncio.run(consumer.synchronize("public-address", stop_event=stop))
        self.assertEqual(self.saved(), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
