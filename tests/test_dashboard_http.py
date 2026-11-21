"""Tests for the authenticated loopback-only read-only HTTP adapter."""

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import Mock

from smart_money_radar.services.dashboard_http import create_read_only_server


class DashboardHTTPTests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.store.get_reconciliation_diagnostics.return_value = {
            "total_attempts": 0, "statuses": {}, "top_reasons": [],
            "pending_transactions_count": 0, "pending_transactions": [],
        }
        self.store.storage_stats.return_value = {}
        self.store.get_events.return_value = []
        self.store.list_cpmm_launch_archived_event_inputs.return_value = []
        self.store.list_smr_archived_event_inputs.return_value = []
        self.token = "t" * 40
        self.server = create_read_only_server(
            self.store, auth_token=self.token, port=0
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path, token=None, method="GET"):
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        req = Request(self.base + path, headers=headers, method=method)
        return urlopen(req)

    def test_local_dashboard_page_is_served_without_exposing_api_data(self):
        with self.request("/") as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers["Content-Type"])
            self.assertIn("Content-Security-Policy", response.headers)
        self.assertIn("SMART MONEY RADAR", body)
        self.assertIn("SMR_API_TOKEN", body)
        self.assertIn("/api/v1/dashboard", body)

    def test_mobile_dashboard_has_separate_archived_radar_render_targets(self):
        with self.request("/") as response:
            html=response.read().decode("utf-8")
        self.assertIn('id="launchEvents"',html)
        self.assertIn('id="smartEvents"',html)
        self.assertIn("data.radar_events",html)
        self.assertIn('id="radarCollectors"',html)
        self.assertIn("last_archived_event_at",html)
        self.assertIn("textContent",html)

    def test_api_serializes_archived_smart_money_without_trades(self):
        import hashlib
        raw=b'{"result":{"slot":9,"transaction":{"signatures":["sig-9"]}}}'
        self.store.list_smr_archived_event_inputs.return_value=[{
            "operation_id":"op-9","pool":"pool-9","side":"BUY",
            "available_at":"2026-11-20T23:30:00+00:00",
            "signature":"sig-9","wallet":"wallet-9",
            "raw_bytes":raw,"slot":9,
            "observed_at":"2026-11-20T23:29:00+00:00",
            "chain":"solana","occurred_at":"2026-11-20T23:28:00+00:00",
        }]
        with self.request("/api/v1/dashboard",self.token) as response:
            data=json.loads(response.read())
        self.assertEqual(data["radar_events"]["launch"],[])
        item,=data["radar_events"]["smart_money"]
        self.assertEqual(item["wallet_address"],"wallet-9")
        self.assertEqual(item["raw_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertEqual(item["direction"],"BUY")
        self.assertEqual(item["coverage"],"UNKNOWN")
        self.assertEqual(item["evidence_quality"],"UNKNOWN")
        self.assertFalse(item["operational_authorized"])
        self.assertEqual(data["radars"]["smart_money"]["status"],"UNKNOWN")
        self.assertEqual(data["radars"]["smart_money"]["last_archived_event_at"],"2026-11-20T23:30:00+00:00")

    def test_dashboard_requires_bearer_token(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/v1/dashboard")
        self.assertEqual(caught.exception.code, 401)

    def test_dashboard_returns_read_only_json(self):
        with self.request("/api/v1/dashboard", self.token) as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["mode"], "read_only")
        self.assertIn("reconciliation", payload)
        self.assertIn("storage", payload)

    def test_reconciliation_query_rejects_limit_above_500(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/v1/reconciliation/attempts?limit=501", self.token)
        self.assertEqual(caught.exception.code, 400)

    def test_unknown_route_returns_404(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/missing", self.token)
        self.assertEqual(caught.exception.code, 404)

    def test_mutation_method_is_rejected(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/v1/dashboard", self.token, method="POST")
        self.assertEqual(caught.exception.code, 405)

    def test_server_rejects_non_loopback_host_and_short_token(self):
        with self.assertRaises(ValueError):
            create_read_only_server(self.store, auth_token=self.token, host="0.0.0.0")
        with self.assertRaises(ValueError):
            create_read_only_server(self.store, auth_token="short")


if __name__ == "__main__":
    unittest.main()
