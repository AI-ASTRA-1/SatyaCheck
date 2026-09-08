# WebRTC Integration Guide (Frontend / Mobile App Handover)

This guide details how the mobile frontend app (React Native / `react-native-webrtc`) integrates with the SatyaCheck WebRTC backend architecture.

---

## 1. System Architecture Overview

The system uses **three distinct WebSocket connections** hosted on the backend server IP (`ws://<SERVER_IP>`):

```text
               +----------------------------------+
               |  Signalling Broker (Port 8766)   |
               +----------------------------------+
                   ^                          ^
   1. dial/sdpOffer|                          |3. accept/sdpAnswer
                   v                          v
             +----------+   WebRTC P2P Call  +----------+
             | Phone A  |====================| Phone B  |
             | (Caller) |    (Direct RTP)    | (Callee) |
             +----------+                    +----------+
                                                  |
                                    4. Taps incoming audio track &
                                       streams binary Opus frames
                                                  v
                                      +------------------------+
                                      | Audio Ingest (Port 8767)|
                                      +------------------------+
                                                  |
                                                  v
                                      +------------------------+
                                      | SatyaCheck AI Pipeline |
                                      +------------------------+
                                                  |
                                     5. RiskUpdates (Port 8765)
                                                  v
                                      +------------------------+
                                      | Phone B Overlay UI     |
                                      +------------------------+
```

---

## 2. Integration Steps for Phone A (Caller)

### Step A1: Connect to Signalling Broker
Open a WebSocket to `ws://<SERVER_IP>:8766`.

### Step A2: Initiate Dial
1. Acquire mic audio stream via `getUserMedia({ audio: true })` or `react-native-webrtc`.
2. Create an `RTCPeerConnection`.
3. Add local audio track to the peer connection.
4. Create SDP offer (`pc.createOffer()`) and set local description (`pc.setLocalDescription(offer)`).
5. Send `dial` payload over Signalling WS:
   ```json
   {
     "type": "dial",
     "call_id": "call_12345",
     "sdp": "v=0\r\no=- ..."
   }
   ```

### Step A3: Handle Signalling Messages
- **`ringing`**: Call is ringing on callee's device. Show calling UI.
  ```json
  { "type": "ringing", "call_id": "call_12345" }
  ```
- **`answer`**: Received SDP Answer from Phone B. Apply remote description:
  ```json
  { "type": "answer", "sdp": "v=0\r\no=- ..." }
  ```
  Run: `pc.setRemoteDescription(new RTCSessionDescription({ type: "answer", sdp: msg.sdp }))`.
- **`ice`**: Remote ICE candidate received from Phone B:
  ```json
  {
    "type": "ice",
    "call_id": "call_12345",
    "candidate": { "candidate": "...", "sdpMid": "0", "sdpMLineIndex": 0 }
  }
  ```
  Run: `pc.addIceCandidate(new RTCIceCandidate(msg.candidate))`.
- Send local ICE candidates to server:
  ```json
  {
    "type": "ice",
    "call_id": "call_12345",
    "candidate": event.candidate
  }
  ```

### Step A4: Hang Up
Send `hangup` message:
```json
{ "type": "hangup", "call_id": "call_12345" }
```

---

## 3. Integration Steps for Phone B (Receiver / Callee)

### Step B1: Connect to Signalling Broker & Listen
Open a WebSocket to `ws://<SERVER_IP>:8766`.

### Step B2: Accept Incoming Call
When server sends `incoming_call`:
```json
{
  "type": "incoming_call",
  "call_id": "call_12345",
  "sdp": "v=0\r\no=- ..."
}
```
1. Create `RTCPeerConnection`.
2. Set remote description: `pc.setRemoteDescription(new RTCSessionDescription({ type: "offer", sdp: msg.sdp }))`.
3. Create SDP Answer (`pc.createAnswer()`) and set local description (`pc.setLocalDescription(answer)`).
4. Send `accept` payload over Signalling WS:
   ```json
   {
     "type": "accept",
     "call_id": "call_12345",
     "sdp": answer.sdp
   }
   ```

### Step B3: Tap Remote Audio & Stream to SatyaCheck Backend (Port 8767)
When the WebRTC remote audio track arrives (`pc.ontrack`):
1. Connect a second WebSocket to `ws://<SERVER_IP>:8767`.
2. **Send JSON Handshake** (text frame) as the first message:
   ```json
   {
     "call_id": "call_12345",
     "codec": "opus",
     "sample_rate": 48000,
     "channels": 1
   }
   ```
3. Forward raw audio packets (Opus or PCM) as **binary WebSocket frames** continuously to `ws://<SERVER_IP>:8767`.

### Step B4: Listen for Real-Time Risk Updates (Port 8765)
Connect the overlay UI to `ws://<SERVER_IP>:8765` (`SessionStart`, `RiskUpdate`, `CallEnded`).

---

## 4. Port Reference Table

| Port | Service | Connection Type | Description |
|---|---|---|---|
| `8766` | Signalling Broker | JSON WebSocket | Exchanging P2P WebRTC SDP offers/answers & ICE candidates |
| `8767` | Audio Ingest | JSON Handshake + Binary WS | Phone B streams tapped remote Opus audio frames for AI analysis |
| `8765` | App Messages | JSON WebSocket | Backend streams real-time `RiskUpdate` scores to overlay UI |
