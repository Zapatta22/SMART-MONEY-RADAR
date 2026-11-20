"""Adversarial finalized Solana history tests without network or RPC credentials."""
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


class HistoryRPC:
    def __init__(self, history, transactions):
        self.history = history
        self.transactions = transactions
        self.calls = []

    async def get_finalized_signatures_for_address_async(
        self, address, *, limit=100, before=None,
    ):
        self.calls.append(("page", before))
        if before is None:
            index = 0
        else:
            index = next((i + 1 for i, x in enumerate(self.history)
                          if x["signature"] == before), len(self.history))
        return self.history[index:index + limit]

    async def get_finalized_transaction_async(self, signature):
        self.calls.append(("tx", signature))
        return self.transactions.get(signature)


class HostileFinalizedHistoryTests(unittest.TestCase):
    fixture = (Path(__file__).resolve().parents[1] /
               "data/fixtures/mainnet/raydium-cpmm-launch/response.json")

    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = SQLiteEventStore(Path(temp.name) / "events.sqlite")
        self.addCleanup(self.store.close)
        tx = json.loads(self.fixture.read_bytes())["result"]
        self.history = []
        self.transactions = {}
        for slot, prefix in ((30, "A"), (29, "B"), (28, "C")):
            signature = prefix * 64
            item = json.loads(json.dumps(tx))
            item["slot"] = slot
            item["transaction"]["signatures"][0] = signature
            self.history.append({
                "signature": signature, "slot": slot,
                "confirmationStatus": "finalized", "err": None,
            })
            self.transactions[signature] = item

    def sync(self, rpc):
        return asyncio.run(FinalizedLaunchBackfill(
            rpc, self.store, source_id="finalized-node",
            page_size=2, max_pages=4,
        ).synchronize("public-program"))

    def cursor(self):
        return self.store.get_cpmm_launch_rpc_cursor("finalized-node:public-program")

    def test_finalized_result_reports_exact_committed_signatures_and_timing(self):
        rpc = HistoryRPC(self.history, self.transactions)
        result = self.sync(rpc)
        self.assertEqual(result.finalized_signatures,
                         ("B" * 64, "A" * 64))
        self.assertEqual(result.new_deliveries, 2)
        self.assertGreaterEqual(result.rpc_elapsed_seconds, 0)
        self.assertGreaterEqual(result.persistence_seconds, 0)
        self.assertEqual(result.coverage, "UNKNOWN")
        self.assertEqual(result.latest_signature, "A" * 64)
        self.assertEqual(self.cursor()["signature"], "A" * 64)

    def test_provider_rejects_a_confirmed_only_row(self):
        rpc = HistoryRPC(self.history, self.transactions)
        rpc.history[0] = {**rpc.history[0], "confirmationStatus": "confirmed"}
        with self.assertRaisesRegex(LaunchBackfillGap, "finalização"):
            self.sync(rpc)
        self.assertIsNone(self.cursor())

    def test_provider_rejects_slots_increasing_in_newest_first_list(self):
        rpc = HistoryRPC(self.history, self.transactions)
        rpc.history[1] = {**rpc.history[1], "slot": 31}
        with self.assertRaisesRegex(LaunchBackfillGap, "ordem"):
            self.sync(rpc)
        self.assertIsNone(self.cursor())

    def test_cross_page_duplicate_does_not_advance_cursor(self):
        initial = HistoryRPC(self.history, self.transactions)
        self.sync(initial)
        # Checkpoint A. Page 1 includes newer signatures E,D.
        # Page 2 includes C,D,A; D is duplicated across pages and must block.
        new = []
        for slot, prefix in ((33, "E"), (32, "D")):
            signature = prefix * 64
            tx = json.loads(json.dumps(self.transactions["A" * 64]))
            tx["slot"] = slot
            tx["transaction"]["signatures"][0] = signature
            self.transactions[signature] = tx
            new.append({"signature": signature, "slot": slot,
                        "confirmationStatus": "finalized", "err": None})

        class CrossPageRPC(HistoryRPC):
            async def get_finalized_signatures_for_address_async(
                self, address, *, limit=100, before=None,
            ):
                if before is None:
                    return new
                return [self.history[0], new[-1]][:limit]

        rpc = CrossPageRPC(self.history, self.transactions)
        with self.assertRaisesRegex(LaunchBackfillGap, "repetida"):
            self.sync(rpc)
        self.assertEqual(self.cursor()["signature"], "A" * 64)

    def test_older_checkpoint_not_replaced_by_failed_provider_page(self):
        rpc = HistoryRPC(self.history, self.transactions)
        self.sync(rpc)
        mismatched = HistoryRPC([
            {"signature": "D" * 64, "slot": 35,
             "confirmationStatus": "processed", "err": None},
            *self.history,
        ], self.transactions)
        with self.assertRaises(LaunchBackfillGap):
            self.sync(mismatched)
        self.assertEqual(self.cursor()["signature"], "A" * 64)


if __name__ == "__main__":
    unittest.main()
