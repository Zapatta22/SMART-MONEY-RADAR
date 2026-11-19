"""Read-only SQLite access must never create or migrate the SMR database."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from smart_money_radar.storage.event_store import SQLiteEventStore


class SQLiteEventStoreReadOnlyTests(unittest.TestCase):
    def test_read_only_open_rejects_missing_database_without_creating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.sqlite3"
            with self.assertRaises(FileNotFoundError):
                SQLiteEventStore(path, read_only=True)
            self.assertFalse(path.exists())

    def test_read_only_mode_allows_queries_but_rejects_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            writer = SQLiteEventStore(path)
            writer.save_observation(
                "wallet-readonly", "sig-readonly", {"meta": {"err": None}}, [],
                parse_status="pending", advance_checkpoint=False,
            )
            writer.close()

            reader = SQLiteEventStore(path, read_only=True)
            try:
                self.assertEqual(
                    reader.get_pending_signatures("wallet-readonly"),
                    ["sig-readonly"],
                )
                self.assertEqual(reader.integrity_check(), ["ok"])
                with self.assertRaises(sqlite3.OperationalError):
                    reader.save_observation(
                        "wallet-readonly", "sig-write-blocked",
                        {"meta": {"err": None}}, [], parse_status="pending",
                    )
                self.assertEqual(
                    reader.get_pending_signatures("wallet-readonly"),
                    ["sig-readonly"],
                )
            finally:
                reader.close()

    def test_read_only_mode_rejects_incomplete_schema_without_migrating(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.sqlite3"
            writer = SQLiteEventStore(path)
            writer.close()
            with sqlite3.connect(path) as connection:
                connection.execute("DROP TABLE swap_evidence")

            with self.assertRaisesRegex(sqlite3.DatabaseError, "swap_evidence"):
                SQLiteEventStore(path, read_only=True)

            with sqlite3.connect(path) as connection:
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            self.assertNotIn("swap_evidence", tables)


if __name__ == "__main__":
    unittest.main()
