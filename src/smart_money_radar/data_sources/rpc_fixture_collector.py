"""Coleta controlada de transações Solana para fixtures de auditoria.

Somente leitura. Não transmite transações, não requer chave Helius e não
normaliza nem anonimiza o payload bruto.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from typing import Callable

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def _is_solana_signature(value: str) -> bool:
    """Valida alfabeto Base58 e tamanho decodificado de uma assinatura Ed25519."""
    if not isinstance(value, str) or not value:
        return False
    number = 0
    for char in value:
        digit = _BASE58_ALPHABET.find(char)
        if digit < 0:
            return False
        number = number * 58 + digit
    leading_zeroes = len(value) - len(value.lstrip("1"))
    decoded_length = (number.bit_length() + 7) // 8 + leading_zeroes
    return decoded_length == 64


@dataclass(frozen=True, slots=True)
class FixtureResult:
    signature: str
    raw_path: Path
    sha256: str
    slot: int
    version: str | int


class RpcFixtureCollector:
    def __init__(
        self,
        endpoint: str,
        output_dir: str | Path,
        *,
        timeout: float = 20.0,
        min_interval_seconds: float = 0.25,
        opener: Callable = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        parsed_endpoint = urlparse(endpoint)
        if parsed_endpoint.scheme != "https" or not parsed_endpoint.hostname:
            raise ValueError("O endpoint RPC deve ser uma URL HTTPS válida.")
        if timeout <= 0 or min_interval_seconds < 0:
            raise ValueError("Timeout deve ser positivo e intervalo não negativo.")
        self.endpoint = endpoint
        self.output_dir = Path(output_dir)
        self.timeout = timeout
        self.min_interval_seconds = min_interval_seconds
        self._opener = opener
        self._sleep = sleeper
        self._last_request: float | None = None

    def collect(self, signature: str) -> FixtureResult:
        if not _is_solana_signature(signature):
            raise ValueError("Assinatura Solana inválida: esperado Base58 de 64 bytes.")
        if self._last_request is not None:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.min_interval_seconds:
                self._sleep(self.min_interval_seconds - elapsed)

        body = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
            "params": [signature, {
                "commitment": "finalized",
                "encoding": "json",
                "maxSupportedTransactionVersion": 0,
            }],
        }, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint, data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            self._last_request = time.monotonic()
            with self._opener(request, timeout=self.timeout) as response:
                raw_bytes = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # Não propaga a mensagem da biblioteca: ela pode conter a URL/token.
            raise RuntimeError(
                f"Falha RPC ao coletar {signature} ({type(exc).__name__}); verifique conectividade e endpoint."
            ) from exc

        try:
            payload = json.loads(raw_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("RPC retornou conteúdo que não é JSON válido.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("RPC retornou JSON com estrutura inválida.")
        if payload.get("jsonrpc") != "2.0":
            raise RuntimeError("RPC retornou resposta sem JSON-RPC 2.0.")
        response_id = payload.get("id")
        if (
            isinstance(response_id, bool)
            or not isinstance(response_id, int)
            or response_id != 1
        ):
            raise RuntimeError("RPC retornou ID de resposta divergente da requisição.")
        if payload.get("error"):
            raise RuntimeError(f"Erro RPC: {payload['error']}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Transação não encontrada ou resposta RPC sem result.")
        tx = result.get("transaction")
        signatures = tx.get("signatures", []) if isinstance(tx, dict) else []
        if signature not in signatures:
            raise RuntimeError("A assinatura solicitada não confere com o payload retornado.")
        if not isinstance(result.get("slot"), int):
            raise RuntimeError("Payload sem slot válido.")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        raw_path = self.output_dir / f"{signature}.raw.json"
        manifest_path = self.output_dir / f"{signature}.manifest.json"
        # Criação exclusiva: evita sobrescrita inclusive em corrida entre processos.
        # Se a gravação do manifesto falhar, remove apenas o bruto criado nesta chamada.
        if raw_path.exists() or manifest_path.exists():
            raise FileExistsError("Fixture já existe; preservando evidência original.")
        digest = hashlib.sha256(raw_bytes).hexdigest()
        version = result.get("version", "legacy")
        manifest = {
            "signature": signature,
            "slot": result["slot"],
            "version": version,
            "commitment": "finalized",
            "encoding": "json",
            "endpoint_host": urlparse(self.endpoint).hostname,
            "raw_file": raw_path.name,
            "sha256": digest,
            "anonymized": False,
            "provenance": "Solana JSON-RPC getTransaction",
        }
        raw_created = False
        try:
            with raw_path.open("xb") as raw_file:
                raw_file.write(raw_bytes)
                raw_file.flush()
                os.fsync(raw_file.fileno())
            raw_created = True
            with manifest_path.open("x", encoding="utf-8") as manifest_file:
                manifest_file.write(json.dumps(manifest, indent=2) + "\n")
                manifest_file.flush()
                os.fsync(manifest_file.fileno())
        except Exception:
            if raw_created:
                raw_path.unlink(missing_ok=True)
            raise
        return FixtureResult(signature, raw_path, digest, result["slot"], version)


def endpoint_from_environment() -> str:
    endpoint = os.environ.get("SMR_SOLANA_RPC_URL", "").strip()
    if not endpoint:
        raise RuntimeError("Defina SMR_SOLANA_RPC_URL com um endpoint RPC HTTPS somente leitura.")
    return endpoint
