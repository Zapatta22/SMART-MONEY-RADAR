import unittest
from datetime import datetime, timezone
from decimal import Decimal

from smart_money_radar.analysis.metrics import count_events_by_token
from smart_money_radar.domain.models import ActivityEvent


class CountEventsByTokenTests(unittest.TestCase):
    def test_counts_events_for_each_token_mint(self) -> None:
        observed_at = datetime(2026, 11, 6, tzinfo=timezone.utc)
        events = [
            ActivityEvent("wallet-a", "sig-1", observed_at, "mint-b", "in", Decimal("1")),
            ActivityEvent("wallet-a", "sig-2", observed_at, "mint-a", "out", Decimal("2")),
            ActivityEvent("wallet-a", "sig-3", observed_at, "mint-b", "out", Decimal("3")),
        ]

        self.assertEqual(
            count_events_by_token(events),
            {"mint-a": 1, "mint-b": 2},
        )


if __name__ == "__main__":
    unittest.main()