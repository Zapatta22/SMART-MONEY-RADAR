"""Cliente estrito para leitura histórica de contas via Helius Historical Accounts API.

A API é específica da Helius (não é Solana JSON-RPC padrão). Este módulo é
somente leitura e nunca trata estado atual como evidência histórica.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class HistoricalAccountSnapshot:
    address: str
    queried_slot: int
    queried_transaction_index: int | None
    last_updated_slot: int
    last_updated_transaction_index: int | None
    owner: str
    lamports: int
    executable: bool
    rent_epoch: int
    data: bytes


def _position(slot: int, transaction_index: int | None) -> tuple[int, int]:
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise ValueError("slot deve ser inteiro não negativo")
    if transaction_index is None:
        return slot, (1 << 63) - 1
    if (
        isinstance(transaction_index, bool)
        or not isinstance(transaction_index, int)
        or transaction_index < 0
    ):
        raise ValueError("transaction_index deve ser inteiro não negativo")
    return slot, transaction_index


def _decode_snapshot(address: str, query_slot: int, query_index: int | None, value: object) -> HistoricalAccountSnapshot:
    if not isinstance(value, dict):
        raise ValueError("conta histórica ausente na posição solicitada")
    owner = value.get("owner")
    lamports = value.get("lamports")
    executable = value.get("executable")
    rent_epoch = value.get("rentEpoch")
    encoded = value.get("data")
    updated = value.get("lastUpdatedAt")
    if not isinstance(owner, str) or not owner:
        raise ValueError("owner ausente na conta histórica")
    if isinstance(lamports, bool) or not isinstance(lamports, int) or lamports < 0:
        raise ValueError("lamports inválido na conta histórica")
    if not isinstance(executable, bool):
        raise ValueError("executable inválido na conta histórica")
    if isinstance(rent_epoch, bool) or not isinstance(rent_epoch, int) or rent_epoch < 0:
        raise ValueError("rentEpoch inválido na conta histórica")
    if (
        not isinstance(encoded, list) or len(encoded) != 2
        or not isinstance(encoded[0], str) or encoded[1] != "base64"
    ):
        raise ValueError("data base64 inválido na conta histórica")
    try:
        raw_data = base64.b64decode(encoded[0], validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("data base64 inválido na conta histórica") from exc
    if not isinstance(updated, dict):
        raise ValueError("lastUpdatedAt ausente na conta histórica")
    updated_slot = updated.get("slot")
    updated_index = updated.get("transactionIndex")
    if isinstance(updated_slot, bool) or not isinstance(updated_slot, int) or updated_slot < 0:
        raise ValueError("lastUpdatedAt.slot inválido")
    if updated_index is not None and (
        isinstance(updated_index, bool) or not isinstance(updated_index, int) or updated_index < 0
    ):
        raise ValueError("lastUpdatedAt.transactionIndex inválido")
    if _position(updated_slot, updated_index) > _position(query_slot, query_index):
        raise ValueError("RPC retornou estado posterior à posição consultada")
    return HistoricalAccountSnapshot(
        address=address,
        queried_slot=query_slot,
        queried_transaction_index=query_index,
        last_updated_slot=updated_slot,
        last_updated_transaction_index=updated_index,
        owner=owner,
        lamports=lamports,
        executable=executable,
        rent_epoch=rent_epoch,
        data=raw_data,
    )


def get_historical_account_info(
    endpoint: str,
    address: str,
    slot: int,
    transaction_index: int | None = None,
    *,
    timeout: float = 20.0,
    opener: Callable = urllib.request.urlopen,
) -> HistoricalAccountSnapshot:
    """Lê o estado imediatamente após a transação indicada ou ao fim do slot."""
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("endpoint histórico deve ser HTTPS")
    if not isinstance(address, str) or not address.strip():
        raise ValueError("address obrigatório")
    _position(slot, transaction_index)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("timeout deve ser positivo")
    query = {"slot": slot}
    if transaction_index is not None:
        query["transactionIndex"] = transaction_index
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "smr-historical-account",
        "method": "getHistoricalAccountInfo",
        "params": [address, query, {"encoding": "base64", "commitment": "finalized"}],
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
        raise RuntimeError(
            f"falha na consulta histórica ({type(exc).__name__}); confira endpoint e acesso"
        ) from exc
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("RPC histórico retornou JSON inválido") from exc
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        raise RuntimeError("envelope JSON-RPC histórico inválido")
    if payload.get("id") != "smr-historical-account":
        raise RuntimeError("ID da resposta histórica diverge da requisição")
    if payload.get("error") is not None:
        error = payload["error"]
        code = error.get("code") if isinstance(error, dict) else None
        # Não ecoar mensagens do provedor, que podem conter detalhes do endpoint.
        raise RuntimeError(f"consulta histórica rejeitada pelo RPC (code={code})")
    result = payload.get("result")
    if not isinstance(result, dict) or "value" not in result:
        raise RuntimeError("resultado histórico sem campo value")
    return _decode_snapshot(address, slot, transaction_index, result["value"])


def get_historical_account_info_before_transaction(
    endpoint: str,
    address: str,
    slot: int,
    transaction_index: int,
    *,
    timeout: float = 20.0,
    opener: Callable = urllib.request.urlopen,
) -> HistoricalAccountSnapshot:
    """Lê estado imediatamente anterior à transação, respeitando índice zero."""
    _position(slot, transaction_index)
    if transaction_index == 0:
        if slot == 0:
            raise ValueError("não há slot anterior a zero")
        return get_historical_account_info(
            endpoint, address, slot - 1, timeout=timeout, opener=opener
        )
    return get_historical_account_info(
        endpoint, address, slot, transaction_index - 1,
        timeout=timeout, opener=opener,
    )
