# CM74 — Android dashboard lifecycle: CI checkpoint

Status: **offline CI approved; Android physical homologation pending**.

Branch: `codex/cm74-android-dashboard-lifecycle`; Draft PR #115.
Last validated functional/test commit: `e5270eaf181160a9d24e5460e7abace4fd3d2c06`.
GitHub Actions run: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44933551733 — success.
Previous commits `bd9f173` and `b13310b` also had successful workflow runs.

## Delivered
- Detached loopback dashboard launcher using existing SQLite; no database creation/migration or trading.
- Fail-closed tests for missing and incompatible databases.
- Tests for active-PID duplicate prevention and stale-PID recovery.
- Existing GitHub CI tests on Python 3.12 and Python 3.14.

## Not yet proven
- Physical Termux/Android startup and process survival across app switching, Doze and reboot.
- Ownership verification of any HTTP listener already bound to port 8765.
- Race-safe exclusive launch under concurrent invocations; a PID file alone is not an atomic lock.
- Supervisor integration, persistent watchdog and verified automatic restart.
- Live data capture or trading (not authorized).

Do not merge PR #115 or modify main/PR #111/PR #113. Keep CM39 blocked.
Global SMR progress estimate remains 58% pending physical homologation and supervisor integration.
