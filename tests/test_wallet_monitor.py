import asyncio
import json
import unittest
from decimal import Decimal

from smart_money_radar.domain.models import Wallet
from smart_money_radar.services.wallet_monitor import WalletMonitor
from smart_money_radar.settings import HeliusSettings
from smart_money_radar.storage.event_store import SQLiteEventStore


def simulated_transaction(signature: str = "simulated-signature") -> dict[str, object]:
    return {
        "blockTime": 1_730_000_000,
        "meta": {
            "err": None,
            "preTokenBalances": [],
            "postTokenBalances": [
                {
                    "owner": "public-wallet",
                    "mint": "mint-demo",
                    "uiTokenAmount": {"amount": "1230000", "decimals": 6},
                }
            ],
            "innerInstructions": [],
        },
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [],
                "instructions": [],
            }
        },
    }


class FakeWebSocket:
    def __init__(self, messages: list[str], stop_event: asyncio.Event) -> None:
        self.messages = list(messages)
        self.stop_event = stop_event
        self.sent: list[dict[str, object]] = []

    async def __aenter__(self) -> "FakeWebSocket":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def recv(self) -> str:
        if self.messages:
            return self.messages.pop(0)
        await self.stop_event.wait()
        return ""


class FakeDataSource:
    def __init__(self, stop_event: asyncio.Event) -> None:
        self.stop_event = stop_event
        self.signatures: list[str] = []

    async def get_transaction_async(self, signature: str) -> dict[str, object]:
        self.signatures.append(signature)
        self.stop_event.set()
        return simulated_transaction(signature)


class WalletMonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_subscription_enriches_and_stores_transaction_without_network(self) -> None:
        stop_event = asyncio.Event()
        messages = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": 42}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "logsNotification",
                    "params": {
                        "subscription": 42,
                        "result": {
                            "value": {
                                "signature": "simulated-signature",
                                "err": None,
                                "logs": [],
                            }
                        },
                    },
                }
            ),
        ]
        websocket = FakeWebSocket(messages, stop_event)
        data_source = FakeDataSource(stop_event)
        settings = HeliusSettings(api_key="simulated-key")
        # A file-backed temporary database is used because the store opens a
        # fresh SQLite connection for each operation.
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            monitor = WalletMonitor(
                settings,
                data_source,  # type: ignore[arg-type]
                store,
                websocket_connector=lambda *_args, **_kwargs: websocket,
            )

            await monitor.run_forever([Wallet("public-wallet")], stop_event)

            self.assertEqual(
                websocket.sent[0]["method"],
                "logsSubscribe",
            )
            self.assertEqual(
                websocket.sent[0]["params"][0],
                {"mentions": ["public-wallet"]},
            )
            self.assertEqual(data_source.signatures, ["simulated-signature"])
            events = store.get_events(wallet_address="public-wallet")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].token_mint, "mint-demo")
            self.assertEqual(events[0].direction, "in")
            self.assertEqual(events[0].amount, Decimal("1.23"))
            self.assertEqual(
                store.get_raw_transaction("public-wallet", "simulated-signature"),
                simulated_transaction(),
            )
            deltas = store.get_token_deltas("public-wallet", "simulated-signature")
            self.assertEqual(len(deltas), 1)
            self.assertEqual(deltas[0].token_mint, "mint-demo")
            self.assertEqual(deltas[0].amount, Decimal("1.23"))
            metadata = store.get_observation_metadata("public-wallet", "simulated-signature")
            self.assertEqual(metadata["chain"], "solana")
            self.assertEqual(metadata["slot"], None)

    async def test_retries_transaction_before_advancing_checkpoint(self) -> None:
        stop_event = asyncio.Event()

        class RetryDataSource:
            def __init__(self) -> None:
                self.calls = 0

            async def get_transaction_async(self, signature: str):
                self.calls += 1
                if self.calls < 3:
                    return None
                stop_event.set()
                return simulated_transaction(signature)

        messages = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": 42}),
            json.dumps({"method": "logsNotification", "params": {"subscription": 42,
                "result": {"value": {"signature": "retry-signature", "err": None}}}}),
        ]
        websocket = FakeWebSocket(messages, stop_event)
        source = RetryDataSource()
        delays: list[float] = []

        async def no_wait(delay: float) -> None:
            delays.append(delay)

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            monitor = WalletMonitor(
                HeliusSettings(api_key="simulated-key"), source, store,  # type: ignore[arg-type]
                websocket_connector=lambda *_args, **_kwargs: websocket,
                sleep=no_wait,
            )
            await monitor.run_forever([Wallet("public-wallet")], stop_event)
            self.assertEqual(source.calls, 3)
            self.assertEqual(delays, [0.5, 1.0])
            self.assertEqual(store.get_checkpoint("public-wallet"), "retry-signature")
            self.assertEqual(len(store.get_events(wallet_address="public-wallet")), 1)

    async def test_backfills_signatures_since_persisted_checkpoint(self) -> None:
        stop_event = asyncio.Event()
        transaction = simulated_transaction("new-signature")

        class BackfillDataSource:
            def __init__(self) -> None:
                self.processed: list[str] = []

            async def get_signatures_for_address_async(self, wallet_address: str, **kwargs):
                return [
                    {"signature": "new-signature", "err": None},
                    {"signature": "old-checkpoint", "err": None},
                ]

            async def get_transaction_async(self, signature: str):
                self.processed.append(signature)
                if signature == "new-signature":
                    stop_event.set()
                return transaction

        websocket = FakeWebSocket(
            [json.dumps({"jsonrpc": "2.0", "id": 1, "result": 42})], stop_event
        )
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            store.save_checkpoint("public-wallet", "old-checkpoint")
            source = BackfillDataSource()
            monitor = WalletMonitor(
                HeliusSettings(api_key="simulated-key"), source, store,  # type: ignore[arg-type]
                websocket_connector=lambda *_args, **_kwargs: websocket,
            )
            await monitor.run_forever([Wallet("public-wallet")], stop_event)
            self.assertEqual(source.processed, ["new-signature"])
            self.assertEqual(store.get_checkpoint("public-wallet"), "new-signature")


    async def test_backfill_fails_if_checkpoint_is_outside_page_limit(self) -> None:
        stop_event = asyncio.Event()

        class PagedSource:
            async def get_signatures_for_address_async(self, wallet_address: str, **kwargs):
                before = kwargs.get("before")
                if before is None:
                    return [{"signature": "page-1-tail", "err": None}]
                return [{"signature": "page-2-tail", "err": None}]

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            store.save_checkpoint("public-wallet", "old-checkpoint")
            monitor = WalletMonitor(
                HeliusSettings(api_key="simulated-key"), PagedSource(), store,  # type: ignore[arg-type]
                backfill_page_limit=1, backfill_max_pages=2,
            )
            with self.assertRaisesRegex(RuntimeError, "Checkpoint não encontrado"):
                await monitor._backfill_wallet("public-wallet", stop_event)
            self.assertEqual(store.get_checkpoint("public-wallet"), "old-checkpoint")

    async def test_backfill_keeps_checkpoint_when_transaction_retries_are_exhausted(self) -> None:
        stop_event = asyncio.Event()

        class UnavailableSource:
            async def get_signatures_for_address_async(self, wallet_address: str, **kwargs):
                return [
                    {"signature": "pending-signature", "err": None},
                    {"signature": "old-checkpoint", "err": None},
                ]

            async def get_transaction_async(self, signature: str):
                return None

        async def no_wait(_: float) -> None:
            return None

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            store.save_checkpoint("public-wallet", "old-checkpoint")
            monitor = WalletMonitor(
                HeliusSettings(api_key="simulated-key"), UnavailableSource(), store,  # type: ignore[arg-type]
                transaction_retry_attempts=2, sleep=no_wait,
            )
            with self.assertRaisesRegex(RuntimeError, "Backfill pausado"):
                await monitor._backfill_wallet("public-wallet", stop_event)
            self.assertEqual(store.get_checkpoint("public-wallet"), "old-checkpoint")
            self.assertFalse(store.has_processed_signature("public-wallet", "pending-signature"))

    async def test_backfill_rpc_error_preserves_checkpoint(self) -> None:
        stop_event = asyncio.Event()

        class RpcFailureSource:
            async def get_signatures_for_address_async(self, wallet_address: str, **kwargs):
                raise OSError("simulated RPC outage")

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            store.save_checkpoint("public-wallet", "old-checkpoint")
            monitor = WalletMonitor(
                HeliusSettings(api_key="simulated-key"), RpcFailureSource(), store,  # type: ignore[arg-type]
            )
            with self.assertRaisesRegex(OSError, "simulated RPC outage"):
                await monitor._backfill_wallet("public-wallet", stop_event)
            self.assertEqual(store.get_checkpoint("public-wallet"), "old-checkpoint")

    async def test_websocket_notification_overlapping_backfill_is_deduplicated(self) -> None:
        stop_event = asyncio.Event()
        notification = json.dumps({
            "method": "logsNotification",
            "params": {"subscription": 42, "result": {"value": {
                "signature": "overlap-signature", "err": None,
            }}},
        })

        class OneNotificationSocket(FakeWebSocket):
            async def recv(self) -> str:
                raw = await super().recv()
                stop_event.set()
                return raw

        class OverlapSource:
            def __init__(self) -> None:
                self.transaction_calls: list[str] = []

            async def get_signatures_for_address_async(self, wallet_address: str, **kwargs):
                return [
                    {"signature": "overlap-signature", "err": None},
                    {"signature": "old-checkpoint", "err": None},
                ]

            async def get_transaction_async(self, signature: str):
                self.transaction_calls.append(signature)
                return simulated_transaction(signature)

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            store.save_checkpoint("public-wallet", "old-checkpoint")
            source = OverlapSource()
            websocket = OneNotificationSocket(
                [json.dumps({"jsonrpc": "2.0", "id": 1, "result": 42}), notification],
                stop_event,
            )
            monitor = WalletMonitor(
                HeliusSettings(api_key="simulated-key"), source, store,  # type: ignore[arg-type]
                websocket_connector=lambda *_args, **_kwargs: websocket,
            )
            await monitor.run_forever([Wallet("public-wallet")], stop_event)
            self.assertEqual(source.transaction_calls, ["overlap-signature"])
            self.assertEqual(store.get_checkpoint("public-wallet"), "overlap-signature")
            self.assertEqual(len(store.get_events(wallet_address="public-wallet")), 1)

    async def test_reconnects_with_exponential_backoff(self) -> None:
        stop_event = asyncio.Event()
        data_source = FakeDataSource(stop_event)
        messages = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": 7}),
            json.dumps(
                {
                    "method": "logsNotification",
                    "params": {
                        "subscription": 7,
                        "result": {
                            "value": {
                                "signature": "simulated-signature",
                                "err": None,
                            }
                        },
                    },
                }
            ),
        ]
        websocket = FakeWebSocket(messages, stop_event)
        attempts = 0
        delays: list[float] = []

        def connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                raise OSError("simulated disconnect")
            return websocket

        async def no_wait(delay: float) -> None:
            delays.append(delay)

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            monitor = WalletMonitor(
                HeliusSettings(api_key="simulated-key"),
                data_source,  # type: ignore[arg-type]
                SQLiteEventStore(Path(directory) / "history.sqlite3"),
                initial_backoff_seconds=1,
                maximum_backoff_seconds=4,
                websocket_connector=connector,
                sleep=no_wait,
            )

            await monitor.run_forever([Wallet("public-wallet")], stop_event)

        self.assertEqual(attempts, 3)
        self.assertEqual(delays, [1, 2])
        self.assertEqual(data_source.signatures, ["simulated-signature"])

    async def test_transaction_without_recognized_events_is_archived_before_checkpoint(self) -> None:
        stop_event = asyncio.Event()
        raw_transaction = {"meta": {"err": None, "innerInstructions": []}, "transaction": {"signatures": ["unclassified-signature"], "message": {"accountKeys": [], "instructions": []}}}

        class NoEventSource:
            async def get_transaction_async(self, signature: str):
                stop_event.set()
                return raw_transaction

        messages = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": 42}),
            json.dumps({"method": "logsNotification", "params": {"subscription": 42,
                "result": {"value": {"signature": "unclassified-signature", "err": None}}}}),
        ]
        websocket = FakeWebSocket(messages, stop_event)
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            monitor = WalletMonitor(
                HeliusSettings(api_key="simulated-key"), NoEventSource(), store,  # type: ignore[arg-type]
                websocket_connector=lambda *_args, **_kwargs: websocket,
            )
            await monitor.run_forever([Wallet("public-wallet")], stop_event)
            self.assertEqual(
                store.get_raw_transaction("public-wallet", "unclassified-signature"),
                raw_transaction,
            )
            self.assertEqual(store.get_checkpoint("public-wallet"), "unclassified-signature")
            self.assertEqual(store.get_events(wallet_address="public-wallet"), [])
            self.assertEqual(
                store.get_observation_metadata("public-wallet", "unclassified-signature")["parse_status"],
                "no_events",
            )

    async def test_parser_exception_archives_payload_with_parse_error_status(self) -> None:
        from unittest.mock import patch
        import tempfile
        stop_event = asyncio.Event()
        raw_transaction = {"meta": {"err": None, "innerInstructions": []}, "transaction": {"signatures": ["parser-error-signature"], "message": {"accountKeys": [], "instructions": []}}}

        class ErrorSource:
            async def get_transaction_async(self, signature: str):
                stop_event.set()
                return raw_transaction

        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            monitor = WalletMonitor(HeliusSettings(api_key="simulated-key"), ErrorSource(), store)  # type: ignore[arg-type]
            with patch("smart_money_radar.domain.raydium_cpmm_persistence_pipeline.normalize_transaction", side_effect=ValueError("bad parser fixture")):
                success = await monitor._collect_transaction("public-wallet", "parser-error-signature", stop_event)
            self.assertFalse(success)
            self.assertEqual(
                store.get_raw_transaction("public-wallet", "parser-error-signature"),
                raw_transaction,
            )
            metadata = store.get_observation_metadata("public-wallet", "parser-error-signature")
            self.assertEqual(metadata["parse_status"], "parse_error")
            self.assertEqual(metadata["parse_error"], "ValueError")
            self.assertIsNone(store.get_checkpoint("public-wallet"))
            self.assertEqual(
                store.get_pending_signatures("public-wallet"),
                ["parser-error-signature"],
            )

    async def test_backfill_records_failed_on_chain_signature_explicitly(self) -> None:
        stop_event = asyncio.Event()

        class FailedOnChainSource:
            async def get_signatures_for_address_async(self, wallet_address: str, **kwargs):
                return [
                    {"signature": "failed-signature", "err": {"InstructionError": [0, "failed"]}},
                    {"signature": "old-checkpoint", "err": None},
                ]

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            store.save_checkpoint("public-wallet", "old-checkpoint")
            monitor = WalletMonitor(
                HeliusSettings(api_key="simulated-key"), FailedOnChainSource(), store,  # type: ignore[arg-type]
            )
            await monitor._backfill_wallet("public-wallet", stop_event)
            self.assertEqual(store.get_checkpoint("public-wallet"), "failed-signature")
            self.assertEqual(
                store.get_observation_metadata("public-wallet", "failed-signature")["parse_status"],
                "failed_on_chain",
            )
            self.assertTrue(store.has_processed_signature("public-wallet", "failed-signature"))


    async def test_first_run_replays_archived_pending_observation_without_history_scan(self) -> None:
        stop_event = asyncio.Event()

        class PendingSource:
            def __init__(self):
                self.calls = []

            async def get_transaction_async(self, signature: str):
                self.calls.append(signature)
                return simulated_transaction(signature)

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            store.save_observation(
                "public-wallet", "pending-first-run", simulated_transaction("pending-first-run"), [],
                parse_status="no_events", parser_version="1",
                advance_checkpoint=False,
            )
            source = PendingSource()
            monitor = WalletMonitor(
                HeliusSettings(api_key="simulated-key"), source, store,  # type: ignore[arg-type]
            )

            await monitor._backfill_wallet("public-wallet", stop_event)

            self.assertEqual(source.calls, ["pending-first-run"])
            self.assertTrue(store.has_processed_signature("public-wallet", "pending-first-run"))
            self.assertEqual(store.get_checkpoint("public-wallet"), "pending-first-run")
            self.assertEqual(store.get_pending_signatures("public-wallet"), [])



    async def test_damm_v2_unresolved_swap_blocks_cpmm_and_checkpoint(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import patch
        import tempfile
        from pathlib import Path

        stop_event = asyncio.Event()

        class Source:
            async def get_transaction_async(self, signature: str):
                stop_event.set()
                return simulated_transaction(signature)

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "history.sqlite3")
            monitor = WalletMonitor(
                HeliusSettings(api_key="simulated-key"), Source(), store,  # type: ignore[arg-type]
            )
            damm_pending = SimpleNamespace(
                ready_for_next_venue=False,
                reconciled_swaps=0,
                decoded_swaps=1,
            )
            with patch(
                "smart_money_radar.services.wallet_monitor.process_damm_v2_observation",
                return_value=damm_pending,
            ), patch(
                "smart_money_radar.services.wallet_monitor.process_raydium_cpmm_observation"
            ) as cpmm:
                result = await monitor._collect_transaction(
                    "public-wallet", "pending-damm-signature", stop_event
                )
            self.assertFalse(result)
            cpmm.assert_not_called()
            self.assertFalse(
                store.has_processed_signature("public-wallet", "pending-damm-signature")
            )
            self.assertIsNone(store.get_checkpoint("public-wallet"))


if __name__ == "__main__":
    unittest.main()