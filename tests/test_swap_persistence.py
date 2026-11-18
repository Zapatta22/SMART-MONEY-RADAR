import unittest
from datetime import datetime, timezone
from decimal import Decimal

from smart_money_radar.domain.models import (
    SwapClassification, SwapEvidence, SwapObservation, build_swap_operation_id,
)
from smart_money_radar.storage.event_store import (
    SQLiteEventStore,
    SwapReconciliationRecord,
)


class SwapPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.store = SQLiteEventStore(":memory:")
        self.store.save_observation(
            "wallet-a", "sig-a", {"meta": {"err": None}}, [],
            parse_status="no_events", parser_version="1",
        )
        self.observation = SwapObservation(
            operation_id=build_swap_operation_id("solana", "sig-a", 2, (0, 1)),
            chain="solana",
            wallet_address="wallet-a",
            signature="sig-a",
            input_mint="So11111111111111111111111111111111111111112",
            output_mint="mint-token",
            input_amount=Decimal("1.250000000"),
            output_amount=Decimal("250.75"),
            observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
            parser_version="swap-parser-1",
        )
        self.classification = SwapClassification(
            operation_id=self.observation.operation_id,
            side="UNKNOWN",
            confidence=Decimal("0.35"),
            reason="Evidence does not establish the wallet's reference asset.",
        )
        self.evidence = SwapEvidence(
            operation_id=self.observation.operation_id,
            program_id="raydium-program",
            venue="Raydium CPMM",
            instruction_index=2,
            cpi_path=(0, 1),
            evidence=("outer instruction 2", "inner instruction path 0/1"),
        )

    def tearDown(self):
        self.store.close()

    def test_persists_and_reads_all_three_contracts_without_decimal_loss(self):
        self.assertTrue(self.store.save_swap_bundle(
            self.observation, self.classification, self.evidence
        ))
        bundle = self.store.get_swap_bundle(self.observation.operation_id)
        self.assertEqual(bundle["observation"], self.observation)
        self.assertEqual(bundle["classification"], self.classification)
        self.assertEqual(bundle["evidence"], self.evidence)
        self.assertEqual(bundle["observation"].input_amount, Decimal("1.250000000"))

    def test_repeated_operation_is_idempotent_and_updates_bundle(self):
        self.assertTrue(self.store.save_swap_bundle(
            self.observation, self.classification, self.evidence
        ))
        self.assertFalse(self.store.save_swap_bundle(
            self.observation, self.classification, self.evidence
        ))
        self.assertEqual(self.store.get_swap_bundle(self.observation.operation_id)["evidence"], self.evidence)

    def test_existing_bundle_rejects_divergent_replay_without_explicit_replace(self):
        self.assertTrue(self.store.save_swap_bundle(
            self.observation, self.classification, self.evidence
        ))
        revised_classification = SwapClassification(
            operation_id=self.observation.operation_id,
            side="BUY",
            confidence=Decimal("0.90"),
            reason="Reference asset and swap direction are now established.",
        )
        revised_evidence = SwapEvidence(
            operation_id=self.observation.operation_id,
            program_id="raydium-cpmm-program",
            venue="Raydium CPMM",
            instruction_index=2,
            cpi_path=(0, 1),
            evidence=("outer instruction 2", "verified inner CPI path"),
        )
        with self.assertRaisesRegex(ValueError, "Bundle divergente"):
            self.store.save_swap_bundle(
                self.observation, revised_classification, revised_evidence
            )
        bundle = self.store.get_swap_bundle(self.observation.operation_id)
        self.assertEqual(bundle["classification"], self.classification)
        self.assertEqual(bundle["evidence"], self.evidence)

    def test_existing_bundle_can_be_replaced_only_explicitly(self):
        self.assertTrue(self.store.save_swap_bundle(
            self.observation, self.classification, self.evidence
        ))
        revised = SwapClassification(
            operation_id=self.observation.operation_id,
            side="BUY",
            confidence=Decimal("0.90"),
            reason="Explicitly authorized parser reprocessing.",
        )
        self.assertFalse(self.store.save_swap_bundle(
            self.observation, revised, self.evidence, replace_existing=True
        ))
        bundle = self.store.get_swap_bundle(self.observation.operation_id)
        self.assertEqual(bundle["classification"], revised)
        self.assertEqual(bundle["evidence"], self.evidence)

    def test_rejects_contracts_with_different_operation_ids(self):
        wrong = SwapClassification(
            operation_id="swap:other", side="UNKNOWN",
            confidence=Decimal("0"), reason="insufficient evidence",
        )
        with self.assertRaises(ValueError):
            self.store.save_swap_bundle(self.observation, wrong, self.evidence)
        self.assertIsNone(self.store.get_swap_bundle(self.observation.operation_id))

    def test_rejects_non_deterministic_operation_id(self):
        fake = SwapObservation(
            operation_id="swap:invented", chain="solana", wallet_address="wallet-a",
            signature="sig-a", input_mint="mint-a", output_mint="mint-b",
            input_amount=Decimal("1"), output_amount=Decimal("2"),
            observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc), parser_version="1",
        )
        classification = SwapClassification(
            operation_id="swap:invented", side="UNKNOWN", confidence=Decimal("0"),
            reason="not classified",
        )
        evidence = SwapEvidence(
            operation_id="swap:invented", program_id="program", venue=None,
            instruction_index=2, cpi_path=(0, 1),
        )
        with self.assertRaisesRegex(ValueError, "identidade determinística"):
            self.store.save_swap_bundle(fake, classification, evidence)
        self.assertIsNone(self.store.get_swap_bundle("swap:invented"))

    def test_bundle_write_rolls_back_if_evidence_insert_fails(self):
        with self.store._connection_scope() as connection:
            connection.execute(
                """CREATE TRIGGER reject_swap_evidence BEFORE INSERT ON swap_evidence
                   BEGIN SELECT RAISE(ABORT, 'forced evidence failure'); END"""
            )
        with self.assertRaisesRegex(Exception, "forced evidence failure"):
            self.store.save_swap_bundle(
                self.observation, self.classification, self.evidence
            )
        self.assertIsNone(self.store.get_swap_bundle(self.observation.operation_id))

    def test_parent_transaction_delete_cascades_swap_bundle(self):
        self.store.save_swap_bundle(
            self.observation, self.classification, self.evidence
        )
        with self.store._connection_scope() as connection:
            connection.execute(
                "DELETE FROM observed_transactions WHERE wallet_address = ? AND signature = ?",
                ("wallet-a", "sig-a"),
            )
        self.assertIsNone(self.store.get_swap_bundle(self.observation.operation_id))

    def test_rejects_non_solana_chain_in_v1(self):
        operation_id = build_swap_operation_id("ethereum", "sig-a", 2, (0, 1))
        observation = SwapObservation(
            operation_id=operation_id, chain="ethereum", wallet_address="wallet-a",
            signature="sig-a", input_mint="mint-a", output_mint="mint-b",
            input_amount=Decimal("1"), output_amount=Decimal("2"),
            observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc), parser_version="1",
        )
        classification = SwapClassification(
            operation_id=operation_id, side="UNKNOWN", confidence=Decimal("0"),
            reason="outside V1 scope",
        )
        evidence = SwapEvidence(
            operation_id=operation_id, program_id="program", venue=None,
            instruction_index=2, cpi_path=(0, 1),
        )
        with self.assertRaisesRegex(ValueError, "apenas da chain Solana"):
            self.store.save_swap_bundle(observation, classification, evidence)

    def test_requires_parent_observation(self):
        # A different signature exercises the missing-parent guard.
        orphan = SwapObservation(
            operation_id=build_swap_operation_id("solana", "missing-signature", 0), chain="solana", wallet_address="wallet-a",
            signature="missing-signature", input_mint="mint-a", output_mint="mint-b",
            input_amount=Decimal("1"), output_amount=Decimal("2"),
            observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc), parser_version="1",
        )
        orphan_classification = SwapClassification(
            operation_id=build_swap_operation_id("solana", "missing-signature", 0), side="UNKNOWN", confidence=Decimal("0"),
            reason="unverified",
        )
        orphan_evidence = SwapEvidence(
            operation_id=build_swap_operation_id("solana", "missing-signature", 0), program_id="program", venue=None,
            instruction_index=0,
        )
        with self.assertRaises(KeyError):
            self.store.save_swap_bundle(orphan, orphan_classification, orphan_evidence)
        self.assertIsNone(self.store.get_swap_bundle(build_swap_operation_id("solana", "missing-signature", 0)))


    def test_deferred_checkpoint_allows_swap_bundle_pipeline_to_finish_first(self):
        store = SQLiteEventStore(":memory:")
        try:
            store.save_observation(
                "wallet-b", "sig-b", {"meta": {"err": None}}, [],
                parse_status="no_events", parser_version="1",
                advance_checkpoint=False,
            )
            self.assertFalse(store.has_processed_signature("wallet-b", "sig-b"))
            self.assertIsNone(store.get_checkpoint("wallet-b"))

            operation_id = build_swap_operation_id("solana", "sig-b", 3, (1,))
            observation = SwapObservation(
                operation_id=operation_id, chain="solana", wallet_address="wallet-b",
                signature="sig-b", input_mint="mint-in", output_mint="mint-out",
                input_amount=Decimal("1"), output_amount=Decimal("2"),
                observed_at=datetime(2026, 11, 18, tzinfo=timezone.utc), parser_version="1",
            )
            classification = SwapClassification(
                operation_id=operation_id, side="UNKNOWN", confidence=Decimal("0"),
                reason="awaiting reference asset",
            )
            evidence = SwapEvidence(
                operation_id=operation_id, program_id="raydium-program",
                venue="Raydium CPMM", instruction_index=3, cpi_path=(1,),
                evidence=("reconciled",),
            )
            self.assertTrue(store.save_swap_bundle(observation, classification, evidence))
            store.mark_processed("wallet-b", "sig-b")
            self.assertTrue(store.has_processed_signature("wallet-b", "sig-b"))
            self.assertEqual(store.get_checkpoint("wallet-b"), "sig-b")
        finally:
            store.close()

    def test_mark_processed_rejects_missing_parent_observation(self):
        with self.assertRaises(KeyError):
            self.store.mark_processed("wallet-missing", "sig-missing")



    def test_pending_signatures_returns_archived_unprocessed_rows_only(self):
        self.store.save_observation(
            "wallet-a", "pending-1", {"meta": {"err": None}}, [],
            parse_status="no_events", parser_version="1",
            advance_checkpoint=False,
        )
        self.store.save_observation(
            "wallet-a", "pending-2", {"meta": {"err": None}}, [],
            parse_status="no_events", parser_version="1",
            advance_checkpoint=False,
        )
        self.store.save_observation(
            "wallet-a", "processed-1", {"meta": {"err": None}}, [],
            parse_status="no_events", parser_version="1",
            advance_checkpoint=False,
        )
        self.store.mark_processed("wallet-a", "processed-1")
        self.assertEqual(
            self.store.get_pending_signatures("wallet-a"),
            ["pending-1", "pending-2"],
        )
        self.assertEqual(
            self.store.get_pending_signatures("wallet-a", limit=1),
            ["pending-1"],
        )

    def test_pending_signatures_rejects_invalid_limit(self):
        for invalid in (0, -1, True, 1.5):
            with self.subTest(limit=invalid):
                with self.assertRaises(ValueError):
                    self.store.get_pending_signatures("wallet-a", limit=invalid)


    def test_reconciliation_attempts_are_append_only_and_keep_negative_reasons(self):
        record = SwapReconciliationRecord(
            operation_id=self.observation.operation_id,
            instruction_index=2,
            inner_instruction_index=4,
            cpi_path=(0, 1),
            status="INCOMPLETE",
            reason="Net token-account delta does not match gross transfer.",
        )
        first_attempt = self.store.save_swap_reconciliation_attempt(
            "wallet-a", "sig-a", [record]
        )
        second_attempt = self.store.save_swap_reconciliation_attempt(
            "wallet-a", "sig-a", [record]
        )

        history = self.store.get_swap_reconciliation_attempts("wallet-a", "sig-a")
        self.assertEqual(len(history), 2)
        self.assertNotEqual(first_attempt, second_attempt)
        self.assertEqual([item["attempt_id"] for item in history],
                         [first_attempt, second_attempt])
        self.assertEqual(history[0]["status"], "INCOMPLETE")
        self.assertEqual(history[0]["reason"], record.reason)
        self.assertEqual(history[0]["operation_id"], record.operation_id)
        self.assertEqual(history[0]["cpi_path"], (0, 1))
        self.assertEqual(
            self.store.storage_stats()["swap_reconciliation_attempts"], 2
        )

    def test_reconciliation_attempt_requires_parent_observation(self):
        record = SwapReconciliationRecord(
            operation_id=build_swap_operation_id("solana", "sig-missing", 0, (0,)),
            instruction_index=0,
            inner_instruction_index=None,
            cpi_path=(0,),
            status="UNRESOLVED",
            reason="No reconciliation result was returned.",
        )
        with self.assertRaises(KeyError):
            self.store.save_swap_reconciliation_attempt(
                "wallet-a", "sig-missing", [record]
            )

    def test_reconciliation_attempt_rejects_unknown_status(self):
        record = SwapReconciliationRecord(
            operation_id=self.observation.operation_id,
            instruction_index=2,
            inner_instruction_index=None,
            cpi_path=(0, 1),
            status="ACCEPTED",
            reason="Invalid status.",
        )
        with self.assertRaises(ValueError):
            self.store.save_swap_reconciliation_attempt(
                "wallet-a", "sig-a", [record]
            )



    def test_reconciliation_attempt_rejects_non_deterministic_operation_id(self):
        record = SwapReconciliationRecord(
            operation_id="not-the-derived-operation-id",
            instruction_index=2,
            inner_instruction_index=4,
            cpi_path=(0, 1),
            status="INCOMPLETE",
            reason="Evidence is incomplete.",
        )
        with self.assertRaisesRegex(ValueError, "operation_id"):
            self.store.save_swap_reconciliation_attempt(
                "wallet-a", "sig-a", [record]
            )


    def test_reconciliation_diagnostics_aggregate_statuses_reasons_and_pending(self):
        incomplete = SwapReconciliationRecord(
            operation_id=self.observation.operation_id,
            instruction_index=2,
            inner_instruction_index=4,
            cpi_path=(0, 1),
            status="INCOMPLETE",
            reason="Net token-account delta does not match gross transfer.",
        )
        matched = SwapReconciliationRecord(
            operation_id=self.observation.operation_id,
            instruction_index=2,
            inner_instruction_index=4,
            cpi_path=(0, 1),
            status="MATCHED",
            reason="All economic deltas reconciled.",
        )
        self.store.save_swap_reconciliation_attempt(
            "wallet-a", "sig-a", [incomplete]
        )
        self.store.save_swap_reconciliation_attempt(
            "wallet-a", "sig-a", [matched]
        )
        self.store.save_observation(
            "wallet-a", "sig-pending", {"meta": {"err": None}}, [],
            parse_status="pending", parser_version="1",
            advance_checkpoint=False,
        )

        report = self.store.get_reconciliation_diagnostics(
            wallet_address="wallet-a"
        )
        self.assertEqual(report["total_attempts"], 2)
        self.assertEqual(report["distinct_operations"], 1)
        self.assertEqual(report["distinct_signatures"], 1)
        self.assertEqual(report["statuses"]["INCOMPLETE"], 1)
        self.assertEqual(report["statuses"]["MATCHED"], 1)
        self.assertEqual(report["statuses"]["AMBIGUOUS"], 0)
        self.assertEqual(report["statuses"]["UNRESOLVED"], 0)
        self.assertEqual(report["top_reasons"][0]["count"], 1)
        self.assertEqual(report["pending_transactions_count"], 1)
        self.assertEqual(report["pending_transactions"][0]["signature"], "sig-pending")

    def test_query_reconciliation_attempts_filters_and_orders_newest_first(self):
        first = SwapReconciliationRecord(
            operation_id=self.observation.operation_id,
            instruction_index=2,
            inner_instruction_index=4,
            cpi_path=(0, 1),
            status="INCOMPLETE",
            reason="First attempt incomplete.",
        )
        second = SwapReconciliationRecord(
            operation_id=self.observation.operation_id,
            instruction_index=2,
            inner_instruction_index=4,
            cpi_path=(0, 1),
            status="MATCHED",
            reason="Second attempt matched.",
        )
        self.store.save_swap_reconciliation_attempt("wallet-a", "sig-a", [first])
        self.store.save_swap_reconciliation_attempt("wallet-a", "sig-a", [second])

        rows = self.store.query_swap_reconciliation_attempts(
            wallet_address="wallet-a",
            signature="sig-a",
            operation_id=self.observation.operation_id,
            status="INCOMPLETE",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "First attempt incomplete.")
        self.assertEqual(rows[0]["cpi_path"], (0, 1))
        newest = self.store.query_swap_reconciliation_attempts(limit=1)
        self.assertEqual(newest[0]["status"], "MATCHED")

    def test_diagnostics_reject_invalid_limits_and_time_ranges(self):
        with self.assertRaises(ValueError):
            self.store.get_reconciliation_diagnostics(top_reasons_limit=0)
        with self.assertRaises(ValueError):
            self.store.get_reconciliation_diagnostics(
                since="2026-11-19", until="2026-11-18"
            )
        with self.assertRaises(ValueError):
            self.store.query_swap_reconciliation_attempts(status="ACCEPTED")



if __name__ == "__main__":
    unittest.main()
