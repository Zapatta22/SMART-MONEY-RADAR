"""Testes do serviço de consulta de diagnósticos de reconciliação."""

import unittest
from unittest.mock import Mock

from smart_money_radar.services.reconciliation_diagnostics import (
    ReconciliationDiagnosticsService,
)


class ReconciliationDiagnosticsServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.service = ReconciliationDiagnosticsService(self.store)

    def test_get_report_delegates_filters_and_returns_store_result(self):
        expected = {
            "total_attempts": 3,
            "distinct_operations": 2,
            "distinct_signatures": 2,
            "statuses": {
                "MATCHED": 1,
                "INCOMPLETE": 1,
                "AMBIGUOUS": 0,
                "UNRESOLVED": 1,
            },
            "top_reasons": [],
            "pending_transactions_count": 0,
            "pending_transactions": [],
        }
        self.store.get_reconciliation_diagnostics.return_value = expected

        result = self.service.get_report(
            wallet_address="wallet-a",
            since="2026-11-18T00:00:00+00:00",
            until="2026-11-18T23:59:59+00:00",
            top_reasons_limit=5,
        )

        self.assertIs(result, expected)
        self.store.get_reconciliation_diagnostics.assert_called_once_with(
            wallet_address="wallet-a",
            since="2026-11-18T00:00:00+00:00",
            until="2026-11-18T23:59:59+00:00",
            top_reasons_limit=5,
        )

    def test_list_attempts_delegates_supported_filters(self):
        expected = [{"operation_id": "op-1", "status": "MATCHED"}]
        self.store.query_swap_reconciliation_attempts.return_value = expected

        result = self.service.list_attempts(
            wallet_address="wallet-a",
            signature="signature-a",
            operation_id="op-1",
            status="MATCHED",
            since="2026-11-18T00:00:00+00:00",
            until="2026-11-18T23:59:59+00:00",
            limit=25,
        )

        self.assertIs(result, expected)
        self.store.query_swap_reconciliation_attempts.assert_called_once_with(
            wallet_address="wallet-a",
            signature="signature-a",
            operation_id="op-1",
            status="MATCHED",
            since="2026-11-18T00:00:00+00:00",
            until="2026-11-18T23:59:59+00:00",
            limit=25,
        )

    def test_service_exposes_no_mutation_operations(self):
        self.assertFalse(hasattr(self.service, "save_observation"))
        self.assertFalse(hasattr(self.service, "save_swap_bundle"))
        self.assertFalse(hasattr(self.service, "mark_processed"))
        self.store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
