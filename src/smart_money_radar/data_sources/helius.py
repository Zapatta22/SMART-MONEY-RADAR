"""Cliente JSON-RPC Helius para consultas Solana somente leitura."""

import asyncio
import json
from itertools import count
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from smart_money_radar.data_sources.transaction_parser import parse_transaction
from smart_money_radar.domain.models import ActivityEvent
from smart_money_radar.settings import HeliusSettings

JsonObject = dict[str, Any]


class HeliusRpcError(RuntimeError):
    """Erro RPC sanitizado para não expor a URL que contém a API key."""


class HeliusDataSource:
    """Acesso HTTP RPC e histórico recente via Helius; nunca envia transações."""

    def __init__(
        self,
        settings: HeliusSettings,
        *,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self._opener = opener or urlopen
        self._request_ids = count(1)

    def call(self, method: str, params: list[Any]) -> Any:
        request_id = next(self._request_ids)
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        request = Request(
            self.settings.http_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(
                request, timeout=self.settings.request_timeout_seconds
            ) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise HeliusRpcError(f"Helius RPC respondeu com HTTP {exc.code}.") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise HeliusRpcError(
                f"Falha de transporte Helius ({type(exc).__name__})."
            ) from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HeliusRpcError("Helius RPC retornou uma resposta inválida.") from None

        if not isinstance(response_payload, dict):
            raise HeliusRpcError("Helius RPC retornou um formato inválido.")
        response_id = response_payload.get("id")
        if (
            response_payload.get("jsonrpc") != "2.0"
            or isinstance(response_id, bool)
            or not isinstance(response_id, int)
            or response_id != request_id
        ):
            raise HeliusRpcError(
                "Helius RPC retornou resposta com versão JSON-RPC ou ID incompatível."
            )
        if "error" in response_payload:
            error = response_payload["error"]
            code = error.get("code") if isinstance(error, dict) else None
            suffix = f" (código {code})" if isinstance(code, int) else ""
            raise HeliusRpcError(f"Helius RPC retornou erro{suffix}.")
        if "result" not in response_payload:
            raise HeliusRpcError("Helius RPC não incluiu o campo result.")
        return response_payload["result"]

    def get_version(self) -> JsonObject:
        """Confirma resposta real do endpoint RPC, sem exibir a API key."""
        result = self.call("getVersion", [])
        if not isinstance(result, dict):
            raise HeliusRpcError("getVersion retornou um formato inválido.")
        return result

    def get_transaction(self, signature: str) -> JsonObject | None:
        """Consulta os detalhes JSON parsed de uma assinatura confirmada."""
        result = self.call(
            "getTransaction",
            [
                signature,
                {
                    "commitment": "confirmed",
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        )
        if result is not None and not isinstance(result, dict):
            raise HeliusRpcError("getTransaction retornou um formato inválido.")
        return result

    def get_signatures_for_address(
        self,
        wallet_address: str,
        *,
        limit: int = 100,
        before: str | None = None,
        until: str | None = None,
    ) -> list[JsonObject]:
        """Obtém uma página de assinaturas confirmadas para recuperação incremental."""
        if not wallet_address.strip():
            raise ValueError("Informe um endereço público de carteira.")
        if not 1 <= limit <= 1000:
            raise ValueError("O limite de assinaturas deve estar entre 1 e 1000.")
        options: dict[str, Any] = {"limit": limit, "commitment": "confirmed"}
        if before:
            options["before"] = before
        if until:
            options["until"] = until
        result = self.call("getSignaturesForAddress", [wallet_address, options])
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise HeliusRpcError("getSignaturesForAddress retornou um formato inválido.")
        seen_signatures: set[str] = set()
        for item in result:
            signature = item.get("signature")
            if not isinstance(signature, str) or not signature.strip():
                raise HeliusRpcError(
                    "getSignaturesForAddress retornou item sem assinatura válida."
                )
            if signature in seen_signatures:
                raise HeliusRpcError(
                    "getSignaturesForAddress retornou assinatura duplicada na mesma página."
                )
            seen_signatures.add(signature)
        return result

    def get_activity(self, wallet_address: str, *, limit: int = 25) -> list[ActivityEvent]:
        """Consulta uma janela limitada de assinaturas e seus detalhes."""
        if not 1 <= limit <= 100:
            raise ValueError("O limite de histórico deve estar entre 1 e 100.")
        signatures = self.get_signatures_for_address(wallet_address, limit=limit)
        events: list[ActivityEvent] = []
        for item in signatures:
            if item.get("err") is not None:
                continue
            signature = item.get("signature")
            if not isinstance(signature, str) or not signature:
                continue
            transaction = self.get_transaction(signature)
            if transaction is not None:
                events.extend(parse_transaction(transaction, wallet_address, signature))
        return events

    async def get_signatures_for_address_async(
        self, wallet_address: str, *, limit: int = 100, before: str | None = None, until: str | None = None
    ) -> list[JsonObject]:
        return await asyncio.to_thread(
            self.get_signatures_for_address, wallet_address, limit=limit, before=before, until=until
        )

    async def get_transaction_async(self, signature: str) -> JsonObject | None:
        """Executa a chamada HTTP sem bloquear o loop do WebSocket."""
        return await asyncio.to_thread(self.get_transaction, signature)