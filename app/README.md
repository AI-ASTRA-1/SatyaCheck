# SATYACHECK app (React Native + Expo)

Owner: React Native / Expo lead.

Placeholder in the contracts-only phase. The Expo scaffold and the overlay drawing
are that role's first coding task, against `docs/interfaces.md` and the RiskUpdate
via `contracts/risk.py`.

The app renders states, never thresholds: `risk_level` decides the overlay
(LOW none, MEDIUM amber chip, HIGH red overlay, CRITICAL red plus an action
prompt); it never computes a band from `score`. It must never block or modify the
call.

Node toolchain only; `app/` is excluded from the Python project.