# WebRTC Acquisition & Signalling Server (R3 Component)

This directory (`acquisitions/webrtc/`) implements the WebRTC P2P acquisition path for real-time audio analysis. It acts as a pure signalling broker and WebSocket audio ingest server, delivering raw audio streams to `AudioStreamConsumer` from `contracts/acquisition.py`.

---

## Architecture & Transport Boundary

```text
Phone A (Caller) ──(WebRTC P2P Audio)──► Phone B (Callee)
       │                                     │ (Taps remote audio track)
       │                                     ▼
       │ WebSocket (Port 8766)     WebSocket (Port 8767)
       │                           (JSON Handshake + Opus Frames)
       ▼                                     ▼
Signalling Server                      Audio Ingest Server
(signalling.py)                        (adapter.py)
                                             │
                                             ▼
                                    AudioStreamConsumer
                                   (Stage 02 Ingestion)
```

---

## File Structure

| File | Purpose |
|---|---|
| `__init__.py` | Package exports (`WebRTCAdapter`, `SignallingServer`). |
| `adapter.py` | `WebRTCAdapter` implementing WebSocket audio ingest server on port 8767. |
| `signalling.py` | Standalone async WebSocket P2P signalling broker (`dial`, `ringing`, `incoming_call`, `accept`, `answer`, `ice`, `hangup`, `call_ended`). |
| `contracts_shim.py` | Fallback contracts shim enabling isolated testing and standalone execution. |
| `test_webrtc.py` | Unit test suite covering protocol conformance, audio ingest, signalling broker, and AST transport invariant. |
| `client.html` | Browser test client supporting Caller (Phone A) and Receiver (Phone B) roles. |
| `FRONTEND_INTEGRATION.md` | Mobile frontend integration guide for React Native developers. |

---

## Quick Start / Running the Backend Services

To run the WebRTC acquisition layer for testing or demo:

```bash
# 1. Run the Signalling Broker (Port 8766)
python -m acquisitions.webrtc.signalling --host 0.0.0.0 --port 8766

# 2. Run the Audio Ingest Server (Port 8767)
python -m acquisitions.webrtc.adapter --host 0.0.0.0 --port 8767
```

---

## Running Unit Tests

```bash
python -m pytest acquisitions/webrtc/test_webrtc.py -v
```
