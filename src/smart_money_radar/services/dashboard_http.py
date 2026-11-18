"""Adaptador HTTP local, autenticado e somente leitura para o SMR."""

import ipaddress
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from smart_money_radar.services.dashboard_read import DashboardReadService
from smart_money_radar.services.reconciliation_diagnostics import (
    ReconciliationDiagnosticsService,
)
from smart_money_radar.storage.event_store import SQLiteEventStore


class _SMRRequestHandler(BaseHTTPRequestHandler):
    server_version = "SMRReadOnly/1.0"
    sys_version = ""

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.auth_token}"
        # Constant-time comparison avoids leaking token-prefix timing.
        import hmac
        if not hmac.compare_digest(supplied, expected):
            self._send_json(401, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self) -> None:
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query, keep_blank_values=False)
        try:
            if parsed.path == "/health":
                self._send_json(200, {"status": "ok", "mode": "read_only"})
                return
            if parsed.path == "/api/v1/dashboard":
                wallet = params.get("wallet_address", [None])[0]
                result = self.server.dashboard_service.get_overview(
                    wallet_address=wallet
                )
                self._send_json(200, result)
                return
            if parsed.path == "/api/v1/reconciliation/attempts":
                result = self.server.diagnostics_service.list_attempts(
                    wallet_address=params.get("wallet_address", [None])[0],
                    signature=params.get("signature", [None])[0],
                    operation_id=params.get("operation_id", [None])[0],
                    status=params.get("status", [None])[0],
                    since=params.get("since", [None])[0],
                    until=params.get("until", [None])[0],
                    limit=int(params.get("limit", ["100"])[0]),
                )
                self._send_json(200, {"items": DashboardReadService._json_value(result)})
                return
            self._send_json(404, {"error": "not_found"})
        except (TypeError, ValueError) as exc:
            self._send_json(400, {"error": "invalid_query", "detail": str(exc)})
        except Exception:
            self._send_json(500, {"error": "internal_error"})

    def do_POST(self) -> None:
        self._send_json(405, {"error": "method_not_allowed"})

    def do_PUT(self) -> None:
        self._send_json(405, {"error": "method_not_allowed"})

    def do_DELETE(self) -> None:
        self._send_json(405, {"error": "method_not_allowed"})

    def log_message(self, format, *args):
        # Avoid logging authorization headers or query values that may be sensitive.
        return


def create_read_only_server(
    event_store: SQLiteEventStore,
    *,
    auth_token: str,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    """Create, but do not start, an authenticated loopback-only HTTP server."""
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError as exc:
        raise ValueError("host must be a loopback IP address") from exc
    if not is_loopback:
        raise ValueError("SMR read-only API must bind to loopback only")
    if not isinstance(auth_token, str) or len(auth_token) < 32:
        raise ValueError("auth_token must contain at least 32 characters")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be an integer between 0 and 65535")

    server = ThreadingHTTPServer((host, port), _SMRRequestHandler)
    server.auth_token = auth_token
    server.dashboard_service = DashboardReadService(event_store)
    server.diagnostics_service = ReconciliationDiagnosticsService(event_store)
    return server


def main(argv=None) -> None:
    """Run the local read-only API without enabling Helius/RPC networking."""
    import argparse
    import os
    from pathlib import Path

    parser = argparse.ArgumentParser(
        prog="smr-api",
        description="API HTTP local e somente leitura do SMART MONEY RADAR.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    token = os.environ.get("SMR_API_TOKEN", "")
    if len(token) < 32:
        raise SystemExit(
            "Defina SMR_API_TOKEN com pelo menos 32 caracteres antes de iniciar."
        )
    database_path = Path(
        os.environ.get("SMR_DB_PATH", "data/smr_history.sqlite3")
    ).expanduser()
    event_store = SQLiteEventStore(database_path)
    server = None
    try:
        server = create_read_only_server(
            event_store, auth_token=token, host=args.host, port=args.port
        )
        print(f"SMR API somente leitura disponível em http://{args.host}:{server.server_port}")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSMR API encerrada.")
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    finally:
        if server is not None:
            server.server_close()
        event_store.close()
