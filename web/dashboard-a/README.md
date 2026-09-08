# SatyaCheck Web Dashboard A

Extends `roles/R5.md`. Live risk view and alert history, against a fake
local WebSocket only. Never connects to a real backend (none exists yet).
This is a fallback surface: the RN/Expo app (`app/`) is primary.

## Run

```
npm install
npm run mock-server            # terminal A, ws://localhost:8787
npm run dev                    # terminal B, http://localhost:5174
```

Set `VITE_MOCK_WS_URL` (default `ws://localhost:8787`) if the mock server
runs on a different port. Mock server scenarios: `--scenario=genuine-call`,
`cloned-voice`, `degraded-clone`, `all-levels-sweep` (default). See
`mock-server/README.md`.

## Self-checks (from `roles/R5.md`)

1. Start the mock server, open the dashboard, confirm messages arrive and
   the live view updates roughly once a second.
2. Kill the mock server; confirm a clear disconnected banner appears, not a
   frozen score.
3. Contract cross-check, from the repo root:
   ```
   node web/dashboard-a/mock-server/server.mjs --dump=risk_update > /tmp/sample.json
   uv run python -c "from contracts.risk import RiskUpdate; RiskUpdate.model_validate_json(open('/tmp/sample.json').read()); print('valid')"
   ```
   Repeat for `--dump=session_start`/`SessionStart` and
   `--dump=call_ended`/`CallEnded`.
4. Run with `--scenario=all-levels-sweep`; confirm all four `RiskLevel`
   colors and labels render, each paired with an icon/label (never color
   alone).
5. `git status` / `git diff --stat`: only `web/dashboard-a/**` changed.

## Design discipline

`src/lib/riskLevelMeta.ts` is the only function allowed to map `risk_level`
to a color, icon, or label. The gauge's sweep angle is driven by `score`
(cosmetic only); its color is driven by `risk_level` only, never
interpolated from score. No per-check numeric confidence is shown or
invented; the wire contract (`contracts/checks.py`) carries only check
names (contributing/degraded) and reason codes on `RiskUpdate`, not
per-check floats.

## Stack and why

Vite + React + TypeScript + Tailwind v4, same design tokens as
`web/landing/` (duplicated, not shared, since a shared package would need a
folder outside the two owned here). `ws` powers `mock-server/server.mjs`
only, a plain Node script never bundled to the browser. No router (one
screen), no chart library (three hand-built SVG elements: gauge, sparkline,
history chips are enough), no state-management library, no GSAP (no
scroll-driven content here).

## Scope

Live risk view and alert history only, per `roles/R5.md`. No enrolment UI,
no settings. Does not touch `contracts/`, `backend/`, `ml/`,
`acquisitions/`, `app/`, `tests/`, `docs/`, `roles/`, or `web/dashboard-b/`.
