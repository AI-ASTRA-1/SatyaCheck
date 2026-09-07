# WebRTC Acquisition Integration Guide (Frontend Handover)

Hey! Here is the complete integration plan for the WebRTC acquisition backend path that was just built (`acquisitions/webrtc/`).

---

## 1. Quick Summary: The "Two Independent Connections" Architecture

The system uses **two independent connections**. Your app does **not** need complex WebRTC audio-pipeline modifications:

```text
1. Phone (SATYACHECK App UI / Overlay)
   └──► ws://BACKEND:8765 (AppMessage: SessionStart, RiskUpdate, CallEnded)
        * Drives the overlay UI via useOverlay() -> OverlayService

2. Audio Source (Browser / WebRTC Test Client / Laptop)
   └──► ws://SIGNALLING:8766 (JSON Signalling: offer/answer/ICE)
        └──► WebRTC Peer Connection (aiortc audio ingestion)
```

- **The Main App (`app/`)**: Keeps listening for `AppMessage` over `ws://BACKEND:8765`. It does not handle RTP audio packets.
- **The Audio Streamer**: Connects to the WebRTC signalling server at `ws://SIGNALLING:8766` to stream the call audio.

---

## 2. What Changes on the Frontend App Side?

**Zero breaking changes.**

1. In `app/src/config.ts`:
   Ensure `WS_URL` points to the backend server (default `ws://<BACKEND_IP>:8765`).
2. The overlay continues consuming:
   - `SessionStart`
   - `RiskUpdate`
   - `CallEnded`

---

## 3. WebRTC Signalling Protocol (For the Audio Streamer)

If you are building or embedding the audio streaming client (or running `client.html`), this is the exact WebSocket protocol running on `ws://<SIGNALLING_IP>:8766`:

### Handshake Flow

```text
Audio Client                                Signalling Server (8766)
     │                                                 │
     │─── 1. {"type": "offer", "call_id", "sdp"} ─────►│
     │                                                 │
     │◄── 2. {"type": "session_id", "stream_id"} ──────│
     │◄── 3. {"type": "answer", "sdp"} ────────────────│
     │                                                 │
     │─── 4. {"type": "ice", "candidate"} ────────────►│ (Optional trickle ICE)
     │                                                 │
     │═════════ RTP Audio Stream (Opus/PCM) ══════════►│ aiortc Ingestion
```

### Signalling Payloads (JSON over WebSocket)

#### Client &rarr; Server: SDP Offer
```json
{
  "type": "offer",
  "call_id": "call_12345",
  "sdp": "v=0\r\no=- ..."
}
```

#### Server &rarr; Client: Session Acknowledgement
```json
{
  "type": "session_id",
  "stream_id": "stream_9f3b...",
  "call_id": "call_12345"
}
```

#### Server &rarr; Client: SDP Answer
```json
{
  "type": "answer",
  "sdp": "v=0\r\no=- ..."
}
```

#### Client &harr; Server: ICE Candidates (Optional)
```json
{
  "type": "ice",
  "candidate": {
    "candidate": "candidate:...",
    "sdpMid": "0",
    "sdpMLineIndex": 0
  }
}
```

---

## 4. Ready-to-Use Frontend Streaming Code Snippet

You can drop this helper function into any web view, browser page, or test interface:

```javascript
let ws, pc, localStream;

async function startWebRTCStream(signallingUrl = "ws://localhost:8766", callId = "call_" + Date.now()) {
  ws = new WebSocket(signallingUrl);

  ws.onopen = async () => {
    // 1. Capture microphone audio
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });

    // 2. Setup RTCPeerConnection
    pc = new RTCPeerConnection();
    localStream.getTracks().forEach(track => pc.addTrack(track, localStream));

    pc.onicecandidate = (event) => {
      if (event.candidate) {
        ws.send(JSON.stringify({ type: "ice", candidate: event.candidate }));
      }
    };

    // 3. Create and send offer
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    ws.send(JSON.stringify({
      type: "offer",
      call_id: callId,
      sdp: offer.sdp
    }));
  };

  ws.onmessage = async (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "session_id") {
      console.log("Assigned stream_id:", data.stream_id);
    } else if (data.type === "answer") {
      await pc.setRemoteDescription(new RTCSessionDescription({ type: "answer", sdp: data.sdp }));
      console.log("WebRTC Audio Streaming Active!");
    } else if (data.type === "error") {
      console.error("Signalling error:", data.reason);
    }
  };
}

function stopWebRTCStream() {
  if (pc) pc.close();
  if (ws) ws.close();
  if (localStream) localStream.getTracks().forEach(track => track.stop());
  console.log("WebRTC Audio Streaming Stopped.");
}
```

Or simply open [`acquisitions/webrtc/client.html`](file:///c:/Users/bhara/Downloads/webrtcsih/acquisitions/webrtc/client.html) directly in a browser to test!

---

## 5. End-to-End Demo Step-by-Step

For our live demo or hackathon presentation:
1. **Start Signalling Server**:
   ```bash
   python -m acquisitions.webrtc.signalling --port 8766
   ```
2. **Start Backend / Risk Engine**:
   Runs on port `8765` broadcasting `AppMessage` updates.
3. **Start the Audio Stream**:
   - Open `client.html` on a laptop or phone browser.
   - Click "Start Streaming" to begin streaming audio.
4. **Watch the App Overlay**:
   - The app receives `RiskUpdate` notifications in real-time as the audio is ingested and evaluated.
