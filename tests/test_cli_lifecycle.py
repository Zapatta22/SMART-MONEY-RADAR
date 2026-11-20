import unittest
from unittest.mock import patch

from smart_money_radar import cli
from smart_money_radar.settings import HeliusSettings


class StoreSpy:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class MonitorStub:
    async def run_forever(self, wallets, stop_event) -> None:
        return None


class FailingMonitorStub:
    async def run_forever(self, wallets, stop_event) -> None:
        raise RuntimeError("simulated monitor failure")


class CliLifecycleTests(unittest.TestCase):
    def test_watch_forwards_reference_mint_to_persisted_swap_monitor(self) -> None:
        settings = HeliusSettings(api_key="simulated-key")
        mint = "So11111111111111111111111111111111111111112"
        with (
            patch.object(cli.HeliusSettings, "from_environment", return_value=settings),
            patch.object(cli, "HeliusDataSource"),
            patch.object(cli, "SQLiteEventStore", return_value=StoreSpy()),
            patch.object(cli, "WalletMonitor", return_value=MonitorStub()) as monitor,
        ):
            cli.main(["watch", "public-wallet", "--reference-mint", mint, "--reference-mint", mint])
        self.assertEqual(monitor.call_args.kwargs["reference_mints"], (mint,))

    def test_invalid_reference_mint_is_rejected_before_opening_database(self) -> None:
        settings = HeliusSettings(api_key="simulated-key")
        with patch.object(cli, "SQLiteEventStore") as store:
            with self.assertRaisesRegex(ValueError, "mint de cotação inválido"):
                cli._run_monitor(settings, object(), ["public-wallet"], reference_mints=["short"])
        store.assert_not_called()

    def test_monitor_closes_event_store_when_run_finishes(self) -> None:
        store = StoreSpy()
        settings = HeliusSettings(api_key="simulated-key")
        with patch.object(cli, "SQLiteEventStore", return_value=store), patch.object(
            cli, "WalletMonitor", return_value=MonitorStub()
        ):
            cli._run_monitor(settings, object(), ["public-wallet"])  # type: ignore[arg-type]
        self.assertTrue(store.closed)

    def test_monitor_closes_event_store_when_monitor_raises(self) -> None:
        store = StoreSpy()
        settings = HeliusSettings(api_key="simulated-key")
        with patch.object(cli, "SQLiteEventStore", return_value=store), patch.object(
            cli, "WalletMonitor", return_value=FailingMonitorStub()
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated monitor failure"):
                cli._run_monitor(settings, object(), ["public-wallet"])  # type: ignore[arg-type]
        self.assertTrue(store.closed)


if __name__ == "__main__":
    unittest.main()
