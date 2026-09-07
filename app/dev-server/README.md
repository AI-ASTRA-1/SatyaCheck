# fake-ws-server

Development-only fake WebSocket server for the SATYACHECK app.

## What it emits

Connects a client and sends the exact `AppMessage` JSON schema
(`contracts/risk.py`): one `session_start`, then a `risk_update` every second
for 35 seconds (score arc: low -> medium -> high -> critical -> back down),
then a `call_ended`.

## Run

```bash
# from repo root
node app/dev-server/fake-ws-server.js
```

Server listens on `ws://localhost:8765`.

## Verify (second terminal)

```bash
npx wscat -c ws://localhost:8765
```

You should see `session_start` immediately, then `risk_update` lines each
second, then `call_ended` after ~35 s and the connection closes.

## Dependencies

Requires the `ws` package. Install once from `app/`:

```bash
cd app && npm install
```

Do not commit this server; it is a dev tool only.
