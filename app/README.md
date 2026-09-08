# SATYACHECK app (React Native + Expo)

Owner: React Native / Expo lead. Folder: `app/`. Do not edit outside this folder.

## What is built (Round 1)

| Item | Status |
|---|---|
| Fake WebSocket server | `dev-server/fake-ws-server.js` |
| TypeScript AppMessage types | `src/ws/types.ts` |
| WebSocket hook with state machine | `src/ws/useRiskSocket.ts` |
| Android SYSTEM_ALERT_WINDOW native module | `modules/overlay/` |
| Overlay control hook | `src/overlay/useOverlay.ts` |
| Main screen (scanning / live / ended states) | `src/screens/OverlayScreen.tsx` |
| WebRTC call screen (fallback calling UI) | `src/screens/CallScreen.tsx` |
| Alert history screen | `src/screens/AlertHistoryScreen.tsx` |
| Pristine light theme & colour tokens | `src/theme.ts` |


Round 2 items (not built, not in this folder): Family Vault enrolment UI, settings screen,
transcript warnings, payment blocking.

## Colour mapping

| risk_level | Colour | Behaviour |
|---|---|---|
| low | green `#22c55e` | subtle chip |
| medium | amber `#f59e0b` | chip |
| high | red `#ef4444` | overlay strip |
| critical | dark red `#b91c1c` | overlay strip + warning prompt |

The app renders `risk_level` as sent by the backend. It never computes a band from `score`.
Deployments override the mapping in backend policy config, not here.

## Running the fake server

```bash
# Terminal 1
cd app && npm install
npm run fake-server

# Terminal 2 (verify messages)
npx wscat -c ws://localhost:8765
```

Expected: `session_start` immediately, then `risk_update` every second for 35 s,
then `call_ended`.

## Building for a physical Android device

1. Set `DEV_MACHINE_IP` in `src/config.ts` to your machine's LAN IP.
2. Enable USB debugging on the phone.
3. From `app/`:

```bash
npx expo run:android
```

4. On first launch, grant "Draw over other apps" permission when prompted.
5. Start the fake server on your machine (same Wi-Fi network as the phone).
6. The overlay should appear over the dialler when a call is active.

## The overlay invariant

The native `OverlayService` uses `FLAG_NOT_FOCUSABLE + FLAG_NOT_TOUCH_MODAL`. All
touches pass through to call controls. The overlay is display-only; it never blocks,
mutes, or ends a call.

Disconnecting the WebSocket (`hideOverlay()`) clears the overlay immediately. A stale
score is never shown.

## WebSocket contract

AppMessage is a discriminated union on `kind`:

| kind | When | App action |
|---|---|---|
| `session_start` | Call begins | Show scanning indicator |
| `risk_update` | ~1/s while call is live | Update overlay, log tick |
| `call_ended` | Call ends | Show summary, add to history |

Full field list: `src/ws/types.ts` (mirrors `contracts/risk.py` exactly).

## Dependencies added

| Package | Why |
|---|---|
| `expo` + `react-native` | app framework |
| `expo-dev-client` | enables native modules in managed Expo |
| `react-native-safe-area-context` | safe area insets |
| `react-native-screens` | navigation screen optimisation |
| `ws` | fake server (Node.js, dev only) |
| `satyacheck-overlay` | local native module (app/modules/overlay/) |

No external overlay package -- the native module is hand-written inside `app/modules/overlay/`
using `expo-modules-core` only.