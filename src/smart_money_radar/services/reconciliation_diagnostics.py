"""Serviço de aplicação somente leitura para diagnósticos de reconciliação."""

from smart_money_radar.storage.event_store import SQLiteEventStore


class ReconciliationDiagnosticsService:
    """Expõe consultas de auditoria sem permitir mutações no EventStore.

    A camada de apresentação/API deve depender deste serviço, não executar SQL
    nem acessar diretamente os detalhes internos do armazenamento.
    """

    def __init__(self, event_store: SQLiteEventStore) -> None:
        self._event_store = event_store

    def get_report(
        self,
        *,
        wallet_address: str | None = None,
        since: str | None = None,
        until: str | None = None,
        top_reasons_limit: int = 10,
    ) -> dict:
        """Retorna métricas, motivos recorrentes e transações pendentes."""
        return self._event_store.get_reconciliation_diagnostics(
            wallet_address=wallet_address,
            since=since,
            until=until,
            top_reasons_limit=top_reasons_limit,
        )

    def list_attempts(
        self,
        *,
        wallet_address: str | None = None,
        signature: str | None = None,
        operation_id: str | None = None,
        status: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Lista tentativas auditáveis com os filtros suportados pelo EventStore."""
        return self._event_store.query_swap_reconciliation_attempts(
            wallet_address=wallet_address,
            signature=signature,
            operation_id=operation_id,
            status=status,
            since=since,
            until=until,
            limit=limit,
        )
