# WebRTC Acquisition & Signalling Server (R3 Component)

This directory (`acquisitions/webrtc/`) implements the WebRTC acquisition path for real-time audio streaming. It is designed as a drop-in replacement for the Exotel telephony path at the acquisition boundary, terminating strictly at `AudioStreamConsumer` from `contracts/acquisition.py`.

---

## Architecture & Transport Boundary

```text
Audio Source (Browser / App / Test Script)
       │
       │ WebSocket (ws://host:8766)
       ▼
Signalling Server (acquisitions/webrtc/signalling.py)
       │
       │ WebRTC Peer Connection (aiortc: RTP/SRTP Opus audio)
       ▼
WebRTCAdapter.connect() (acquisitions/webrtc/adapter.py)
       │
       │ on_open(StreamOpen) ──► on_chunk(AudioChunk)* ──► on_close(StreamClose)
       ▼
AudioStreamConsumer (Stage 02 Ingestion)
```

### Strict Boundary Rules:
- **Zero cross-boundary imports**: `acquisitions/webrtc/` does NOT import or touch `backend/`, `ml/`, `app/`, `tests/`, or `docs/`.
- **Approved Imports**: Only Python standard libraries, `aiortc`, `websockets`, and `contracts.acquisition` are permitted.
- **Contract Compliance**: All emitted events strictly follow the `StreamOpen`, `AudioChunk`, and `StreamClose` schemas.

---

## File Structure

| File | Purpose |
|---|---|
| `__init__.py` | Package exports (`WebRTCAdapter`, `SignallingServer`, schemas). |
| `adapter.py` | `WebRTCAdapter` implementing `AudioStreamAdapter` via `aiortc`. |
| `signalling.py` | Standalone async WebSocket signalling server (`offer`, `answer`, `ice`, `session_id`, `error`). |
| `contracts_shim.py` | Fallback contracts shim enabling isolated testing and standalone execution. |
| `test_webrtc.py` | Unit test suite covering protocol conformance, frame monotonicity, and AST transport invariant. |
| `README.md` | Documentation and running instructions. |

---

## Installation & Setup

Install the required WebRTC transport packages:

```bash
pip install aiortc websockets
```

---

## Running the Signalling Server

Run the standalone signalling server:

```bash
python -m acquisitions.webrtc.signalling --host 0.0.0.0 --port 8766
```

Options:
- `--host`: Bind host (default: `0.0.0.0`)
- `--port`: WebSocket port (default: `8766`)
- `--log-level`: Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`)

When running in standalone mode, the server initializes a default `WebRTCAdapter` with a logger consumer that outputs chunk sequences and byte statistics.

---

## Connecting a Client (Browser Test Client)

Save the following minimal HTML as `client.html` and open it in a modern browser (Chrome, Firefox, Safari) to stream microphone audio to the signalling server:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>WebRTC Audio Stream Test Client</title>
</head>
<body style="font-family: sans-serif; padding: 2rem;">
  <h2>WebRTC Audio Streaming Test</h2>
  <button id="startBtn" onclick="startStream()">Start Microphone Stream</button>
  <button id="stopBtn" onclick="stopStream()" disabled>Stop Stream</button>
  <p id="status">Status: Idle</p>

  <script>
    let ws, pc, localStream;

    async function startStream() {
      const status = document.getElementById("status");
      status.innerText = "Status: Connecting WebSocket...";

      ws = new WebSocket("ws://localhost:8766");

      ws.onopen = async () => {
        status.innerText = "Status: Acquiring microphone...";
        localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });

        pc = new RTCPeerConnection();
        localStream.getTracks().forEach(track => pc.addTrack(track, localStream));

        pc.onicecandidate = (event) => {
          if (event.candidate) {
            ws.send(JSON.stringify({ type: "ice", candidate: event.candidate }));
          }
        };

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        status.innerText = "Status: Sending SDP offer...";
        ws.send(JSON.stringify({
          type: "offer",
          call_id: "demo_call_" + Date.now(),
          sdp: offer.sdp
        }));
      };

      ws.onmessage = async (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "session_id") {
          console.log("Assigned Stream ID:", msg.stream_id);
        } else if (msg.type === "answer") {
          await pc.setRemoteDescription(new RTCSessionDescription(msg));
          status.innerText = "Status: Audio streaming active!";
          document.getElementById("startBtn").disabled = true;
          document.getElementById("stopBtn").disabled = false;
        } else if (msg.type === "error") {
          status.innerText = "Error: " + msg.reason;
        }
      };
    }

    function stopStream() {
      if (pc) pc.close();
      if (ws) ws.close();
      if (localStream) localStream.getTracks().forEach(t => t.stop());
      document.getElementById("status").innerText = "Status: Stopped";
      document.getElementById("startBtn").disabled = false;
      document.getElementById("stopBtn").disabled = true;
    }
  </script>
</body>
</html>
```

---

## Verification & Testing

Run the test suite:

```bash
python -m unittest acquisitions/webrtc/test_webrtc.py -v
```

The test suite validates:
1. **Protocol Compliance**: `WebRTCAdapter` implements `AudioStreamAdapter` and invokes callbacks in strict `on_open` &rarr; `on_chunk`* &rarr; `on_close` order.
2. **Frame Monotonicity**: Verifies consistent `stream_id`, sequence strictly starting from 0 without gaps, and `transport == "webrtc"` on every frame.
3. **AST Transport Invariant**: Parses all Python files in `acquisitions/webrtc/` and verifies zero imports from `backend/`, `ml/`, `app/`, `tests/`, or `docs/`.
