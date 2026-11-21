"""Serviço de leitura para alimentar o resumo do futuro painel do SMR."""

from datetime import datetime
from decimal import Decimal

from smart_money_radar.services.reconciliation_diagnostics import (
    ReconciliationDiagnosticsService,
)
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.radar_event_bridge import read_archived_radar_events


class DashboardReadService:
    """Compõe dados locais já persistidos; não consulta rede nem altera estado."""

    def __init__(
        self,
        event_store: SQLiteEventStore,
        diagnostics: ReconciliationDiagnosticsService | None = None,
    ) -> None:
        self._event_store = event_store
        self._diagnostics = diagnostics or ReconciliationDiagnosticsService(event_store)

    @staticmethod
    def _json_value(value):
        if isinstance(value, (datetime,)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, tuple):
            return [DashboardReadService._json_value(item) for item in value]
        if isinstance(value, list):
            return [DashboardReadService._json_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): DashboardReadService._json_value(item)
                    for key, item in value.items()}
        return value

    def get_overview(self, *, wallet_address: str | None = None) -> dict:
        """Retorna resumo de persistência e reconciliação em formato serializável."""
        report = self._diagnostics.get_report(wallet_address=wallet_address)
        storage = self._event_store.storage_stats()
        recent_events = self._event_store.get_events(
            wallet_address=wallet_address, limit=20
        )
        events = [{
            "wallet_address": event.wallet_address,
            "signature": event.signature,
            "occurred_at": self._json_value(event.occurred_at),
            "token_mint": event.token_mint,
            "direction": event.direction,
            "amount": self._json_value(event.amount),
        } for event in recent_events]
        radar_events = read_archived_radar_events(self._event_store, limit=20)
        return {
            "mode": "read_only",
            "wallet_address": wallet_address,
            "storage": self._json_value(storage),
            "reconciliation": self._json_value(report),
            "recent_events": events,
            "radar_events": self._json_value(radar_events),
            # Separate radar channels are observational until independently
            # attested evidence is supplied. Database events do not prove
            # launch detection or Smart Money signal completeness.
            "radars": {
                name: {
                    "name": name, "status": "UNKNOWN",
                    "evidence_coverage": "UNKNOWN",
                    "operational_authorized": False,
                    "paper_modes": {
                        "immediate": "BLOCKED", "confirmed": "BLOCKED",
                    },
                } for name in ("launch", "smart_money")
            },
        }
