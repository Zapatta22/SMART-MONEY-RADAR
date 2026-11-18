"""Tests for the smr-api command entry point."""

import os
import unittest
from unittest.mock import Mock, patch

from smart_money_radar.services import dashboard_http


class DashboardHTTPMainTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_requires_api_token(self):
        with self.assertRaises(SystemExit) as caught:
            dashboard_http.main([])
        self.assertIn("SMR_API_TOKEN", str(caught.exception))

    @patch.dict(os.environ, {"SMR_API_TOKEN": "x" * 40, "SMR_DB_PATH": ":memory:"}, clear=True)
    @patch("smart_money_radar.services.dashboard_http.SQLiteEventStore")
    @patch("smart_money_radar.services.dashboard_http.create_read_only_server")
    def test_starts_and_closes_local_server(self, create_server, store_class):
        store = store_class.return_value
        server = Mock()
        server.server_port = 8765
        create_server.return_value = server

        dashboard_http.main(["--port", "8765"])

        create_server.assert_called_once_with(
            store, auth_token="x" * 40, host="127.0.0.1", port=8765
        )
        server.serve_forever.assert_called_once_with()
        server.server_close.assert_called_once_with()
        store.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
