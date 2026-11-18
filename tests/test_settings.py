import os
import unittest
from pathlib import Path
from unittest.mock import patch

from smart_money_radar.settings import HeliusSettings, SettingsError


class HeliusSettingsTests(unittest.TestCase):
    def test_network_is_disabled_without_explicit_opt_in(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SettingsError, "SMR_ALLOW_NETWORK=true"):
                HeliusSettings.from_environment()

    def test_reads_api_key_and_cluster_from_environment(self) -> None:
        values = {
            "SMR_ALLOW_NETWORK": "true",
            "HELIUS_API_KEY": "simulated-key",
            "SOLANA_CLUSTER": "devnet",
            "SMR_DB_PATH": "/tmp/smr-test.sqlite3",
        }
        with patch.dict(os.environ, values, clear=True):
            settings = HeliusSettings.from_environment()

        self.assertEqual(settings.cluster, "devnet")
        self.assertEqual(settings.database_path, Path("/tmp/smr-test.sqlite3"))
        self.assertEqual(
            settings.http_url,
            "https://devnet.helius-rpc.com/?api-key=simulated-key",
        )
        self.assertEqual(
            settings.websocket_url,
            "wss://devnet.helius-rpc.com/?api-key=simulated-key",
        )

    def test_rejects_non_finite_or_boolean_timeout(self) -> None:
        for timeout in (True, float("nan"), float("inf"), 10**10000, 0, -1):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(SettingsError, "timeout RPC"):
                    HeliusSettings(
                        api_key="simulated-key",
                        request_timeout_seconds=timeout,
                    )

    def test_rejects_non_string_api_key(self) -> None:
        with self.assertRaisesRegex(SettingsError, "texto não vazio"):
            HeliusSettings(api_key=None)  # type: ignore[arg-type]

    def test_rejects_invalid_cluster(self) -> None:
        with self.assertRaisesRegex(SettingsError, "SOLANA_CLUSTER"):
            HeliusSettings(api_key="simulated-key", cluster="unknown")


if __name__ == "__main__":
    unittest.main()