# WebRTC acquisition + signalling server: implementation plan

For your friend building the WebRTC fallback path (R3 role, folder `acquisitions/webrtc/`).

---

## The one-paragraph boundary

The WebRTC path is a drop-in replacement for the Exotel path at and only at the
acquisition boundary. Everything the friend builds terminates at `AudioStreamConsumer`
from `contracts/acquisition.py`. The backend, AI checks, risk engine, and the app
contract (`AppMessage`) do not change. The friend does not touch `backend/`, `ml/`,
`app/`, `contracts/`, `tests/`, or `docs/`.

---

## What the app already does (your side -- do not change)

```
app/ connects to ws://IP:8765 (fake server today, real backend tomorrow)
receives AppMessage: SessionStart, RiskUpdate, CallEnded
drives the overlay via useOverlay() -> OverlayService (native Android)
```

The app does NOT speak WebRTC. The app does NOT stream audio. That is the
acquisition layer's job, entirely in `acquisitions/webrtc/` and a signalling server.

---

## What the friend builds

```
acquisitions/webrtc/
  __init__.py
  adapter.py          # WebRTCAdapter implements AudioStreamAdapter
  signalling.py       # thin WebSocket signalling server (offer/answer/ICE)
  README.md           # how to run it, how to connect a browser/app test client
```

Plus optionally a standalone signalling server script (can live in `acquisitions/webrtc/`).

---

## Interface the friend MUST satisfy

From `contracts/acquisition.py` -- do not change these, they are the contract:

```python
class AudioStreamAdapter(Protocol):
    def connect(
        self,
        endpoint: str,
        *,
        on_open: Callable[[StreamOpen], None],
        on_chunk: Callable[[AudioChunk], None],
        on_close: Callable[[StreamClose], None],
    ) -> None: ...

class AudioStreamConsumer(Protocol):
    def on_open(self, open_msg: StreamOpen) -> None: ...
    def on_chunk(self, chunk: AudioChunk) -> None: ...
    def on_close(self, close_msg: StreamClose) -> None: ...
```

The WebRTC adapter calls the three callbacks in this exact order:
1. `on_open(StreamOpen)` -- once, before any audio
2. `on_chunk(AudioChunk)` -- once per 20 ms frame, for the life of the call
3. `on_close(StreamClose)` -- once, after the last frame

**That is the entire interface.** Stage 02 ingestion consumes these callbacks and
the adapter never talks to anything below stage 02.

---

## AudioChunk fields the WebRTC adapter must fill

From `contracts/acquisition.py AudioChunk`:

| Field | Value for WebRTC path |
|---|---|
| `stream_id` | unique per call leg, generated at `connect()` |
| `call_id` | passed in from the signalling handshake |
| `transport` | `Transport.WEBRTC` (the only place this value appears) |
| `codec` | `Codec.OPUS` (WebRTC standard) or `Codec.PCM_S16LE` if decoded before emit |
| `sample_rate` | 48000 for Opus (WebRTC default), or 16000 if decoded to PCM |
| `channels` | 1 (mono) |
| `frame_ms` | 20 (target; WebRTC Opus default ptime) |
| `sequence` | monotonic from 0, per stream |
| `payload` | raw encoded bytes from the RTP packet (Opus) or decoded PCM |
| `capture_timestamp` | RTP timestamp converted to wall clock |
| `received_at` | `datetime.utcnow()` at the moment the frame arrives |
| `rtp_ts` | the raw RTP timestamp (uint32); set to None if unavailable |
| `metadata` | `{"peer_id": "<webrtc peer id>"}` or empty dict |

> [!IMPORTANT]
> Stage 02 ingestion handles decoding Opus -> PCM. The adapter can emit raw Opus
> frames if it sets `codec=Codec.OPUS`. Emitting pre-decoded PCM is also fine
> (`codec=Codec.PCM_S16LE, sample_rate=16000`). Pick one and be consistent.

---

## StreamOpen fields

```python
StreamOpen(
    stream_id=stream_id,
    call_id=call_id,
    transport=Transport.WEBRTC,
    direction=CallDirection.INBOUND,   # or OUTBOUND
    caller_number=None,                # WebRTC path has no PSTN number
    callee_number=None,
    started_at=datetime.utcnow(),
    codec=Codec.OPUS,
    sample_rate=48000,
    channels=1,
    frame_ms=20,
    external_ref=peer_id,              # WebRTC peer connection id
)
```

---

## StreamClose fields

```python
StreamClose(
    stream_id=stream_id,
    call_id=call_id,
    ended_at=datetime.utcnow(),
    reason="completed",                # or "dropped" / "error"
    frames_received=frame_count,
    bytes_received=byte_count,
    dropped_frames=dropped_count,
)
```

---

## Signalling server design (friend builds this)

A minimal WebSocket signalling server. Purpose: broker the WebRTC offer/answer and
ICE candidates between the audio source (phone's browser or a test client) and the
backend peer connection.

```
audio source (browser / test client)
       |  ws://signalling:PORT
       v
  signalling server          <-- friend builds
       |  WebRTC peer connection (aiortc or similar)
       v
  WebRTCAdapter.connect()
       |  on_open / on_chunk / on_close callbacks
       v
  AudioStreamConsumer (stage 02 ingestion) -- not the friend's concern
```

### Signalling messages (JSON over WebSocket)

The friend defines these. Suggested minimal set:

| Direction | Message | Fields |
|---|---|---|
| client -> server | `offer` | `call_id`, `sdp` (SDP offer string) |
| server -> client | `answer` | `sdp` (SDP answer string) |
| either | `ice` | `candidate` (ICE candidate object) |
| server -> client | `session_id` | `stream_id`, `call_id` (echoed back so the adapter knows its ids) |
| server -> client | `error` | `reason` string |

The app does NOT speak this protocol. The audio source (phone browser, or a test
client on a laptop) speaks it. The app speaks only `AppMessage` WebSocket.

### The two connections in the demo

```
Phone (SATYACHECK app)
  --> ws://BACKEND:8765           AppMessage (RiskUpdate, etc.)

Phone browser / test laptop
  --> ws://SIGNALLING:PORT        signalling (offer/answer/ICE)
  ==> WebRTC peer connection  --> backend WebRTCAdapter --> AudioStreamConsumer
```

The two connections are independent. The app does not need to change for the WebRTC
path to work.

---

## Transport invariant -- the friend must not cross it

From `AGENTS.md` and `docs/interfaces.md` section 1:

- `acquisitions/webrtc/` may import `contracts.acquisition` and the WebRTC SDK only.
- It must NOT import `backend/`, `ml/`, or any type below stage 02.
- `backend/`, `ml/` must NOT import from `acquisitions/`.
- The existing test `tests/test_transport_invariant.py` enforces this with an AST walk.
  Run `uv run pytest tests/test_transport_invariant.py -q` after writing any code.

To verify manually:
```bash
# Should return nothing
grep -r "from acquisitions" backend/ ml/ --include="*.py"
grep -r "webrtc\|exotel" backend/ ml/ --include="*.py"
```

---

## Recommended Python libraries (friend asks before adding)

| Library | Purpose |
|---|---|
| `aiortc` | WebRTC peer connection in Python (MediaTrack -> audio frames) |
| `aiohttp` or `websockets` | signalling server WebSocket |

`aiortc` is the standard choice for server-side WebRTC in Python. It handles
Opus decoding natively so the adapter can emit either raw Opus or decoded PCM.

Per AGENTS.md: confirm with the backend lead (R2) before adding any new dependency.

---

## Self-check for the friend (from R3.md)

1. Write a test: imports `AudioStreamAdapter` and `AudioStreamConsumer` from
   `contracts/acquisition.py`, verifies the WebRTC adapter class satisfies both protocols.
2. Write a test: feeds 10 `AudioChunk`s through the adapter, verifies `stream_id` is
   consistent, `sequence` is monotonic, and `transport == "webrtc"` on every frame.
3. Run `uv run pytest tests/test_transport_invariant.py -q` -- must pass.
4. Verify `grep -r "from acquisitions" backend/ ml/` returns nothing.

---

## What the friend does NOT build

- Anything in `backend/`, `ml/`, `app/`, `contracts/`, `tests/`, `docs/`
- The `AppMessage` WebSocket (that is the backend response layer, stage 06)
- Any UI
- Any model or scoring logic

---

## Coordination point with the app

The app connects to the `AppMessage` WebSocket URL set in `app/src/config.ts`.
When the real backend exists, the friend's audio path feeds into it and the backend
sends `RiskUpdate` messages the app already consumes. No app change is needed to
switch from the fake server to the real one -- just update `WS_URL` in `config.ts`.
