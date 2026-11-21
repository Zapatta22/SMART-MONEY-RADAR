"""Adversarial tests for the persisted FIFO adapter."""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import sqlite3
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.cm38k_persisted_fifo import persist_fifo_swap

class PersistedFifoTests(unittest.TestCase):
    def setUp(self):
        self.db = SQLiteEventStore(":memory:")
        self.addCleanup(self.db.close)
        self.at = datetime.now(timezone.utc)-timedelta(seconds=1)

    def test_missing_swap(self):
        with self.assertRaisesRegex(ValueError, "swap missing"):
            persist_fifo_swap(self.db, operation_id="missing", as_of=self.at)

    def test_future(self):
        with self.assertRaisesRegex(ValueError, "future"):
            persist_fifo_swap(self.db, operation_id="missing",
                              as_of=self.at+timedelta(days=1))

    def fixture(self):
        # Isolate publication from the derivation tests: FK still requires
        # a real parent, and no generated mock receipt is market evidence.
        with self.db._connection_scope() as c, c:
            c.execute("INSERT INTO observed_transactions(wallet_address,signature,parse_status,parser_version) VALUES ('w','s','parsed','1')")
            c.execute("INSERT INTO swap_observations VALUES ('op','solana','w','s','q','t','1','2',?,'1')",
                      (self.at.isoformat(),))
        return {"sha256":"a"*64,"status":"NOT_COMPUTABLE"}

    def test_idempotency_and_divergence(self):
        receipt=self.fixture()
        with patch("smart_money_radar.services.cm38k_persisted_fifo._derive", return_value=receipt):
            self.assertEqual(persist_fifo_swap(self.db, operation_id="op", as_of=self.at),receipt)
            self.assertEqual(persist_fifo_swap(self.db, operation_id="op", as_of=self.at),receipt)
        with patch("smart_money_radar.services.cm38k_persisted_fifo._derive", return_value={"sha256":"b"*64}):
            with self.assertRaisesRegex(ValueError,"divergent"):
                persist_fifo_swap(self.db, operation_id="op", as_of=self.at)
        with self.db._connection_scope() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM cm38k_persisted_fifo").fetchone()[0],1)

    def test_rollback_missing_parent(self):
        with patch("smart_money_radar.services.cm38k_persisted_fifo._derive", return_value={"sha256":"a"*64}):
            with self.assertRaises(sqlite3.IntegrityError):
                persist_fifo_swap(self.db, operation_id="missing", as_of=self.at)
        with self.db._connection_scope() as c:
            self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='cm38k_persisted_fifo'").fetchone())
