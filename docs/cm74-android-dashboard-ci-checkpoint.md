# CM74 — Android dashboard lifecycle: CI checkpoint

Status: **offline CI approved; Android physical homologation pending**.

Branch: `codex/cm74-android-dashboard-lifecycle`; Draft PR #115.
Last validated functional/test commit: `0091ab6e1d3ace8114a2f19bfb621dc1cee0fb3e`.
GitHub Actions run: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44934834195 — success (Python 3.12 main suite and Python 3.14 evaluation).

## Delivered
- Detached loopback dashboard launcher using existing SQLite; no database creation/migration or trading.
- Fail-closed tests for missing and incompatible databases.
- Tests for active-PID duplicate prevention and stale-PID recovery.
- Existing GitHub CI tests on Python 3.12 and Python 3.14.
- Authenticated HTTP health probe requiring exact `read_only` response; token file and state permissions checked.
- Periodic local watchdog with exclusive lock and bounded failure budget.
- CM73 offline regression for exhausted worker restart budget before a conflicting lease snapshot; CI approved.

## Not yet proven
- Physical Termux/Android startup and process survival across app switching, Doze and reboot.
- Ownership verification of any HTTP listener already bound to port 8765.
- Physical concurrent-launch behavior under Termux (launcher and watchdog now use `flock` locks; Linux CI is not Android homologation).
- Full cross-component supervisor integration and verified automatic restart on a physical Android device.
- Live data capture or trading (not authorized).

Do not merge PR #115 or modify main/PR #111/PR #113. Keep CM39 blocked.
Global SMR progress estimate remains 58% pending physical homologation and supervisor integration.
