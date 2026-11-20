"""Preflight must never reveal credentials or perform a network request."""
import unittest

from smart_money_radar.services.launch_live_preflight import evaluate_launch_live_preflight


class SolanaLivePreflightTests(unittest.TestCase):
    def settings(self, **override):
        env = {"SMR_ALLOW_NETWORK": "true", "HELIUS_API_KEY": "super-private-example-value",
               "SOLANA_CLUSTER": "mainnet"}
        env.update(override)
        return env

    def evaluate(self, environ=None, **override):
        params = dict(
            environ=environ if environ is not None else self.settings(),
            addresses=("public-solana-address",), duration_seconds=120,
            page_size=100, max_pages=10, source_id="provider-mainnet-test",
        )
        params.update(override)
        return evaluate_launch_live_preflight(**params)

    def test_authorized_bounded_configuration_is_ready_but_quota_unproven(self):
        report = self.evaluate()
        self.assertTrue(report.ready)
        self.assertTrue(report.network_authorized)
        self.assertTrue(report.credentials_configured)
        self.assertFalse(report.limits_known)
        self.assertEqual(report.max_rpc_pages_per_reconciliation, 1000)
        self.assertNotIn("super-private-example-value", repr(report))

    def test_missing_authorization_or_credentials_fails_closed(self):
        for env in (
            self.settings(SMR_ALLOW_NETWORK="false"),
            self.settings(HELIUS_API_KEY=""),
            self.settings(HELIUS_API_KEY="replace_with_your_helius_api_key"),
            self.settings(SOLANA_CLUSTER="unknown"),
        ):
            with self.subTest(env=list(env)):
                self.assertFalse(self.evaluate(env).ready)

    def test_large_capture_or_unbounded_queries_rejected(self):
        for override in (
            {"duration_seconds": 901},
            {"duration_seconds": 0},
            {"page_size": 1000},
            {"max_pages": 100},
            {"addresses": ("a",) * 5},
            {"addresses": ("a", "a")},
            {"source_id": ""},
        ):
            with self.subTest(override=override):
                self.assertFalse(self.evaluate(**override).ready)

    def test_preflight_is_offline_and_never_prints_key(self):
        import socket
        from unittest.mock import patch
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")):
            report = self.evaluate()
        self.assertTrue(report.ready)
        self.assertNotIn("super-private-example-value", str(report))
        self.assertEqual(report.reasons, ())


if __name__ == "__main__":
    unittest.main()
