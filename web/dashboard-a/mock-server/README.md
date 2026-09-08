# Mock SatyaCheck WebSocket server

A fake local server standing in for the real backend, which does not exist
yet anywhere in this repo. Emits `AppMessage` JSON matching
`contracts/risk.py` exactly. Never used against a real backend.

## Run

```
node mock-server/server.mjs [--port=8787] [--scenario=<name>] [--tick-ms=1000]
```

Scenarios: `genuine-call` (stays low), `cloned-voice` (climbs through all
four bands, ends with a full evidence payload), `degraded-clone` (wobbling
score, degraded checks, low confidence), `all-levels-sweep` (default: fast
deterministic cycle through all four `RiskLevel` values).

## Dump one sample message, no server needed

```
node mock-server/server.mjs --dump=session_start
node mock-server/server.mjs --dump=risk_update
node mock-server/server.mjs --dump=call_ended
```

Used for the contract cross-check in the dashboard README: pipe the output
to a file and validate it against the real Pydantic model with
`RiskUpdate.model_validate_json(...)` (or `SessionStart`/`CallEnded`) from
the repo root.
