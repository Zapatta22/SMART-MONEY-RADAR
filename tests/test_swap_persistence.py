import unittest
from datetime import datetime, timezone
from decimal import Decimal

from smart_money_radar.domain.models import (
    SwapClassification, SwapEvidence, SwapObservation, build_swap_operation_id,
)
from smart_money_radar.storage.event_store import SQLiteEventStore


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

    def test_existing_bundle_is_updated_without_creating_duplicate(self):
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
        self.assertFalse(self.store.save_swap_bundle(
            self.observation, revised_classification, revised_evidence
        ))
        bundle = self.store.get_swap_bundle(self.observation.operation_id)
        self.assertEqual(bundle["classification"], revised_classification)
        self.assertEqual(bundle["evidence"], revised_evidence)

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


if __name__ == "__main__":
    unittest.main()
