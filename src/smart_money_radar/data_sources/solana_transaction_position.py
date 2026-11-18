"""Localiza a posição transacional exata de uma assinatura dentro de um slot."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable


def get_transaction_index(
    endpoint: str,
    slot: int,
    signature: str,
    *,
    timeout: float = 25.0,
    opener: Callable = urllib.request.urlopen,
) -> int:
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise ValueError("RPC deve usar HTTPS")
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise ValueError("slot deve ser inteiro não negativo")
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError("signature obrigatória")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("timeout deve ser positivo")
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "smr-transaction-position",
        "method": "getBlock",
        "params": [slot, {
            "commitment": "finalized",
            "encoding": "json",
            "transactionDetails": "full",
            "rewards": False,
            "maxSupportedTransactionVersion": 1,
        }],
    }, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"falha ao consultar bloco ({type(exc).__name__})") from exc
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("RPC retornou JSON inválido para getBlock") from exc
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        raise RuntimeError("envelope JSON-RPC inválido para getBlock")
    if payload.get("id") != "smr-transaction-position":
        raise RuntimeError("ID da resposta getBlock divergente")
    if payload.get("error") is not None:
        error = payload["error"]
        code = error.get("code") if isinstance(error, dict) else None
        raise RuntimeError(f"getBlock rejeitado pelo RPC (code={code})")
    block = payload.get("result")
    if not isinstance(block, dict):
        raise RuntimeError(f"bloco {slot} indisponível")
    transactions = block.get("transactions")
    if not isinstance(transactions, list):
        raise RuntimeError("getBlock sem lista de transações")
    matches = []
    for index, item in enumerate(transactions):
        if not isinstance(item, dict):
            raise RuntimeError("entrada de transação inválida no bloco")
        signatures = item.get("transaction", {}).get("signatures")
        if not isinstance(signatures, list) or not signatures:
            raise RuntimeError("transação do bloco sem assinatura primária")
        if signatures[0] == signature:
            matches.append(index)
    if len(matches) != 1:
        if not matches:
            raise ValueError("assinatura não encontrada no slot informado")
        raise ValueError("assinatura primária duplicada no bloco")
    return matches[0]
