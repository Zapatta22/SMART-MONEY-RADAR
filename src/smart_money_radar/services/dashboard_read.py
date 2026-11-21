"""Serviço de leitura para alimentar o resumo do futuro painel do SMR."""

from datetime import datetime
from decimal import Decimal

from smart_money_radar.services.reconciliation_diagnostics import (
    ReconciliationDiagnosticsService,
)
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.radar_event_bridge import read_archived_radar_events
from smart_money_radar.services.radar_intelligence import read_intelligence_reports
from smart_money_radar.services.synthetic_paper_ledger import read_synthetic_paper, paper_preflight
from smart_money_radar.services.synthetic_capital import read_capital_accounts
from smart_money_radar.services.operational_controls import read_operational_status
from smart_money_radar.services.wallet_discovery import read_wallet_snapshots


class DashboardReadService:
    """Compõe dados locais já persistidos; não consulta rede nem altera estado."""

    def __init__(
        self,
        event_store: SQLiteEventStore,
        diagnostics: ReconciliationDiagnosticsService | None = None,
        *, intelligence_scopes: dict | None = None,
    ) -> None:
        self._event_store = event_store
        self._intelligence_scopes = dict(intelligence_scopes or {})
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

    @staticmethod
    def _last_archived_event_at(items: list[dict]) -> str | None:
        """Local archive timestamp, not a live collector heartbeat."""
        stamps = [datetime.fromisoformat(row["available_at"])
                  for row in items if row.get("available_at")]
        return max(stamps).isoformat() if stamps else None

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
        intelligence = read_intelligence_reports(self._event_store, radar_events, scopes=self._intelligence_scopes)
        return {
            "mode": "read_only",
            "wallet_address": wallet_address,
            "storage": self._json_value(storage),
            "reconciliation": self._json_value(report),
            "recent_events": events,
            "radar_events": self._json_value(radar_events),
            "radar_opportunities": self._json_value(intelligence),
            "synthetic_paper": read_synthetic_paper(self._event_store),
            "capital_accounts": read_capital_accounts(self._event_store),
            "operational_controls": read_operational_status(self._event_store),
            "wallet_discovery": read_wallet_snapshots(self._event_store,limit=1),
            "paper_preflight": {radar: [paper_preflight(d,kind="HISTORICAL_REPLAY")
                for d in decisions] for radar,decisions in intelligence.items()},
            # Separate radar channels are observational until independently
            # attested evidence is supplied. Database events do not prove
            # launch detection or Smart Money signal completeness.
            "radars": {
                name: {
                    "name": name, "status": "UNKNOWN",
                    "last_archived_event_at": self._last_archived_event_at(radar_events[name]),
                    "evidence_coverage": "UNKNOWN",
                    "operational_authorized": False,
                    "paper_modes": {
                        "immediate": "BLOCKED", "confirmed": "BLOCKED",
                    },
                } for name in ("launch", "smart_money")
            },
        }
