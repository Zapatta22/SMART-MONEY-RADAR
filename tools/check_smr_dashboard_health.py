#!/usr/bin/env python3
"""Authenticated, local-only dashboard health probe (no token in argv)."""
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

state = Path(os.environ.get("SMR_DASHBOARD_STATE_DIR", str(Path.home() / ".local/state/smr-dashboard")))
token_path = state / "health.token"
try:
    if token_path.is_symlink() or not token_path.is_file():
        raise ValueError("missing token")
    if token_path.stat().st_mode & 0o077:
        raise ValueError("insecure token permissions")
    token = token_path.read_text().strip()
    if len(token) < 32:
        raise ValueError("invalid token")
    req = Request("http://127.0.0.1:8765/health", headers={"Authorization": "Bearer " + token})
    with urlopen(req, timeout=3) as response:
        payload = json.load(response)
        if response.status != 200 or payload != {"status": "ok", "mode": "read_only"}:
            raise ValueError("unexpected health payload")
except (OSError, ValueError, HTTPError, URLError, json.JSONDecodeError):
    sys.exit(1)
sys.exit(0)
