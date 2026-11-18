#!/usr/bin/env python3
"""Verifica conectividade de leitura com um endpoint Solana RPC HTTPS.

Não imprime a URL completa, cabeçalhos, tokens ou resposta integral.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse


def main() -> int:
    endpoint = os.environ.get("SMR_SOLANA_RPC_URL", "").strip()
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname:
        print("BLOQUEADO: defina SMR_SOLANA_RPC_URL com endpoint HTTPS válido.")
        return 2
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getHealth"}).encode()
    request = urllib.request.Request(endpoint, data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"FALHA: host={parsed.hostname}; tipo={type(exc).__name__}; URL e credenciais omitidas.")
        return 1
    if payload.get("result") != "ok":
        print(f"FALHA: host={parsed.hostname}; resposta getHealth não confirmou ok.")
        return 1
    print(f"OK: RPC respondeu getHealth; host={parsed.hostname}; somente leitura.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
