"""Persistent Smart Money replay pages through the real SQLite producers."""

from datetime import datetime, timedelta, timezone
import json
import unittest

import test_cm38_economic_child_links as fixtures
from smart_money_radar.services.operational_controls import LocalOperationalControls
from smart_money_radar.services.persistent_supervisor import PersistentSupervisor, SupervisorPolicy
from smart_money_radar.services.synthetic_paper_ledger import _encode, _hash
from smart_money_radar.storage.event_store import SQLiteEventStore


class SmartMoneyArchivePaginationTests(unittest.TestCase):
    def setUp(self):
        fixtures.EconomicChildEvidenceLinks.setUp(self)
        self.tx["transaction"]["message"]["accountKeys"] = [self.wallet]
        capability = b"offline-archive-pagination-test-000"
        LocalOperationalControls(self.store, operator_capability=capability).apply(
            capability=capability, event_id="start-smart-money", action="START",
            actor="fixture", at=datetime.now(timezone.utc), radar="smart_money",
            reason="offline Smart Money archive pagination",
        )

    def archive(self, suffix, *, linked=True):
        self.signature = "1" * 63 + suffix
        self.tx["transaction"]["signatures"] = [self.signature]
        evidence_id = (
            fixtures.EconomicChildEvidenceLinks.capture(
                self, radar="smart_money", source="helius-wallet-rpc",
            )
            if linked else None
        )
        operation, bundle = fixtures.EconomicChildEvidenceLinks.add_swap(self)
        with self.store._connection_scope() as conn, conn:
            conn.execute(
                """UPDATE observed_transactions SET chain='solana', observed_at=?
                   WHERE wallet_address=? AND signature=?""",
                (self.at.isoformat(), self.wallet, self.signature),
            )
        self.store.mark_processed(
            self.wallet, self.signature, replay_bundles=(bundle,), evidence_id=evidence_id,
        )
        return f"smart_money:{operation}", evidence_id

    def supervisor(self):
        runner = PersistentSupervisor(
            self.store, clock=lambda: self.now,
            policy=SupervisorPolicy(batch_limit=1, interval_seconds=1),
        )
        runner.acquire()
        return runner

    def decisions(self):
        with self.store._connection_scope() as conn:
            return [event_id for event_id, in conn.execute(
                "SELECT event_id FROM cm36_decision_journal WHERE radar='smart_money' ORDER BY rowid",
            )]

    def test_oldest_first_resume_deduplicate_and_report_legacy_gap(self):
        first, _ = self.archive("2")
        second, _ = self.archive("3", linked=False)
        third, _ = self.archive("4")
        self.now = datetime.now(timezone.utc).timestamp()
        runner = self.supervisor()
        current = runner.step("smart_money")
        self.assertEqual((current["archive_cursor"], current["processed_new"]), (1, 1))
        self.assertEqual(current["archive_coverage"]["status"], "LOCAL_BACKLOG")
        self.assertEqual(self.decisions(), [first])
        runner.stop()
        path = self.store.database_path
        self.store.close()
        self.store = SQLiteEventStore(path)
        self.addCleanup(self.store.close)

        self.now += 2
        runner = self.supervisor()
        current = runner.step("smart_money")
        self.assertEqual((current["archive_cursor"], current["processed_new"]), (2, 1))
        self.assertEqual(self.decisions(), [first, second])
        self.now += 2
        current = runner.step("smart_money")
        self.assertEqual(current["archive_coverage"]["status"], "LOCAL_PAGE_DRAINED")
        self.assertEqual(current["archive_coverage"]["linked_rpc_receipts"], 2)
        self.assertEqual(current["archive_coverage"]["missing_rpc_links"], 1)
        self.assertEqual(current["coverage"], "UNKNOWN")
        self.assertEqual(current["archive_coverage"]["independent_coverage"], "UNKNOWN")
        self.assertEqual(self.decisions(), [first, second, third])

        # A legacy task with decisions but no numeric cursor backfills the
        # archive positions without writing a second copy of the decisions.
        with self.store._connection_scope() as conn, conn:
            payload, = conn.execute(
                "SELECT payload FROM cm36_supervisor_tasks WHERE radar='smart_money'",
            ).fetchone()
            old_task = json.loads(payload)
            for key in ("archive_cursor", "archive_cursor_anchor", "archive_coverage"):
                del old_task[key]
            value = _encode(old_task)
            conn.execute(
                "UPDATE cm36_supervisor_tasks SET payload=?,payload_sha=? WHERE radar='smart_money'",
                (value, _hash(value)),
            )
        self.now += 2
        replay = runner.step("smart_money")
        self.assertEqual((replay["archive_cursor"], replay["processed_new"]), (1, 0))
        self.assertEqual(replay["checkpoint"], third)
        self.assertEqual(self.decisions(), [first, second, third])
        runner.stop()

    def test_future_rpc_link_blocks_older_receipt_and_later_positions(self):
        first, evidence_id = self.archive("2")
        second, _ = self.archive("3")
        self.now = datetime.now(timezone.utc).timestamp()
        with self.store._connection_scope() as conn, conn:
            conn.execute(
                """UPDATE cm38_economic_evidence_links SET linked_at=?
                   WHERE evidence_id=? AND entity_type='replay_opportunity'""",
                (datetime.fromtimestamp(self.now + 5, timezone.utc).isoformat(), evidence_id),
            )
        runner = self.supervisor()
        waiting = runner.step("smart_money")
        self.assertEqual(waiting["archive_cursor"], 0)
        self.assertEqual(waiting["archive_coverage"]["status"], "WAITING_FOR_CUTOFF")
        self.assertEqual(self.decisions(), [])
        self.now += 6
        self.assertEqual(runner.step("smart_money")["archive_cursor"], 1)
        self.assertEqual(self.decisions(), [first])
        self.now += 2
        self.assertEqual(runner.step("smart_money")["archive_cursor"], 2)
        self.assertEqual(self.decisions(), [first, second])
        runner.stop()

    def test_failed_write_preserves_position_and_corrupt_link_records_gap(self):
        first, _ = self.archive("2")
        _, corrupt_id = self.archive("3")
        self.now = datetime.now(timezone.utc).timestamp()
        runner = self.supervisor()
        with self.store._connection_scope() as conn, conn:
            conn.execute(
                """CREATE TRIGGER fail_cm73_insert BEFORE INSERT ON cm36_decision_journal
                   WHEN NEW.radar='smart_money' BEGIN SELECT RAISE(ABORT,'test'); END""",
            )
        failed = runner.step("smart_money")
        self.assertEqual(failed["status"], "BACKOFF")
        self.assertEqual(failed.get("archive_cursor", 0), 0)
        self.assertEqual(self.decisions(), [])
        with self.store._connection_scope() as conn, conn:
            conn.execute("DROP TRIGGER fail_cm73_insert")
            conn.execute("UPDATE cm38_rpc_observations SET raw=? WHERE evidence_id=?",
                         (b"{}", corrupt_id))
        self.now += 2
        self.assertEqual(runner.step("smart_money")["archive_cursor"], 1)
        self.now += 2
        recovered = runner.step("smart_money")
        self.assertEqual(recovered["archive_cursor"], 2)
        self.assertEqual(recovered["archive_coverage"]["conflicted_receipts"], 1)
        self.assertEqual(recovered["coverage"], "UNKNOWN")
        self.assertEqual(self.decisions(), [first])
        runner.stop()

    def test_normalized_body_and_checkpoint_identity_conflicts_fail_closed(self):
        first, _ = self.archive("2")
        _, _ = self.archive("3")
        with self.store._connection_scope() as conn, conn:
            divergent = {**self.tx, "meta": {"err": None, "fee": 9000}}
            conn.execute(
                "UPDATE observed_transactions SET payload_json=? WHERE signature=?",
                (json.dumps(divergent), self.signature),
            )
        self.now = datetime.now(timezone.utc).timestamp()
        runner = self.supervisor()
        self.assertEqual(runner.step("smart_money")["archive_cursor"], 1)
        self.now += 2
        result = runner.step("smart_money")
        self.assertEqual(result["archive_cursor"], 2)
        self.assertEqual(result["archive_coverage"]["conflicted_receipts"], 1)
        self.assertEqual(self.decisions(), [first])

        with self.store._connection_scope() as conn, conn:
            conn.execute("DELETE FROM swap_replay_archive WHERE receipt_id=2")
        original_store = self.store
        self.store = runner.bind_collector_store(original_store, "smart_money")
        try:
            self.archive("4")  # SQLite can reuse a deleted tail receipt ID.
        finally:
            self.store.close()
            self.store = original_store
        self.now += 2
        result = runner.step("smart_money")
        self.assertEqual(result["status"], "BACKOFF")
        self.assertEqual(result["archive_cursor"], 2)
        self.assertEqual(self.decisions(), [first])
        runner.stop()
