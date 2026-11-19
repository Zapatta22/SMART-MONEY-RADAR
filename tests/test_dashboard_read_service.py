"""Testes do serviço de leitura do resumo do painel."""

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

from smart_money_radar.services.dashboard_read import DashboardReadService
from smart_money_radar.services.reconciliation_diagnostics import (
    ReconciliationDiagnosticsService,
)


class DashboardReadServiceTests(unittest.TestCase):
    def test_overview_composes_persisted_data_as_serializable_read_only_payload(self):
        store = Mock()
        report = {
            "total_attempts": 2,
            "statuses": {"MATCHED": 1, "INCOMPLETE": 1,
                         "AMBIGUOUS": 0, "UNRESOLVED": 0},
            "top_reasons": [],
            "pending_transactions_count": 0,
            "pending_transactions": [],
        }
        store.get_reconciliation_diagnostics.return_value = report
        store.storage_stats.return_value = {
            "observed_transactions": 2, "database_bytes": 4096,
        }
        store.get_events.return_value = [Mock(
            wallet_address="wallet-a",
            signature="sig-a",
            occurred_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
            token_mint="mint-a",
            direction="BUY",
            amount=Decimal("1.2500"),
        )]

        service = DashboardReadService(store)
        result = service.get_overview(wallet_address="wallet-a")

        self.assertEqual(result["mode"], "read_only")
        self.assertEqual(result["wallet_address"], "wallet-a")
        self.assertEqual(result["storage"]["database_bytes"], 4096)
        self.assertEqual(result["reconciliation"], report)
        self.assertEqual(result["recent_events"][0]["occurred_at"],
                         "2026-11-18T00:00:00+00:00")
        self.assertEqual(result["recent_events"][0]["amount"], "1.2500")
        store.get_reconciliation_diagnostics.assert_called_once_with(
            wallet_address="wallet-a",
            since=None,
            until=None,
            top_reasons_limit=10,
        )
        store.storage_stats.assert_called_once_with()
        store.get_events.assert_called_once_with(
            wallet_address="wallet-a", limit=20
        )

    def test_uses_injected_diagnostics_service(self):
        store = Mock()
        diagnostics = Mock(spec=ReconciliationDiagnosticsService)
        diagnostics.get_report.return_value = {"total_attempts": 0}
        store.storage_stats.return_value = {}
        store.get_events.return_value = []

        result = DashboardReadService(store, diagnostics).get_overview()

        self.assertEqual(result["reconciliation"], {"total_attempts": 0})
        diagnostics.get_report.assert_called_once_with(wallet_address=None)

    def test_no_network_or_mutation_methods_are_exposed(self):
        service = DashboardReadService(Mock())
        self.assertFalse(hasattr(service, "submit_transaction"))
        self.assertFalse(hasattr(service, "save_observation"))
        self.assertFalse(hasattr(service, "mark_processed"))


if __name__ == "__main__":
    unittest.main()
