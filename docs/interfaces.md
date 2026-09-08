# SATYACHECK interface contracts

Single written source of truth for the shared interfaces the team codes against.
It is written against `contracts/`; when the two disagree, `contracts/` is the
mechanism and this file is the prose, and a doc that contradicts the code is a
regression.

Authority: the SIH deck and the project report win for scope, architecture, numbers
and claims. The Exotel/WebRTC acquisition decision (2026-09-06) postdates both and
`AGENTS.md` "Audio acquisition" is its authority. This document does not add a fact
that appears in none of them.

Versioning: wire messages carry `schema_version` (currently `1.0`). Additive field
changes are free. Breaking changes require a stated review by the backend lead and a
`schema_version` bump.

## 1. The transport invariant

Exotel (primary) and WebRTC (fallback) are interchangeable acquisition layers. Both
terminate at the same audio-stream interface (`contracts.acquisition`). The backend,
the AI checks, the risk engine and the app contract are the same on both paths.

Enforced two ways:

- Structural. Below stage 02 only `CanonicalAudioChunk` and `CanonicalAudioBatch`
  exist. They carry no `transport`, `codec` or `sample_rate` field, so nothing below
  ingestion can branch on which transport delivered the audio. There is no field to
  read.
- Mechanical. `tests/test_transport_invariant.py` scans `backend/` and `ml/` with an
  AST walk and fails on any transport import, acquisition-boundary type use, or
  `.transport` / `.codec` attribute access outside `backend/app/ingestion/`. Run it
  with `uv run pytest tests/test_transport_invariant.py -q`.

A change that makes one path behave differently from the other is a bug, unless the
difference is a documented codec or sample-rate property of the transport itself.
Adding a third acquisition layer requires a new `acquisitions/<name>/` and one
registry line in ingestion; nothing below stage 02 changes.

## 2. Stream lifecycle

```
adapter.connect(...)                 acquisition (exotel | webrtc)
  on_open(StreamOpen)                one, first
  on_chunk(AudioChunk)               zero or more, one per 20 ms frame
  on_close(StreamClose)              one, last
            |
            v  (AudioStreamConsumer: the single seam both transports terminate at)
stage 02 ingestion: decode + normalize -> one CanonicalAudioChunk per 20 ms
            |
            v
stage 03 pipeline: buffer, silence filter -> CanonicalAudioBatch windows
stage 04 runner: 4 checks in parallel on a COPY, 180 ms deadline
            |
            v
stage 05 fusion: signals + CallContext -> 0 to 100 score, ~1/s
            |
            v
stage 06 response: RiskUpdate to the app
stage 07 evidence: alert fingerprint -> Merkle root published off-ledger
```

Scoring ticks roughly once a second for the life of the call. Until there is enough
audio, checks return SKIPPED and the score stays UNKNOWN / LOW, which renders as no
warning. A model failure degrades to "no warning", never to a dropped or altered
call; detection runs out-of-band on a copy so the audio never passes through the
models on its way to the listener.

### 2.1 WebSocket routes and the WebRTC ingest join point

Two concrete routes exist on the backend (`backend/app/main.py`):

- `/ws/audio/{stream_id}/{call_id}` -- inbound. `ExotelWebSocketAdapter` here already
  auto-detects transport per message: JSON text frames follow Exotel's
  connected/start/media/stop protocol (base64 8kHz PCM, resampled to 16kHz); binary
  frames are treated as raw, already-16kHz-mono-s16le PCM of any size, buffered and
  sliced into exact 640-byte canonical frames (remainder carried across messages, a
  true short tail marked `is_final` at close). **This binary path is the WebRTC
  ingest join point** -- a custom WebRTC adapter does not get its own route. It
  connects here directly and sends raw PCM as binary WebSocket messages, no JSON
  handshake, no separate port. It is responsible for Opus decode and 48kHz -> 16kHz
  resampling itself before sending; `IngestionConsumer.on_chunk` (stage 02) strictly
  requires `codec=pcm_s16le, sample_rate=16000, channels=1` and rejects anything else
  by design (`UnsupportedAudioFormatError`) -- this check is not to be loosened; fix
  the sender instead.
- `/ws/risk/{stream_id}` -- outbound. Broadcasts `AppMessage` JSON
  (`SessionStart` / `RiskUpdate` / `CallEnded`) to every listener registered on that
  `stream_id`.

`stream_id`/`call_id` contract: both are caller-supplied, not server-generated.
Whoever originates the call (the app) picks one id (e.g. a UUID) before dialing and
uses the same value as: the WebRTC signaling call id, both path segments of
`/ws/audio/{stream_id}/{call_id}` (`stream_id` and `call_id` may be the same value
for now), and the `{stream_id}` in `/ws/risk/{stream_id}`. A server-side adapter that
generates its own id (as an earlier WebRTC prototype did) breaks this -- the app has
no way to learn a server-generated id today.

## 3. Message schemas

### 3.1 Acquisition boundary (`contracts/acquisition.py`)

Never imported below stage 02.

AudioChunk: one frame as the transport delivered it, 20 ms nominal.

| Field | Type | Notes |
|---|---|---|
| stream_id | str | unique per call leg |
| call_id | str | groups the call |
| transport | Transport | exotel, webrtc. Allowed only here |
| codec | Codec | opus, g711_ulaw, g711_alaw, amr_nb, pcm_s16le |
| sample_rate | int | documented transport property (telephony 8k, WebRTC may be 48k) |
| channels | int | default 1 |
| frame_ms | int | default 20 |
| sequence | int | monotonic from 0, delivery order |
| payload | bytes | encoded in `codec` |
| capture_timestamp | datetime | call-side clock |
| received_at | datetime | adapter receive time, feeds latency budget |
| rtp_ts | int or None | transport-specific, never read below 02 |
| is_final | bool | default False. Marks a short trailing partial frame emitted once at stream close, not padded to frame_ms. Stage 02 must propagate it unpadded to CanonicalAudioChunk.is_final rather than dropping or padding it |
| metadata | dict[str, str] | transport extras, never read below 02 |

StreamOpen: call start, one per stream, before the first chunk. Carries
`direction` (inbound, outbound), `caller_number` and `callee_number` (PII, internal
only, never in the app contract), `started_at`, the codec properties, and an
`external_ref` (Exotel call SID or WebRTC peer id).

StreamClose: call end, one per stream, after the last chunk. `reason` is completed,
dropped, timeout or error. Carries `frames_received`, `bytes_received`,
`dropped_frames` so gaps are recorded, not hidden. `dropped_frames` is
incremented by the adapter whenever one media event's audio could not be
recovered (missing/empty payload, undecodable base64) and that event is
skipped rather than turned into an AudioChunk.

`AudioStreamAdapter` (Protocol): what the acquisition adapters implement.
`AudioStreamConsumer` (Protocol): what stage 02 implements. This is the exact seam
both Exotel and WebRTC terminate at.

### 3.2 Canonical audio (`contracts/pipeline.py`)

| Constant | Value | Meaning |
|---|---|---|
| CANONICAL_SAMPLE_RATE | 16000 | the only sample rate below stage 02 |
| CANONICAL_FRAME_MS | 20 | one frame per chunk |
| CANONICAL_FRAME_BYTES | 640 | 320 samples of mono s16le |

CanonicalAudioChunk: one 20 ms frame. `stream_id`, `call_id`, `sequence`
(renumbered from 0 at ingestion), `pcm_s16le` (mono little-endian signed 16-bit,
exactly 640 bytes unless `is_final`), `capture_timestamp`, `ingest_timestamp`, and
`is_final` (short tail on StreamClose; checks must tolerate it). No codec, no
transport, no sample-rate field. A non-final frame with the wrong length is
rejected by the model validator.

CanonicalAudioBatch: a contiguous window handed to the checks. It is a COPY; checks
MUST NOT mutate it. Fields: `stream_id`, `call_id`, `start_sequence`,
`end_sequence`, `pcm_s16le`, `sample_count`, `capture_started_at`,
`capture_ended_at`, `window_ms`.

### 3.3 Call context (`contracts/context.py`)

CallContext flows into fusion alongside the check signals: `stream_id`, `call_id`,
`caller_number` / `callee_number` (PII, internal), `direction`, `started_at`,
`location_hint`, `call_history` (list of CallHistoryEntry: other_number, started_at,
duration_seconds, outcome), `number_reputation` (NumberReputation: blocklisted,
reported_before, spam_score 0 to 1), and `policy` (PolicyRef: deployment_id,
policy_version). Policy rules are per customer; the 0 to 100 score is the output and
what it triggers is configurable per deployment.

### 3.4 Checks (`contracts/checks.py`)

CheckName: machine_fingerprint (XLS-R + AASIST), speaker_identity (ECAPA-TDNN),
prosody (openSMILE), stt_llm (speech-to-text then language model).

CheckStatus: ok, degraded (ran with caveats), failed (model error, treated as no
signal, never a verdict), skipped (not enough audio yet).

ReasonCode: the stable, non-PII reason strings the risk engine folds into the score
(fingerprint_synthetic, fingerprint_genuine, voiceprint_no_enrolment,
voiceprint_no_match, voiceprint_match, voiceprint_match_synthetic, prosody_anomaly,
prosody_normal, script_risk_high, script_risk_absent, context_high_risk,
context_low_risk, insufficient_audio, degraded_check).

EvidenceItem: reason_code, detail (short, non-PII), model, model_version,
window_started_at, latency_ms.

The four signals, discriminated on `kind`:

| Signal | kind | Fields |
|---|---|---|
| MachineFingerprintSignal | machine_fingerprint | synthetic_probability (0 to 1) |
| SpeakerIdentitySignal | speaker_identity | match_status, similarity (0 to 1, when enrolment exists) |
| ProsodySignal | prosody | anomaly_score (0 to 1) |
| SttLlmSignal | stt_llm | script_risk (0 to 1), script_category |

SpeakerIdentitySignal.match_status: no_enrolment, no_match, match_synthetic,
match_human. Family Vault is Round 2, so Round 1 returns no_enrolment, which is
neutral evidence and never a verdict. match_synthetic is the dangerous case: a clone
of an enrolled person.

SttLlmSignal carries only script_risk and script_category. The transcript itself is
an in-memory working artifact of the stt_llm check only; it must never appear in
EvidenceItem, CheckResult, RiskUpdate or AlertRecord, and is discarded when the
check returns. No transcript at rest.

CheckResult: check, status, signal (one of the four, or None), evidence, processed_at,
window_ms. A check returns evidence, never a final security verdict.

Check (Protocol): `name` plus `run(batch: CanonicalAudioBatch, context: CallContext)
-> CheckResult`. CheckRunner (Protocol): `run_checks(...) -> ChecksBatchResult`,
stage 04 orchestration. ChecksBatchResult: stream_id, call_id, started_at,
batch_sequence, results, audio_window_ms, degraded.

### 3.5 The app contract (`contracts/risk.py`)

SCHEMA_VERSION is `1.0`.

RiskVerdict: genuine, synthetic, unknown (insufficient audio, or a model degraded).
RiskLevel: low, medium, high, critical.

DEFAULT_BAND_MAPPING (score to first RiskLevel at or above it):

| Score | RiskLevel |
|---|---|
| 0 | low |
| 40 | medium |
| 70 | high |
| 90 | critical |

The app renders states, never thresholds. It maps RiskLevel to visuals; it never
computes a band from score. Deployments override the mapping in backend policy
config, never in app code.

SessionStart: kind session_start, stream_id, call_id, started_at,
protected_number (the enrolled user's own number), schema_version. The app shows a
subtle scanning indicator.

RiskUpdate, roughly once per second: kind risk_update, stream_id, call_id,
sequence (scoring tick), timestamp, score (0 to 100), verdict, risk_level,
confidence (0 to 1, aggregate signal confidence, not a threshold), reasons,
contributing_checks, degraded_checks, evidence_refs (opaque ids only; no audio, no
transcript, no numbers), schema_version.

CallEnded: kind call_ended, stream_id, call_id, ended_at, duration_seconds,
final_score, final_verdict, final_level, reasons, alert_fingerprint (present iff an
alert was raised), merkle_root, sealed_record_id, root_published_at,
schema_version.

AppMessage is the discriminated union over the three, on `kind`.

## 4. The 180 ms check budget

Stage 04 fans out to all four checks in parallel on a COPY of the window and must
return within 180 ms. The runner marks any straggler FAILED or SKIPPED; a failed
check contributes no signal and the relevant reason appears as degraded_check, so a
model failure degrades to "no warning" and never pauses or alters the call.
EvidenceItem.latency_ms is where each check records its own time against the budget.

## 5. Scoring and decision semantics

Fusion (stage 05) combines the four check signals with CallContext into a single 0
to 100 score, updating roughly once a second. Continuous scoring means there is
never a single start-of-call decision. What a score triggers (warning, SMS,
escalation, callback, second factor) is per deployment; this contract only carries
the score in RiskLevel. The human decides; a warning is not a verdict.

## 6. Evidence and privacy

Stage 07 fingerprints each alert event, folds the fingerprints into a Merkle tree,
and publishes the root where it cannot be quietly rewritten. The fingerprint is a
sha256 over the canonical alert event (score, verdict, reasons, model versions, call
metadata, timestamps). No audio, no transcript, no voice data, no numbers on the
ledger. SealedRecord is the artifact handed to NCRP / 1930 on request.

Shapes: ChainAnchor (network, root, published_at), SealedRecord (sealed_record_id,
alert_fingerprint, created_at), AlertRecord (alert_id, stream_id, call_id, raised_at,
final_score, verdict, risk_level, reasons, contributing_checks, degraded_checks,
fingerprint, merkle_leaf, merkle_root, root_published_at, chain_anchor,
sealed_record_ref).

Privacy rules that travel with the code: embeddings never audio; no call recordings
at rest; analysis is in-flight; voiceprints are personal data under the DPDP Act
2023 with explicit, revocable consent; never a feature that injects or modifies call
audio.

## 7. Latency budget definition

The docs state spoken word to warning on screen under 400 ms, nine times out of
ten, and each stage carries a budget: stage 03 under 20 ms, stage 04 under 180 ms,
stage 05 under 30 ms, stage 06 under 50 ms.

What the 400 ms figure measures: the pipeline latency for one scoring tick, from the
audio window leaving stage 03 to the overlay drawing, excluding audio accumulation
time, because the models need seconds of audio before a signal exists. The
timestamps that measure it are on the messages: AudioChunk.received_at,
CanonicalAudioChunk.ingest_timestamp, EvidenceItem.window_started_at,
CheckResult.processed_at, RiskUpdate.timestamp, plus the app render time.

Open, and blocking for any "real time" claim: whether the telephony provider can
stream call audio during the call rather than hand over a recording afterwards
(`AGENTS.md` open questions). If it is recordings only, the primary path degrades to
chunked near-real-time analysis and is described in those words. The WebRTC
fallback is the mitigation, not a second product.

## 8. Import rule matrix

| Directory | May import | Must NOT import |
|---|---|---|
| contracts/ | pydantic, stdlib | anything else |
| acquisitions/exotel, acquisitions/webrtc | contracts, transport SDK | backend/, ml/, app/ |
| backend/app/ingestion/ | contracts, acquisitions (wiring only), codec libs | ml/, app/ |
| backend/app/pipeline/, fusion/, response/, evidence/ | contracts, redis, numpy, websockets | acquisitions, any transport symbol |
| ml/checks/* | contracts.checks, torch/model libs | contracts.risk, contracts.evidence, backend/, acquisitions/ |
| ml/runner/ | contracts, ml/checks/* | backend/, acquisitions/ |
| app/ (TypeScript) | RiskUpdate JSON schema | never Python |

The invariant test enforces the transport rows mechanically. Contract reviewer also
greps `import.*(exotel|webrtc)|from (exotel|webrtc)` on any diff touching a module
below stage 02. A third acquisition layer is added entirely above stage 02.

## 9. Round 2 boundary

Round 1 (built): audio acquisition (Exotel primary, WebRTC fallback); detection on
stream with live score; risk display with a warning state; training pipeline with
phone compression and noise; evaluation on unseen data including Indian-accented
genuine speech; alert fingerprinting and the sealed record.

Round 2 (described, not built, not in these contracts as product features): Family
Vault enrolment and consent flow (so speaker_identity returns no_enrolment in
Round 1); transcript-based scam-script detection as a product warning (Check 4 is
Round 1 only as an evidence channel); payment-blocking integration; on-device
inference.

## 10. Open decisions to confirm before coding turn 1

- Canonical sample rate: 16000 is the constant now. The ML lead confirms it against
  the fine-tuned model input specs in the same change that adds stage 04.
- Whether the telephony provider streams mid-call: human check against Exotel's own
  documentation, not a web search.
- Torch wheels on Python 3.13: verify with
  `uv run --extra ml python -c "import torch, torchaudio"` before the ml extra is
  enabled.