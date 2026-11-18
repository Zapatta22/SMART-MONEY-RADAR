import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from smart_money_radar.domain.models import ActivityEvent
from smart_money_radar.domain.normalization import normalize_transaction
from smart_money_radar.storage.event_store import SQLiteEventStore


class SQLiteEventStoreTests(unittest.TestCase):
    def test_persists_events_and_ignores_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            event = ActivityEvent(
                wallet_address="public-wallet",
                signature="simulated-signature",
                occurred_at=datetime(2026, 11, 7, tzinfo=timezone.utc),
                token_mint="mint-a",
                direction="in",
                amount=Decimal("1.25"),
            )

            self.assertEqual(store.save_events([event]), 1)
            self.assertEqual(store.save_events([event]), 0)
            self.assertEqual(store.get_events(wallet_address="public-wallet"), [event])

    def test_memory_database_persists_across_store_operations(self) -> None:
        store = SQLiteEventStore(":memory:")
        event = ActivityEvent(
            wallet_address="public-wallet",
            signature="memory-signature",
            occurred_at=datetime(2026, 11, 7, tzinfo=timezone.utc),
            token_mint="mint-memory",
            direction="in",
            amount=Decimal("2.5"),
        )

        self.assertEqual(store.save_events([event]), 1)
        self.assertEqual(store.get_events(), [event])
        store.close()


    def test_checkpoint_also_records_processed_signature(self) -> None:
        store = SQLiteEventStore(":memory:")
        self.assertFalse(store.has_processed_signature("wallet-a", "signature-a"))
        store.save_checkpoint("wallet-a", "signature-a")
        self.assertTrue(store.has_processed_signature("wallet-a", "signature-a"))
        self.assertEqual(store.get_checkpoint("wallet-a"), "signature-a")
        store.close()

    def test_allows_unknown_time_from_rpc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            event = ActivityEvent(
                wallet_address="public-wallet",
                signature="simulated-signature",
                occurred_at=None,
                token_mint="mint-a",
                direction="out",
                amount=Decimal("0.5"),
            )

            store.save_events([event])

            self.assertEqual(store.get_events()[0], event)

    def test_close_is_idempotent_for_in_memory_store(self) -> None:
        store = SQLiteEventStore(":memory:")
        store.close()
        store.close()
        self.assertIsNone(store._memory_connection)

    def test_save_observation_atomically_archives_raw_payload_and_checkpoint(self) -> None:
        store = SQLiteEventStore(":memory:")
        payload = {"meta": {"err": None}, "transaction": {"message": {}}}

        store.save_observation(
            "wallet-a", "signature-a", payload, [], parse_status="no_events", parser_version="1"
        )

        self.assertEqual(store.get_raw_transaction("wallet-a", "signature-a"), payload)
        self.assertTrue(store.has_processed_signature("wallet-a", "signature-a"))
        self.assertEqual(store.get_checkpoint("wallet-a"), "signature-a")
        self.assertEqual(
            store.get_observation_metadata("wallet-a", "signature-a")["parse_status"],
            "no_events",
        )
        store.close()

    def test_save_observation_rejects_different_raw_payload_for_same_signature(self) -> None:
        store = SQLiteEventStore(":memory:")
        original = {"meta": {"err": None}, "transaction": {"signatures": ["sig-a"]}}
        conflicting = {"meta": {"err": None}, "transaction": {"signatures": ["sig-b"]}}
        store.save_observation(
            "wallet-a", "sig-a", original, [],
            parse_status="no_events", parser_version="1",
            advance_checkpoint=False,
        )

        with self.assertRaisesRegex(ValueError, "Payload RAW divergente"):
            store.save_observation(
                "wallet-a", "sig-a", conflicting, [],
                parse_status="no_events", parser_version="1",
                advance_checkpoint=False,
            )

        self.assertEqual(store.get_raw_transaction("wallet-a", "sig-a"), original)
        self.assertFalse(store.has_processed_signature("wallet-a", "sig-a"))
        self.assertIsNone(store.get_checkpoint("wallet-a"))
        store.close()

    def test_save_observation_allows_filling_missing_raw_payload(self) -> None:
        store = SQLiteEventStore(":memory:")
        store.save_observation(
            "wallet-a", "sig-a", None, [],
            parse_status="failed_on_chain", parser_version="1",
            advance_checkpoint=False,
        )
        payload = {"meta": {"err": None}, "transaction": {"signatures": ["sig-a"]}}
        store.save_observation(
            "wallet-a", "sig-a", payload, [],
            parse_status="no_events", parser_version="1",
            advance_checkpoint=False,
        )
        self.assertEqual(store.get_raw_transaction("wallet-a", "sig-a"), payload)
        store.close()

    def test_save_observation_rejects_events_from_another_signature(self) -> None:
        store = SQLiteEventStore(":memory:")
        event = ActivityEvent(
            wallet_address="wallet-a", signature="other-signature", occurred_at=None,
            token_mint="mint-a", direction="in", amount=Decimal("1"),
        )
        with self.assertRaises(ValueError):
            store.save_observation(
                "wallet-a", "signature-a", {"meta": {}}, [event],
                parse_status="parsed", parser_version="1",
            )
        self.assertIsNone(store.get_checkpoint("wallet-a"))
        store.close()

    def test_reprocess_observation_replaces_derived_events_without_moving_checkpoint(self) -> None:
        store = SQLiteEventStore(":memory:")
        payload = {"meta": {"err": None}}
        store.save_observation(
            "wallet-a", "signature-a", payload, [], parse_status="no_events", parser_version="1"
        )
        event = ActivityEvent(
            wallet_address="wallet-a",
            signature="signature-a",
            occurred_at=None,
            token_mint="mint-a",
            direction="in",
            amount=Decimal("3"),
        )

        self.assertEqual(
            store.reprocess_observation(
                "wallet-a", "signature-a", [event], parse_status="parsed", parser_version="2"
            ),
            1,
        )
        self.assertEqual(store.get_events(wallet_address="wallet-a"), [event])
        self.assertEqual(store.get_checkpoint("wallet-a"), "signature-a")
        self.assertEqual(store.get_raw_transaction("wallet-a", "signature-a"), payload)
        store.close()

    def test_reprocess_replaces_normalized_deltas_without_moving_checkpoint(self) -> None:
        store = SQLiteEventStore(":memory:")
        wallet = "wallet-a"
        first_payload = {"meta": {"err": None,
            "preTokenBalances": [{"owner": wallet, "mint": "mint-a",
                "uiTokenAmount": {"amount": "0", "decimals": 2}}],
            "postTokenBalances": [{"owner": wallet, "mint": "mint-a",
                "uiTokenAmount": {"amount": "100", "decimals": 2}}],
            "innerInstructions": []}, "transaction": {"message": {"instructions": []}}}
        first = normalize_transaction(first_payload, wallet, "sig-replay")
        store.save_observation(wallet, "sig-replay", first_payload, list(first.activity_events),
            parse_status=first.transaction.parse_status, parser_version=first.transaction.parser_version,
            normalized_observation=first)
        replayed = normalize_transaction(first_payload, wallet, "sig-replay")
        store.reprocess_observation(wallet, "sig-replay", list(replayed.activity_events),
            parse_status=replayed.transaction.parse_status,
            parser_version="replay-v2", normalized_observation=replayed)
        self.assertEqual(store.get_token_deltas(wallet, "sig-replay")[0].amount, Decimal("1"))
        self.assertEqual(store.get_checkpoint(wallet), "sig-replay")
        self.assertEqual(store.get_raw_transaction(wallet, "sig-replay"), first_payload)
        self.assertEqual(store.get_observation_metadata(wallet, "sig-replay")["parser_version"], "1")
        store.close()

    def test_reprocess_requires_existing_observation(self) -> None:
        store = SQLiteEventStore(":memory:")
        with self.assertRaises(KeyError):
            store.reprocess_observation(
                "wallet-a", "missing", [], parse_status="no_events", parser_version="2"
            )
        store.close()

    def test_integrity_check_and_storage_stats(self) -> None:
        store = SQLiteEventStore(":memory:")
        store.save_checkpoint("wallet-a", "signature-a")
        self.assertEqual(store.integrity_check(), ["ok"])
        stats = store.storage_stats()
        self.assertEqual(stats["wallet_checkpoints"], 1)
        self.assertGreater(stats["database_bytes"], 0)
        store.close()

    def test_normalized_contracts_are_persisted_with_legacy_events(self) -> None:
        store = SQLiteEventStore(":memory:")
        wallet = "wallet-a"
        payload = {
            "slot": 321, "blockTime": 1_730_000_000,
            "meta": {"err": None,
                "preTokenBalances": [{"owner": wallet, "mint": "mint-a",
                    "uiTokenAmount": {"amount": "100", "decimals": 2}}],
                "postTokenBalances": [{"owner": wallet, "mint": "mint-a",
                    "uiTokenAmount": {"amount": "350", "decimals": 2}}],
                "innerInstructions": []},
            "transaction": {"message": {"instructions": []}},
        }
        normalized = normalize_transaction(payload, wallet, "sig-a")
        store.save_observation(
            wallet, "sig-a", payload, list(normalized.activity_events),
            parse_status=normalized.transaction.parse_status,
            parser_version=normalized.transaction.parser_version,
            normalized_observation=normalized,
        )
        self.assertEqual(len(store.get_events(wallet_address=wallet)), 1)
        self.assertEqual(len(store.get_token_deltas(wallet, "sig-a")), 1)
        self.assertEqual(store.get_token_deltas(wallet, "sig-a")[0].amount, Decimal("2.5"))
        metadata = store.get_observation_metadata(wallet, "sig-a")
        self.assertEqual(metadata["chain"], "solana")
        self.assertEqual(metadata["slot"], 321)
        self.assertTrue(store.has_processed_signature(wallet, "sig-a"))
        self.assertEqual(store.get_checkpoint(wallet), "sig-a")
        store.close()

    def test_normalized_persistence_rolls_back_every_table_on_delta_failure(self) -> None:
        store = SQLiteEventStore(":memory:")
        wallet = "wallet-a"
        payload = {"meta": {"err": None,
            "preTokenBalances": [{"owner": wallet, "mint": "mint-a",
                "uiTokenAmount": {"amount": "0", "decimals": 2}}],
            "postTokenBalances": [{"owner": wallet, "mint": "mint-a",
                "uiTokenAmount": {"amount": "100", "decimals": 2}}],
            "innerInstructions": []}, "transaction": {"message": {"instructions": []}}}
        normalized = normalize_transaction(payload, wallet, "sig-fail")
        with store._connection_scope() as connection:
            connection.execute("""CREATE TRIGGER reject_delta BEFORE INSERT ON token_balance_deltas
                BEGIN SELECT RAISE(ABORT, 'forced delta failure'); END""")
        with self.assertRaisesRegex(Exception, "forced delta failure"):
            store.save_observation(wallet, "sig-fail", payload, list(normalized.activity_events),
                parse_status=normalized.transaction.parse_status,
                parser_version=normalized.transaction.parser_version,
                normalized_observation=normalized)
        self.assertIsNone(store.get_raw_transaction(wallet, "sig-fail"))
        self.assertFalse(store.has_processed_signature(wallet, "sig-fail"))
        self.assertIsNone(store.get_checkpoint(wallet))
        self.assertEqual(store.get_events(wallet_address=wallet), [])
        self.assertEqual(store.get_token_deltas(wallet, "sig-fail"), [])
        store.close()

    def test_migrates_legacy_observation_table_without_losing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            import sqlite3
            connection = sqlite3.connect(path)
            connection.executescript("""
                CREATE TABLE observed_transactions (
                    wallet_address TEXT NOT NULL, signature TEXT NOT NULL, payload_json TEXT,
                    parse_status TEXT NOT NULL, parser_version TEXT NOT NULL, parse_error TEXT,
                    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(wallet_address, signature));
                INSERT INTO observed_transactions(wallet_address, signature, payload_json,
                    parse_status, parser_version) VALUES ('wallet-a', 'old-sig', '{\"meta\":{}}', 'no_events', '1');
            """)
            connection.commit(); connection.close()
            store = SQLiteEventStore(path)
            self.assertEqual(store.get_raw_transaction("wallet-a", "old-sig"), {"meta": {}})
            metadata = store.get_observation_metadata("wallet-a", "old-sig")
            self.assertIsNone(metadata["chain"])
            self.assertIsNone(metadata["slot"])
            self.assertEqual(store.integrity_check(), ["ok"])
            store.close()

    def test_backup_restores_observations_and_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.sqlite3"
            backup_path = Path(directory) / "backups" / "smr-backup.sqlite3"
            source = SQLiteEventStore(source_path)
            payload = {"meta": {"err": None,
                "preTokenBalances": [{"owner": "wallet-a", "mint": "mint-a",
                    "uiTokenAmount": {"amount": "0", "decimals": 2}}],
                "postTokenBalances": [{"owner": "wallet-a", "mint": "mint-a",
                    "uiTokenAmount": {"amount": "125", "decimals": 2}}],
                "innerInstructions": []},
                "transaction": {"signatures": ["sig-a"], "message": {"instructions": []}}}
            normalized = normalize_transaction(payload, "wallet-a", "sig-a")
            source.save_observation(
                "wallet-a", "sig-a", payload, list(normalized.activity_events),
                parse_status=normalized.transaction.parse_status,
                parser_version=normalized.transaction.parser_version,
                normalized_observation=normalized,
            )

            self.assertEqual(source.backup_to(backup_path), backup_path)
            source.close()

            restored = SQLiteEventStore(backup_path)
            self.assertEqual(restored.integrity_check(), ["ok"])
            self.assertEqual(restored.get_checkpoint("wallet-a"), "sig-a")
            self.assertEqual(restored.get_raw_transaction("wallet-a", "sig-a"), payload)
            self.assertEqual(restored.get_token_deltas("wallet-a", "sig-a")[0].amount, Decimal("1.25"))
            restored.close()

    def test_backup_rejects_source_database_as_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            store = SQLiteEventStore(path)
            with self.assertRaises(ValueError):
                store.backup_to(path)
            store.close()

    def test_existing_database_reopens_with_observation_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            first = SQLiteEventStore(path)
            first.save_checkpoint("wallet-a", "old-signature")
            first.close()

            reopened = SQLiteEventStore(path)
            self.assertEqual(reopened.get_checkpoint("wallet-a"), "old-signature")
            self.assertIsNone(reopened.get_observation_metadata("wallet-a", "old-signature"))
            reopened.close()


if __name__ == "__main__":
    unittest.main()