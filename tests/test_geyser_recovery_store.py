from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from smart_money_radar.storage.geyser_recovery_store import SQLiteGeyserRecoveryStore


class GeyserRecoveryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "smr_geyser.sqlite"
        self.store = SQLiteGeyserRecoveryStore(self.database)

    def tearDown(self):
        self.temp.cleanup()

    def create_job(self):
        return self.store.create_backfill_job(
            source_id="helius-mainnet",
            start_slot=100,
            end_slot=200,
            provider="provider-test",
            adapter_version="adapter-v1",
            schema_version="yellowstone-v1",
            query_semantics="account updates inclusive slot range",
            cursor_start="cursor-100",
            cursor_end="cursor-200",
        )

    def test_job_lifecycle_records_proven_complete_coverage(self):
        job = self.create_job()
        self.assertEqual(job["status"], "PENDING")
        self.assertEqual(job["coverage_status"], "UNKNOWN")
        job = self.store.start_backfill_job(job["job_id"])
        self.assertEqual(job["status"], "RUNNING")
        job = self.store.update_backfill_progress(
            job["job_id"], cursor_current="cursor-180",
            requested_count=101, received_count=80, normalized_count=78,
            rejected_count=2, coverage_status="PARTIAL",
            coverage_evidence={"pages_seen": 8},
        )
        self.assertEqual(job["received_count"], 80)
        evidence = {
            "provider_contract": "confirmed",
            "range_covered": True,
            "pagination_exhausted": True,
            "query_semantics": "account updates inclusive slot range",
            "retention_limit_checked": True,
        }
        job = self.store.finish_backfill_job(
            job["job_id"], status="COMPLETED",
            coverage_status="COMPLETE", coverage_evidence=evidence,
        )
        self.assertEqual(job["status"], "COMPLETED")
        self.assertEqual(job["coverage_status"], "COMPLETE")
        self.assertEqual(job["cursor_current"], "cursor-180")
        self.assertEqual(len(self.store.list_backfill_attempts(job["job_id"])), 1)
        self.assertEqual(self.store.list_backfill_attempts(job["job_id"])[0]["status"], "COMPLETED")

    def test_completed_requires_explicit_range_and_pagination_evidence(self):
        job = self.store.start_backfill_job(self.create_job()["job_id"])
        with self.assertRaisesRegex(ValueError, "evidência explícita"):
            self.store.finish_backfill_job(
                job["job_id"], status="COMPLETED", coverage_status="COMPLETE",
                coverage_evidence={"provider_contract": "confirmed"},
            )
        with self.assertRaisesRegex(ValueError, "coverage COMPLETE"):
            self.store.finish_backfill_job(
                job["job_id"], status="COMPLETED", coverage_status="UNKNOWN",
                coverage_evidence={
                    "provider_contract": "confirmed", "range_covered": True,
                    "pagination_exhausted": True, "query_semantics": "test",
                },
            )

    def test_progress_counters_cannot_regress_and_only_running_jobs_change(self):
        job = self.store.start_backfill_job(self.create_job()["job_id"])
        self.store.update_backfill_progress(job["job_id"], received_count=10)
        with self.assertRaisesRegex(ValueError, "não pode regredir"):
            self.store.update_backfill_progress(job["job_id"], received_count=9)
        self.store.finish_backfill_job(
            job["job_id"], status="PARTIAL", coverage_status="PARTIAL",
            coverage_evidence={"reason": "provider window ended"},
        )
        with self.assertRaisesRegex(ValueError, "RUNNING"):
            self.store.update_backfill_progress(job["job_id"], received_count=11)

    def test_interrupted_job_preserves_cursor_and_retries_with_new_attempt_number(self):
        job = self.store.start_backfill_job(self.create_job()["job_id"])
        self.store.update_backfill_progress(
            job["job_id"], cursor_current="cursor-145", received_count=20,
            normalized_count=18,
        )
        recovered = self.store.recover_interrupted_jobs()
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["status"], "PARTIAL")
        self.assertEqual(recovered[0]["coverage_status"], "PARTIAL")
        self.assertEqual(recovered[0]["cursor_current"], "cursor-145")
        attempts = self.store.list_backfill_attempts(job["job_id"])
        self.assertEqual(attempts[0]["status"], "INTERRUPTED")
        restarted = self.store.start_backfill_job(job["job_id"])
        self.assertEqual(restarted["status"], "RUNNING")
        attempts = self.store.list_backfill_attempts(job["job_id"])
        self.assertEqual([item["attempt_number"] for item in attempts], [1, 2])
        self.assertEqual(attempts[1]["cursor_start"], "cursor-145")

    def test_interrupted_empty_job_becomes_failed_with_unknown_coverage(self):
        job = self.store.start_backfill_job(self.create_job()["job_id"])
        recovered = self.store.recover_interrupted_jobs()
        self.assertEqual(recovered[0]["job_id"], job["job_id"])
        self.assertEqual(recovered[0]["status"], "FAILED")
        self.assertEqual(recovered[0]["coverage_status"], "UNKNOWN")
        self.assertEqual(self.store.recover_interrupted_jobs(), [])

    def test_partial_job_can_be_retried_and_finished_without_false_completion(self):
        job = self.store.start_backfill_job(self.create_job()["job_id"])
        self.store.update_backfill_progress(job["job_id"], received_count=5)
        self.store.finish_backfill_job(
            job["job_id"], status="PARTIAL", coverage_status="PARTIAL",
            coverage_evidence={"gap_slots": [[120, 130]]},
        )
        self.store.start_backfill_job(job["job_id"])
        job = self.store.finish_backfill_job(
            job["job_id"], status="FAILED", coverage_status="UNKNOWN",
            coverage_evidence={"reason": "provider unavailable"}, error="timeout",
        )
        self.assertEqual(job["status"], "FAILED")
        self.assertEqual(job["retry_count"], 1)
        self.assertEqual(len(self.store.list_backfill_attempts(job["job_id"])), 2)

    def test_projection_checkpoint_is_source_scoped_and_persistent(self):
        args = dict(
            projection_name="geyser_account_timeline", projection_version=1,
            source_id="source-a", generation=1, last_delivery_id=50,
            last_event_id="event-50", source_delivery_count=50,
            projected_event_count=45, skipped_unsequenced_count=0,
            input_coverage_status="COMPLETE", continuity_interrupted=False,
        )
        checkpoint = self.store.record_projection_checkpoint(**args)
        self.assertEqual(checkpoint["input_coverage_status"], "COMPLETE")
        other = dict(args, source_id="source-b", last_delivery_id=10, last_event_id="event-10")
        self.assertEqual(self.store.record_projection_checkpoint(**other)["source_id"], "source-b")
        reopened = SQLiteGeyserRecoveryStore(self.database)
        self.assertEqual(
            reopened.get_projection_checkpoint("geyser_account_timeline", 1, "source-a")["generation"],
            1,
        )

    def test_projection_cannot_claim_complete_with_gap_or_unsequenced_events(self):
        args = dict(
            projection_name="timeline", projection_version=1, source_id="source",
            generation=1, last_delivery_id=10, last_event_id="event",
            source_delivery_count=10, projected_event_count=8,
            skipped_unsequenced_count=1, input_coverage_status="COMPLETE",
            continuity_interrupted=False,
        )
        with self.assertRaisesRegex(ValueError, "zero evento sem sequência"):
            self.store.record_projection_checkpoint(**args)
        args["skipped_unsequenced_count"] = 0
        args["continuity_interrupted"] = True
        with self.assertRaisesRegex(ValueError, "continuidade não interrompida"):
            self.store.record_projection_checkpoint(**args)

    def test_projection_generation_and_delivery_checkpoint_cannot_regress(self):
        args = dict(
            projection_name="timeline", projection_version=1, source_id="source",
            generation=2, last_delivery_id=20, last_event_id="event-20",
            source_delivery_count=20, projected_event_count=20,
            skipped_unsequenced_count=0, input_coverage_status="PARTIAL",
            continuity_interrupted=False,
        )
        self.store.record_projection_checkpoint(**args)
        with self.assertRaisesRegex(ValueError, "generation deve avançar"):
            self.store.record_projection_checkpoint(**dict(args, generation=2, last_delivery_id=21))
        with self.assertRaisesRegex(ValueError, "last_delivery_id não pode regredir"):
            self.store.record_projection_checkpoint(**dict(args, generation=3, last_delivery_id=19))

    def test_invalid_slot_range_and_job_state_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "end_slot"):
            self.store.create_backfill_job(
                source_id="s", start_slot=20, end_slot=10, provider="p",
                adapter_version="a", schema_version="v", query_semantics="q",
            )
        job = self.create_job()
        with self.assertRaisesRegex(ValueError, "não é possível iniciar"):
            self.store.start_backfill_job(job["job_id"])
        self.store.start_backfill_job(job["job_id"])
        with self.assertRaisesRegex(ValueError, "não é possível iniciar"):
            self.store.start_backfill_job(job["job_id"])


if __name__ == "__main__":
    unittest.main()
