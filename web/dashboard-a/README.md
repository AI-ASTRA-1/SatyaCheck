# Web Dashboard A

Independent fallback web dashboard for SATYACHECK (SIH 2026 SIH26104).
Builds against `contracts/risk.py` with an internal mock WebSocket server.
See [roles/R5.md](../../roles/R5.md) for the role specification.

---

## Capabilities

1. **Live Risk View:**
   - Full-width continuous score gauge (0 to 100) and live session telemetry.
   - Renders `RiskLevel` directly (`low`, `medium`, `high`, `critical`) without computing score bands in client code.
   - Live verdict indicator (`genuine`, `synthetic`, `unknown`).
   - Signal confidence meter (0 to 100%).
   - Full-width parallel AI check breakdown across all 4 checks:
     - Machine Fingerprints (XLS-R + AASIST)
     - Speaker Identity (ECAPA-TDNN)
     - Rhythm & Pitch (openSMILE)
     - Script Analysis (STT + LLM)
   - Triggered evidence reason codes with human-readable tags and severity styles.
   - Stream metadata tracking (`stream_id`, `call_id`, sequence ticks, timestamps).

2. **Alert History & Evidence Record:**
   - Bottom dropdown lists for both Telemetry History and Call Concluded Summary.
   - Stage 07 call conclusion summary displaying duration, final verdict, final score, `alert_fingerprint` (SHA-256), off-ledger `merkle_root`, `root_published_at` timestamp, and `sealed_record_id`.
   - Chronological scrollable feed of all session events and scoring updates, including `evidence_refs` tracking.

3. **Connection State & Graceful Degradation:**
   - Handles `session_start`, `risk_update`, and `call_ended` discriminated union messages.
   - Validates `schema_version` ("1.0") and logs console warnings upon version mismatches.
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

Scenarios are triggered interactively from the dashboard toolbar (Genuine Call, Voice Clone Attack, Degraded Clone, Stop Stream). Auto-Repeat is off by default; enable it via the checkbox to loop continuously.

1. **Scenario 1: Genuine Indian-Accented Call:** Score stays low (`score <= 15`, `fingerprint_genuine`, `prosody_normal`).
2. **Scenario 2: AI Voice Clone Impersonation Attack:** Early ticks accumulate audio, then score spikes to High/Critical (`score 76-96`, `fingerprint_synthetic`, `prosody_anomaly`, `script_risk_high`) and seals an alert record.
3. **Scenario 3: Badly Degraded Clone:** Noisy audio channel causing degraded AI checks (`degraded_check`, score wobbling).

---

## Contract Verification & Assumptions

- **Check Status Contract Boundary:** The `RiskUpdate` contract provides `contributing_checks` and `degraded_checks`. Unlisted checks are marked as "Idle / Unknown" because the downstream contract does not distinguish between idle, failed, or skipped-for-insufficient-audio states.
- **Mock Simulator Control Channel:** The scenario toolbar triggers upstream WebSocket action messages (`play`, `stop`, `set_loop`) to `mock_server.py`. This upstream channel is a test harness convenience; the production contract in `contracts/risk.py` is downstream only (backend to app).
- **Evidence References & Anchors:** `evidence_refs` are displayed in telemetry history feed items; `root_published_at` is shown in the call conclusion card.
- **Schema Version Verification:** Messages are validated against `schema_version == "1.0"`.

Run the test suite to verify that all emitted messages strictly adhere to `contracts.risk.AppMessage`:

```bash
python -m pytest web/dashboard-a/test_mock_server.py -q
```

---

## Beyond the R5 spec

The scenario-trigger toolbar (Genuine / Attack / Degraded / Stop, with auto-loop toggle) is an extra added for demo convenience; the literal R5.md spec requires only a live risk view and a scrollable alert history.
