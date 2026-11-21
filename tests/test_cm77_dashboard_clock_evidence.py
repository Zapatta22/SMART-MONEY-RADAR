"""CM77: untrusted supervisor clock evidence must fail closed."""
import unittest
from datetime import datetime, timedelta, timezone

from smart_money_radar.services.dashboard_read import DashboardReadService


class DashboardSupervisorClockTests(unittest.TestCase):
    def test_active_lease_without_expiry_is_not_trusted(self):
        status = {"status": "ACTIVE", "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                  "expires_at": None, "alerts": []}
        result = DashboardReadService._supervisor_history(status)
        self.assertEqual(result["integrity"], "CONFLICTED")
        self.assertEqual(result["availability"], "UNAVAILABLE")
        self.assertFalse(result["live_authorized"])

    def test_future_heartbeat_is_not_trusted(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        status = {"status": "ACTIVE", "last_heartbeat": future.isoformat(),
                  "expires_at": (future + timedelta(minutes=1)).isoformat(), "alerts": []}
        result = DashboardReadService._supervisor_history(status)
        self.assertEqual(result["watchdog_state"], "INTEGRITY_CONFLICT")
        self.assertEqual(result["recovery_history"], [])
        self.assertFalse(result["execution_enabled"])


if __name__ == "__main__":
    unittest.main()
