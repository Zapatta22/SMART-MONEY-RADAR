"""Monitor WebSocket de carteiras com reconexão exponencial."""

import asyncio
import json
import logging
import math
import time
from collections.abc import Callable, Sequence
from typing import Any

from websockets import connect

from smart_money_radar.data_sources.helius import HeliusDataSource
from smart_money_radar.data_sources.transaction_parser import PARSER_VERSION
from smart_money_radar.domain.models import Wallet
from smart_money_radar.domain.damm_v2_persistence_pipeline import (
    process_damm_v2_observation,
)
from smart_money_radar.domain.raydium_cpmm_persistence_pipeline import (
    process_raydium_cpmm_observation,
)
from smart_money_radar.settings import HeliusSettings
from smart_money_radar.storage.event_store import SQLiteEventStore

Logger = logging.Logger


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


class WalletMonitor:
    """Assina logs de carteiras públicas, enriquece assinaturas e persiste eventos."""

    def __init__(
        self,
        settings: HeliusSettings,
        data_source: HeliusDataSource,
        event_store: SQLiteEventStore,
        *,
        initial_backoff_seconds: float = 1.0,
        maximum_backoff_seconds: float = 30.0,
        stable_session_seconds: float = 60.0,
        transaction_retry_attempts: int = 3,
        transaction_retry_initial_seconds: float = 0.5,
        backfill_page_limit: int = 100,
        backfill_max_pages: int = 10,
        reference_mints: Sequence[str] = (),
        token2022_fee_proof_resolver: Callable[..., Any] | None = None,
        websocket_connector: Callable[..., Any] | None = None,
        sleep: Callable[[float], Any] = asyncio.sleep,
        logger: Logger | None = None,
    ) -> None:
        numeric_parameters = (
            initial_backoff_seconds,
            maximum_backoff_seconds,
            stable_session_seconds,
            transaction_retry_initial_seconds,
        )
        if any(not _is_finite_number(value) for value in numeric_parameters):
            raise ValueError("Parâmetros temporais devem ser números finitos.")
        if (
            initial_backoff_seconds <= 0
            or maximum_backoff_seconds < initial_backoff_seconds
            or stable_session_seconds < 0
            or transaction_retry_initial_seconds < 0
        ):
            raise ValueError("Parâmetros de backoff/retry inválidos.")
        if (
            isinstance(transaction_retry_attempts, bool)
            or not isinstance(transaction_retry_attempts, int)
            or transaction_retry_attempts < 1
        ):
            raise ValueError("transaction_retry_attempts deve ser inteiro positivo.")
        if (
            isinstance(backfill_page_limit, bool)
            or not isinstance(backfill_page_limit, int)
            or not 1 <= backfill_page_limit <= 1000
            or isinstance(backfill_max_pages, bool)
            or not isinstance(backfill_max_pages, int)
            or backfill_max_pages < 1
        ):
            raise ValueError("Parâmetros de recuperação histórica inválidos.")
        self.settings = settings
        self.data_source = data_source
        self.event_store = event_store
        self.initial_backoff_seconds = initial_backoff_seconds
        self.maximum_backoff_seconds = maximum_backoff_seconds
        self.stable_session_seconds = stable_session_seconds
        self.transaction_retry_attempts = transaction_retry_attempts
        self.transaction_retry_initial_seconds = transaction_retry_initial_seconds
        self.backfill_page_limit = backfill_page_limit
        if any(not isinstance(mint, str) or not mint.strip() for mint in reference_mints):
            raise ValueError("reference_mints deve conter apenas mints não vazios.")
        self.reference_mints = tuple(reference_mints)
        self._token2022_fee_proof_resolver = token2022_fee_proof_resolver
        self.backfill_max_pages = backfill_max_pages
        self._websocket_connector = websocket_connector or connect
        self._sleep = sleep
        self._logger = logger or logging.getLogger(__name__)

    async def run_forever(
        self,
        wallets: Sequence[Wallet],
        stop_event: asyncio.Event,
    ) -> None:
        addresses = list(dict.fromkeys(wallet.address for wallet in wallets))
        if not addresses:
            raise ValueError("Informe ao menos um endereço público para monitorar.")

        delay = self.initial_backoff_seconds
        while not stop_event.is_set():
            started_at = time.monotonic()
            try:
                await self._listen_once(addresses, stop_event)
                if stop_event.is_set():
                    return
                raise ConnectionError("A sessão WebSocket terminou inesperadamente.")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if stop_event.is_set():
                    return
                elapsed = time.monotonic() - started_at
                if elapsed >= self.stable_session_seconds:
                    delay = self.initial_backoff_seconds
                self._logger.warning(
                    "WebSocket Helius desconectado; nova tentativa em %.1fs (%s).",
                    delay,
                    type(exc).__name__,
                )
                if await self._wait_or_stop(stop_event, delay):
                    return
                delay = min(delay * 2, self.maximum_backoff_seconds)

    async def _listen_once(
        self,
        wallet_addresses: Sequence[str],
        stop_event: asyncio.Event,
    ) -> None:
        request_to_wallet: dict[int, str] = {}
        subscription_to_wallet: dict[int, str] = {}
        async with self._websocket_connector(
            self.settings.websocket_url,
            ping_interval=30,
            ping_timeout=20,
            open_timeout=10,
            max_size=1_048_576,
        ) as websocket:
            for request_id, address in enumerate(wallet_addresses, start=1):
                request_to_wallet[request_id] = address
                await websocket.send(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "logsSubscribe",
                            "params": [
                                {"mentions": [address]},
                                {"commitment": "confirmed"},
                            ],
                        }
                    )
                )

            self._logger.info(
                "Conectado ao WebSocket Helius; aguardando confirmações para %d carteira(s).",
                len(wallet_addresses),
            )
            # A assinatura já foi enviada. Recupera o intervalo desde o último
            # checkpoint enquanto as notificações novas ficam enfileiradas no socket.
            for address in wallet_addresses:
                if stop_event.is_set():
                    return
                await self._backfill_wallet(address, stop_event)
            while not stop_event.is_set():
                raw_message = await self._receive_or_stop(websocket, stop_event)
                if raw_message is None:
                    return
                try:
                    message = json.loads(raw_message)
                except (json.JSONDecodeError, TypeError):
                    self._logger.warning("Mensagem WebSocket inválida; ignorada.")
                    continue
                if not isinstance(message, dict):
                    continue

                if "id" in message:
                    self._handle_subscription_response(
                        message, request_to_wallet, subscription_to_wallet
                    )
                    continue
                if (
                    message.get("jsonrpc") != "2.0"
                    or message.get("method") != "logsNotification"
                ):
                    continue

                notification = message.get("params")
                if not isinstance(notification, dict):
                    continue
                subscription_id = notification.get("subscription")
                if isinstance(subscription_id, bool) or not isinstance(subscription_id, int):
                    continue
                wallet_address = subscription_to_wallet.get(subscription_id)
                result = notification.get("result")
                value = result.get("value") if isinstance(result, dict) else None
                if not wallet_address or not isinstance(value, dict):
                    continue
                if value.get("err") is not None:
                    continue
                signature = value.get("signature")
                if not isinstance(signature, str) or not signature:
                    continue
                await self._collect_transaction(wallet_address, signature, stop_event)

    def _handle_subscription_response(
        self,
        message: dict[str, Any],
        request_to_wallet: dict[int, str],
        subscription_to_wallet: dict[int, str],
    ) -> None:
        if message.get("jsonrpc") != "2.0":
            raise RuntimeError("Resposta logsSubscribe sem versão JSON-RPC 2.0.")
        request_id = message.get("id")
        if (
            isinstance(request_id, bool)
            or not isinstance(request_id, int)
            or request_id not in request_to_wallet
        ):
            return
        if "error" in message:
            error = message["error"]
            code = error.get("code") if isinstance(error, dict) else None
            raise RuntimeError(
                f"Helius recusou uma assinatura logsSubscribe (código {code})."
            )
        subscription_id = message.get("result")
        if isinstance(subscription_id, bool) or not isinstance(subscription_id, int):
            raise RuntimeError("Resposta logsSubscribe sem ID de assinatura inteiro válido.")
        subscription_to_wallet[subscription_id] = request_to_wallet[request_id]

    async def _collect_transaction(
        self,
        wallet_address: str,
        signature: str,
        stop_event: asyncio.Event | None = None,
        *,
        advance_checkpoint: bool = True,
    ) -> bool:
        """Busca, interpreta e persiste; só avança o cursor após sucesso."""
        if self.event_store.has_processed_signature(wallet_address, signature):
            self._logger.debug("Assinatura já processada; notificação duplicada ignorada.")
            return True
        delay = self.transaction_retry_initial_seconds
        for attempt in range(1, self.transaction_retry_attempts + 1):
            if stop_event is not None and stop_event.is_set():
                return False
            try:
                transaction = await self.data_source.get_transaction_async(signature)
            except Exception as exc:
                self._logger.warning(
                    "Tentativa %d/%d falhou ao consultar transação (%s).",
                    attempt, self.transaction_retry_attempts, type(exc).__name__,
                )
                transaction = None
            if transaction is not None:
                try:
                    fee_proofs = ()
                    if self._token2022_fee_proof_resolver is not None:
                        fee_proof_resolution = await asyncio.to_thread(
                            self._token2022_fee_proof_resolver,
                            transaction,
                            monitored_wallet=wallet_address,
                            signature=signature,
                            rpc_endpoint=self.settings.http_url,
                        )
                        fee_proofs = fee_proof_resolution.proofs
                        if fee_proof_resolution.reasons:
                            self._logger.warning(
                                "Prova de taxa Token-2022 indisponível para %d mint(s); mantendo fail-closed.",
                                len(fee_proof_resolution.unresolved_mints),
                            )
                    damm_result = process_damm_v2_observation(
                        self.event_store,
                        transaction,
                        wallet_address=wallet_address,
                        signature=signature,
                        transfer_fee_absence_proofs=fee_proofs,
                    )
                except Exception as exc:
                    self._logger.warning(
                        "Transação arquivada, mas o pipeline DAMM v2 não foi concluído (%s); checkpoint preservado.",
                        type(exc).__name__,
                    )
                    return False
                if not damm_result.ready_for_next_venue:
                    self._logger.warning(
                        "Transação permanece pendente no DAMM v2: %d/%d swap(s) reconciliados; %d pendência(s); checkpoint preservado.",
                        damm_result.reconciled_swaps,
                        damm_result.decoded_swaps,
                        damm_result.unresolved_swaps,
                    )
                    return False
                try:
                    result = process_raydium_cpmm_observation(
                        self.event_store,
                        transaction,
                        wallet_address=wallet_address,
                        signature=signature,
                        reference_mints=self.reference_mints,
                        advance_checkpoint=advance_checkpoint,
                    )
                except Exception as exc:
                    self._logger.warning(
                        "Transação arquivada, mas o pipeline CPMM não foi concluído (%s); checkpoint preservado.",
                        type(exc).__name__,
                    )
                    return False
                # Em backfill ordenado, advance_checkpoint=False é intencional:
                # a conclusão do processamento deve ser separada do avanço do cursor,
                # que será feito depois pelo CAS com o slot/assinatura da página RPC.
                if (
                    result.status not in {"processed", "failed_on_chain", "no_cpmm_swaps"}
                    or result.unresolved_swaps != 0
                ):
                    self._logger.warning(
                        "Transação permanece pendente: %d/%d swap(s) sem reconciliação completa; checkpoint preservado.",
                        result.unresolved_swaps,
                        result.decoded_swaps,
                    )
                    return False
                self._logger.info(
                    "Transação processada (%s): %d swap(s) decodificado(s), %d bundle(s) persistido(s).",
                    result.status,
                    result.decoded_swaps,
                    result.saved_bundles,
                )
                return True
            if attempt < self.transaction_retry_attempts:
                self._logger.info(
                    "Transação ainda indisponível; repetindo consulta (%d/%d).",
                    attempt + 1, self.transaction_retry_attempts,
                )
                if delay > 0:
                    await self._sleep(delay)
                    delay *= 2
        self._logger.warning(
            "Transação não processada após %d tentativas; checkpoint preservado para recuperação.",
            self.transaction_retry_attempts,
        )
        return False

    async def _backfill_wallet(self, wallet_address: str, stop_event: asyncio.Event) -> None:
        """Recupera assinaturas posteriores ao último checkpoint, em ordem cronológica."""
        initial_checkpoint = self.event_store.get_checkpoint(wallet_address)
        pending_limit = self.backfill_page_limit * self.backfill_max_pages
        pending = self.event_store.get_pending_signatures(
            wallet_address, limit=pending_limit + 1
        )
        if len(pending) > pending_limit:
            raise RuntimeError(
                "Há mais observações pendentes que o limite de recuperação; cursor preservado."
            )
        for pending_signature in pending:
            if stop_event.is_set():
                return
            if not await self._collect_transaction(
                wallet_address,
                pending_signature,
                stop_event,
                advance_checkpoint=initial_checkpoint is None,
            ):
                raise RuntimeError(
                    "Recuperação de observação pendente interrompida; checkpoint preservado."
                )

        if initial_checkpoint is None:
            # Na primeira execução, recupera somente observações já arquivadas;
            # não inicia varredura histórica ampla sem autorização.
            return
        checkpoint = self.event_store.get_checkpoint(wallet_address)
        if checkpoint is None:
            return
        collected: list[dict[str, Any]] = []
        before: str | None = None
        found_checkpoint = False
        for _ in range(self.backfill_max_pages):
            page = await self.data_source.get_signatures_for_address_async(
                wallet_address, limit=self.backfill_page_limit, before=before
            )
            if not page:
                break
            for item in page:
                signature = item.get("signature")
                if signature == checkpoint:
                    found_checkpoint = True
                    break
                if isinstance(signature, str) and signature:
                    collected.append(item)
            if found_checkpoint:
                break
            last_signature = page[-1].get("signature")
            if not isinstance(last_signature, str) or not last_signature:
                raise RuntimeError("Backfill recebeu página sem assinatura final válida.")
            before = last_signature
            if len(page) < self.backfill_page_limit:
                break
        if not found_checkpoint:
            raise RuntimeError(
                "Checkpoint não encontrado dentro do limite de páginas; recuperação interrompida para evitar lacuna silenciosa."
            )
        if collected:
            self._logger.info(
                "Recuperando %d assinatura(s) pendente(s) da carteira %s…",
                len(collected), wallet_address[:8],
            )
        for item in reversed(collected):
            if stop_event.is_set():
                return
            signature = item["signature"]
            expected_previous_signature = self.event_store.get_checkpoint(wallet_address)
            if expected_previous_signature is None:
                raise RuntimeError("Checkpoint desapareceu durante o backfill; recuperação interrompida.")
            if item.get("err") is not None:
                # Falha on-chain é um resultado conhecido, não uma lacuna de dados.
                self.event_store.save_observation(
                    wallet_address,
                    signature,
                    None,
                    [],
                    parse_status="failed_on_chain",
                    parser_version=PARSER_VERSION,
                    advance_checkpoint=False,
                    slot=item.get("slot"),
                )
                self.event_store.mark_processed(
                    wallet_address, signature, advance_checkpoint=False
                )
                failed_slot = item.get("slot")
                if isinstance(failed_slot, bool) or not isinstance(failed_slot, int) or failed_slot < 0:
                    raise RuntimeError(
                        "Backfill recebeu slot inválido para transação falhada; checkpoint preservado."
                    )
                self.event_store.advance_checkpoint_in_order(
                    wallet_address,
                    signature,
                    failed_slot,
                    expected_previous_signature=expected_previous_signature,
                )
                continue
            if not await self._collect_transaction(
                wallet_address,
                signature,
                stop_event,
                advance_checkpoint=False,
            ):
                raise RuntimeError(
                    "Backfill pausado: uma transação ainda não pôde ser processada; cursor não avançado."
                )
            transaction_slot = item.get("slot")
            if isinstance(transaction_slot, bool) or not isinstance(transaction_slot, int) or transaction_slot < 0:
                raise RuntimeError(
                    "Backfill recebeu slot inválido após processar transação; checkpoint preservado."
                )
            self.event_store.advance_checkpoint_in_order(
                wallet_address,
                signature,
                transaction_slot,
                expected_previous_signature=expected_previous_signature,
            )

    async def _receive_or_stop(self, websocket: Any, stop_event: asyncio.Event) -> Any:
        receive_task = asyncio.create_task(websocket.recv())
        stop_task = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            {receive_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if stop_task in done and stop_event.is_set():
            return None
        return receive_task.result()

    async def _wait_or_stop(self, stop_event: asyncio.Event, delay: float) -> bool:
        if stop_event.is_set():
            return True
        sleep_task = asyncio.create_task(self._sleep(delay))
        stop_task = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            {sleep_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        return stop_task in done