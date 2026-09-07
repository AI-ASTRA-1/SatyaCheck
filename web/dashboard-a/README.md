# Web Dashboard A

Independent fallback web dashboard for SATYACHECK (SIH 2026 SIH26104).
Builds against `contracts/risk.py` with an internal mock WebSocket server.
See [roles/R5.md](../../roles/R5.md) for the role specification.

---

## Capabilities

1. **Live Risk View:**
   - Real-time continuous score gauge (0 to 100).
   - Renders `RiskLevel` directly (`low`, `medium`, `high`, `critical`) without computing score bands in client code.
   - Live verdict indicator (`genuine`, `synthetic`, `unknown`).
   - Signal confidence meter (0 to 100%).
   - Parallel AI check breakdown across all 4 checks:
     - Machine Fingerprints (XLS-R + AASIST)
     - Speaker Identity (ECAPA-TDNN)
     - Rhythm & Pitch (openSMILE)
     - Script Analysis (STT + LLM)
   - Triggered evidence reason codes with human-readable tags and severity styles.
   - Stream metadata tracking (`stream_id`, `call_id`, sequence ticks, timestamps).

2. **Alert History & Evidence Record:**
   - Chronological scrollable feed of all session events and scoring updates.
   - Stage 07 call conclusion summary displaying duration, final verdict, final score, `alert_fingerprint` (SHA-256), off-ledger `merkle_root`, and `sealed_record_id`.

3. **Connection State & Graceful Degradation:**
   - Handles `session_start`, `risk_update`, and `call_ended` discriminated union messages.
   - Clear disconnected banner and visual state reset upon disconnect (never freezes on last score).
   - Auto-reconnect polling.

---

## Running the Mock Server & Dashboard

### 1. Start the Server

Runs the mock WebSocket server on `ws://127.0.0.1:8765` and serves the web UI on `http://127.0.0.1:8080`:

```bash
python web/dashboard-a/mock_server.py
```

### 2. View in Browser

Open `http://127.0.0.1:8080` in any web browser, or open `web/dashboard-a/index.html` directly.

---

## Simulated Scenarios

The mock server loops through three realistic call scenarios:

1. **Scenario 1: Genuine Indian-Accented Call:** Score stays low (`score <= 15`, `fingerprint_genuine`, `prosody_normal`).
2. **Scenario 2: AI Voice Clone Impersonation Attack:** Early ticks accumulate audio, then score spikes to High/Critical (`score 76-96`, `fingerprint_synthetic`, `prosody_anomaly`, `script_risk_high`) and seals an alert record.
3. **Scenario 3: Badly Degraded Clone:** Noisy audio channel causing degraded AI checks (`degraded_check`, score wobbling).

---

## Contract Verification Tests

Run the test suite to verify that all emitted messages strictly adhere to `contracts.risk.AppMessage`:

```bash
python -m pytest web/dashboard-a/test_mock_server.py -q
```
