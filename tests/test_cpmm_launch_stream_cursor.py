"""Durable CPMM launch consumer cursor: fail closed and atomic with RAW."""
import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from smart_money_radar.storage.event_store import SQLiteEventStore


class CPMMLaunchStreamCursorTests(unittest.TestCase):
    fixture = (Path(__file__).resolve().parents[1]
               / "data/fixtures/mainnet/raydium-cpmm-launch/response.json")

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "launches.sqlite"
        self.raw = self.fixture.read_bytes()
        self.store = SQLiteEventStore(self.path)
        self.addCleanup(self.store.close)

    def failed_transaction(self):
        transaction = json.loads(self.raw)
        transaction["result"]["meta"]["err"] = {"InstructionError": [4, "Custom"]}
        return json.dumps(transaction, sort_keys=True).encode()

    def counts(self):
        with sqlite3.connect(self.path) as conn:
            return tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                         for table in ("cpmm_launch_raw", "cpmm_launch_evidence",
                                       "cpmm_launch_stream_delivery", "cpmm_launch_stream_cursor"))

    def test_checkpoint_and_raw_cover_unmatched_frames_across_reopen(self):
        failed = self.failed_transaction()
        first = self.store.archive_cpmm_launches(
            [self.raw, failed], source_id="helius-public-rpc", first_sequence=500,
        )
        self.assertEqual(len(first["initializations"]), 1)
        self.assertEqual(first["stream_cursor"], {
            "source_id": "helius-public-rpc", "first_sequence": 500,
            "last_sequence": 501, "new_deliveries": 2,
            "replayed_deliveries": 0, "prior_coverage": "UNKNOWN",
        })
        self.assertEqual(self.counts(), (2, 1, 2, 1))
        self.store.close()
        self.store = SQLiteEventStore(self.path)
        again = self.store.archive_cpmm_launches(
            [self.raw, failed], source_id="helius-public-rpc", first_sequence=500,
        )
        self.assertEqual(again["initializations"], [])
        self.assertEqual(again["stream_cursor"]["new_deliveries"], 0)
        self.assertEqual(again["stream_cursor"]["replayed_deliveries"], 2)
        extra = self.store.archive_cpmm_launches(
            [failed], source_id="helius-public-rpc", first_sequence=502,
        )
        self.assertEqual(extra["stream_cursor"]["last_sequence"], 502)
        self.assertEqual(self.counts(), (2, 1, 3, 1))

    def test_gap_unknown_history_and_conflicting_replay_rejected_without_write(self):
        self.store.archive_cpmm_launches(
            [self.raw], source_id="stream-a", first_sequence=25,
        )
        before = self.counts()
        for sequence, raw in (
            (27, self.failed_transaction()),
            (24, self.raw),
            (25, self.failed_transaction()),
        ):
            with self.subTest(sequence=sequence):
                with self.assertRaisesRegex(ValueError, "lacuna|conflito"):
                    self.store.archive_cpmm_launches(
                        [raw], source_id="stream-a", first_sequence=sequence,
                    )
                self.assertEqual(self.counts(), before)
        # An independent source has its own cursor, not an inherited baseline.
        self.store.archive_cpmm_launches(
            [self.raw], source_id="stream-b", first_sequence=900,
        )
        self.assertEqual(self.counts(), (1, 1, 2, 2))

    def test_delivery_failure_rolls_back_raw_identity_and_checkpoint(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """CREATE TRIGGER reject_cursor BEFORE INSERT ON cpmm_launch_stream_delivery
                   BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END"""
            )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated disk failure"):
            self.store.archive_cpmm_launches(
                [self.raw], source_id="stream-a", first_sequence=0,
            )
        self.assertEqual(self.counts(), (0, 0, 0, 0))
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TRIGGER reject_cursor")
        self.assertEqual(self.store.archive_cpmm_launches(
            [self.raw], source_id="stream-a", first_sequence=0,
        )["stream_cursor"]["last_sequence"], 0)

    def test_existing_checkpoint_does_not_advance_after_failure(self):
        self.store.archive_cpmm_launches(
            [self.raw], source_id="stream-a", first_sequence=10,
        )
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """CREATE TRIGGER reject_cursor BEFORE INSERT ON cpmm_launch_stream_delivery
                   BEGIN SELECT RAISE(ABORT, 'simulated failure'); END"""
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.archive_cpmm_launches(
                [self.failed_transaction()], source_id="stream-a", first_sequence=11,
            )
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute(
                "SELECT last_sequence FROM cpmm_launch_stream_cursor WHERE source_id = 'stream-a'"
            ).fetchone()[0], 10)
            conn.execute("DROP TRIGGER reject_cursor")
        self.assertEqual(self.store.archive_cpmm_launches(
            [self.failed_transaction()], source_id="stream-a", first_sequence=11,
        )["stream_cursor"]["last_sequence"], 11)

    def test_invalid_sequence_configuration_rejected(self):
        for kwargs in (
            {"source_id": "stream"},
            {"first_sequence": 0},
            {"source_id": "", "first_sequence": 0},
            {"source_id": "stream", "first_sequence": True},
            {"source_id": "stream", "first_sequence": -1},
            {"source_id": "stream", "first_sequence": 2**63},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self.store.archive_cpmm_launches([self.raw], **kwargs)
        self.assertEqual(self.counts(), (0, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
