/**
 * WS_URL: address of the WebSocket server the app connects to.
 *
 * On a physical Android device "localhost" refers to the device itself,
 * not the dev machine. Set DEV_MACHINE_IP to your machine's LAN IP
 * (e.g. 192.168.1.42) and run the fake server on port 8765.
 *
 * Find your IP:  ipconfig  (Windows) -- look for "IPv4 Address" on your
 *                Wi-Fi adapter. The phone must be on the same network.
 */
const DEV_MACHINE_IP = "192.168.29.196"; // <-- set this to your machine's LAN IP
export const WS_URL = __DEV__
  ? `ws://${DEV_MACHINE_IP}:8765`
  : "wss://api.satyacheck.example"; // production URL: not built in Round 1

/**
 * WebRTC fallback path -- signalling server (friend's server).
 * Used only when both caller and receiver are on the SATYACHECK app.
 * Port 8766 is separate from WS_URL (port 8765) -- two independent connections.
 */
export const SIGNALLING_URL = __DEV__
  ? `ws://${DEV_MACHINE_IP}:8766`
  : "wss://signal.satyacheck.example"; // not built in Round 1

/**
 * WebRTC fallback path -- backend audio ingest.
 * Receiver app forwards caller's raw Opus frames here.
 * Confirm port 8767 with the WebRTC lead before the first integration test.
 */
export const AUDIO_INGEST_URL = __DEV__
  ? `ws://${DEV_MACHINE_IP}:8767`
  : "wss://ingest.satyacheck.example"; // not built in Round 1
