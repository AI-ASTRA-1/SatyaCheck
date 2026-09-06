# SATYACHECK

**Real Voice. Real Person. Real-Time Protection.**

Real-time detection of AI-cloned voices during live calls.

Smart India Hackathon 2026 · Problem Statement **SIH26104** · Team **AI ASTRA**
Theme: Blockchain & Cybersecurity · PS Category: Software

> A controlled live-warning prototype now. Real-world deployment after validation.

---

## What it does

Listens to a live call and answers one question, updated continuously throughout the
call rather than once at the start: **how likely is it that this voice is
machine-generated?** If the answer crosses a threshold, the person on the call is
warned — before a transfer is approved or an OTP is read aloud.

It **raises a warning**; the human decides. We do not claim to detect deepfakes, and we
do not claim the problem is solved — see Findings.

Four checks run in parallel on a **copy** of the audio. Each returns evidence, not a
verdict. A separate risk engine fuses them with call context (number, location, time,
history) into a single **0–100** score; what that score triggers is a policy rule set per
customer, because a bank is not a family.

| Check | What it answers | Model | Module |
|---|---|---|---|
| Machine fingerprints | Is the waveform synthetic? | XLS-R + AASIST | `audio_ml/` |
| Speaker identity | Is this who they claim to be? | ECAPA-TDNN | `audio_ml/` |
| Rhythm & pitch | Is the prosody anomalous? | openSMILE | `audio_ml/` |
| What is being said | Is this a scam script? | speech-to-text → LM | `nlp_rag/` |

XLS-R carries the multilingual front end — Hindi, English, Tamil, Marathi, Bengali and
more. AASIST-L (~85K params) runs on CPU. All inference is local; there is no external
API to fail on demo day.

Detection runs **out-of-band**. If the models fail mid-call, the call continues
unprotected — it can never be dropped or altered.

**Latency budget:** spoken word to warning on screen in under **400 ms**, nine times out
of ten. Bridging through a virtual number (V2) adds a further ~100–330 ms.

---

## Pipeline

```
call source → audio ingestion → live pipeline → four AI checks → risk fusion → response → evidence
```

| Stage | Contents | Budget |
|---|---|---|
| 01 Call source | **Exotel** (primary) or **WebRTC** (fallback) — see Audio acquisition | — |
| 02 Audio ingestion | Unpacking, codec handling (Opus / G.711 / AMR), 20 ms frames | — |
| 03 Live pipeline | WebSocket → short buffer (Redis Streams) → silence filtering | < 20 ms |
| 04 Four AI checks | In parallel, on a copy | < 180 ms |
| 05 Risk fusion | AI signals + call context → 0–100 | < 30 ms |
| 06 Response | Warning → verify / escalate → transaction protection | < 50 ms |
| 07 Evidence | Incident fingerprint → tamper-evident record | — |

**Stack:** WebRTC · Python · PyTorch · WebSocket · FastAPI · React Native

---

## Audio acquisition

Two paths deliver call audio. They differ in nothing else.

```
Primary:   Exotel → audio stream ┐
                                 ├→ SatyaCheck backend → AI models → risk engine → app / overlay
Fallback:  WebRTC → audio stream ┘
```

**Primary — Exotel.** Exotel is the telephony infrastructure. Incoming calls to the
protected user arrive through it, Exotel streams the call audio to our backend, and the
call itself continues normally through Exotel throughout. The caller installs nothing.

**Fallback — WebRTC.** If the Exotel integration fails, or its call/audio streaming
proves too limited, we establish the audio channel over WebRTC and run the identical
backend. This exists so the complete system can still be demonstrated with the telephony
integration down.

The risk result — genuine or synthetic, plus the risk level — goes to the SatyaCheck app,
which draws the warning **over whatever app is in the foreground**, so the user sees it
mid-call without switching apps. Identical on both paths.

**The invariant:** Exotel and WebRTC are acquisition layers only. The backend, the four
AI checks, the risk engine and the app contract are the same on both. Transport-specific
handling stops at ingestion (stage 02); nothing below it may branch on which transport
delivered the audio. Adding a third acquisition layer later should require no change
below stage 02.

> Exotel is a team decision (2026-09-06) and is named in neither the deck nor the report.
> This section and the matching one in `AGENTS.md` are the authority for it.

---

## Scope

Round 1 must exist and must demo. Round 2 is described, not built — do not present a
Round 2 item as working.

| Round 1 — built | Round 2 — designed |
|---|---|
| Exotel acquisition (primary) and the WebRTC fallback | Family Vault enrolment and consent flow |
| Detection model on the stream, score updating live | Transcript-based scam-script detection |
| Risk display and over-the-top warning overlay | Payment-blocking integration with a bank |
| Training pipeline with compression and noise built in | On-device inference |
| Evaluation on unseen data, incl. Indian-accented speech | |
| Alert-fingerprinting and the sealed record | |

---

## Status

Honest state of the repo. Do not read anything here as more finished than it says.

| Component | Status |
|---|---|
| `nlp_rag/` scoring pipeline | **Working** — 191 tests passing |
| Speaker verification (ECAPA-TDNN) | **Working** — calibrated on real audio, 12-scenario regression passing |
| Voice activity detection (Silero VAD) | **Working** |
| Anti-spoof detection | **Not working** — no checkpoint on Python 3.14; returns neutral `0.5` / `"uncertain"` |
| `embed.py`, `asr.py` | **Shells** — adapter stubs, unwired |
| Retrieval evaluation | **Not written** — `eval_retrieval.py` missing, `corpus/heldout/` empty |
| Call-screen overlay (React Native, Android) | **Working** — three states, auto-speakerphone, raw mic capture |
| Exotel acquisition (primary path) | **Not built** — mid-call audio streaming unverified against Exotel's documentation |
| WebRTC acquisition (fallback path) | **Not built** — designed as the Exotel fallback |
| Family Vault | **Not built** — planned for Round 2 |

**Calibration caveat:** current calibration was fitted against a placeholder lexical
encoder, not BGE-m3. Confidence figures derived from it are provisional.

**Unconfirmed and blocking:** whether **Exotel** can stream call audio *during* the call
rather than handing over a recording afterwards. Nobody has checked this against Exotel's
documentation, and the whole primary path rests on it. If it is recordings only, that
path degrades to chunked near-real-time analysis and we say so in those words rather than
claiming "real time" — the WebRTC fallback exists precisely because this is open. TRAI
and DoT clauses on live voice analysis are also unread.

---

## Layout and ownership

Folder ownership is absolute. Do not edit outside your folder — open a request instead.

```
audio_ml/      A (Srujan)  speaker verification, VAD, anti-spoof, React Native app
nlp_rag/       B           corpus, ASR, retrieval, markers, scoring, reason codes
server/        C           API layer, backend integration
contracts.py   C           FROZEN — read only
config.py      C           FROZEN — read only
```

---

## Setup

Environment is **Python 3.14.7**. Older docs say 3.11 — they are wrong, and the mismatch
is the biggest time sink in this repo.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Known-unavailable on 3.14, do not assume they work: `faiss`, `faster-whisper`,
`sentence-transformers`, `indic_transliteration`.

If a task depends on one of these, say so before starting rather than after failing.

---

## Running tests

```bash
pytest nlp_rag/                    # full suite — 191 tests, must stay green
pytest nlp_rag/tests/test_<mod>.py # single module
```

A red suite blocks the commit. Never `xfail` or delete a test to get a green run. Run
them before handing work back — reporting a pass count you did not observe is worse than
reporting a failure.

For model evaluation, report **cost-weighted metrics** (ASVspoof 5 standard) on unseen
data, never a bare EER on data resembling the training set.

---

## Training data rules

These are the difference between working and not working, not optional polish.

- Train directly on **8 kHz G.711 and AMR-NB**. Phone compression destroys exactly the
  detail the models rely on.
- Train on noisy audio as well as clean.
- Train across corpora; score only on unseen data.
- **Watermark both classes or neither.**
- Build and publish our own **Indian-accent false-positive benchmark**. Nobody else's
  covers it. This is what the empty `corpus/heldout/` is blocking.

---

## Findings worth knowing

**Lab accuracy does not survive the real world.** Published detectors reporting **2.85%**
equal error rate on ASVspoof 2021 DF (Tak et al., Odyssey 2022, `arXiv:2202.12233`)
degrade to **35.24%** on real-world multilingual audio (ML-ITW, Wuhan University — *ID
not verified*). That gap is the project. Any claim we make is measured on unseen data or
not made.

**Simulated degradation is not a substitute for real phone audio.** We tested the
condition-matched 8 kHz enrollment hypothesis and it was falsified — genuine
phone-degraded audio outperformed simulated degradation by roughly 14.6%. We publish
this rather than bury it.

**Watermarking naively is worse than not watermarking.** Training on data where only the
fakes carry a watermark produces a shortcut; watermarking a genuine voice then pushes
error from ~16% to ~75% (Fraunhofer AISEC — *ID not verified*). Watermarks go on both
classes or neither.

**Noise-aware training recovers real ground.** Retraining on noisy audio recovered
roughly 10–15 percentage points in harder conditions (NTU Singapore — *ID not verified*).

**The attack works on people.** In a survey experiment with ~4,100 US adults, about
**16.5%** said they would comply with an AI voice scam, rising to **36%** in the
relative-in-distress scenario (Harvard Kennedy School / SEAS with Meta — *ID not
verified*). Carry the caveat: US sample, stated intent, not Indian behaviour. For Indian
fraud figures use I4C, NCRP or RBI with the financial year attached.

**The Family Vault does not prove a caller is genuine.** A clone is *built* to match the
real person's voiceprint. The vault reliably catches a different person impersonating
family; catching a clone of an enrolled person needs the synthetic-speech check too.

Four sources above are marked *ID not verified*. A human confirms them on arXiv before
any goes on a slide.

---

## Privacy and legal constraints

These are product constraints, not paperwork.

- **Embeddings, never audio.** Enrolment recordings are destroyed after the voiceprint.
- No call recordings at rest. Analysis is in-flight.
- **Evidence layer:** each alert event is hashed, the hashes are folded into a Merkle
  tree, and the root is published where it cannot be quietly rewritten. That proves a
  single alert existed and predates the transfer, without exposing anyone else's call.
  **No voice data on the ledger** — putting it there would breach DPDP data
  minimisation. Handed to NCRP / 1930 on request.
- Voiceprints are personal data under the DPDP Act 2023 (Rules notified November 2025).
  Consent must be explicit and revocable; deletion must actually delete.
- **Never add a feature that modifies the call.** No injected audio, no synthetic speech
  into the stream. Our legal basis is one-party consent — our user is a genuine
  participant. Observing is defensible; altering is not.

Never commit: real audio, voiceprints, `.env`, keys, `corpus/heldout/`.

---

## Documents

| Document | Contents |
|---|---|
| SIH 2026 idea presentation (deck) | **Authoritative** — solution, technical approach, feasibility, impact, references |
| SIH 26104 project report | **Authoritative** — full architecture, research findings, scope split, glossary, reading list |
| `AGENTS.md` | Instructions for coding agents — ownership, constraints, settled facts |
| `CLAUDE.md` | Claude Code specifics; imports `AGENTS.md` |
| `GEMINI.md` | Gemini CLI / Antigravity pointer to `AGENTS.md` |

The deck and the report are not committed to this repo and are not edited by agents.

---

## Maintaining this file

Agents may update this README. Rules:

1. **The deck and the report win.** If this file contradicts either, this file is wrong —
   fix it. If a change would contradict them, stop and say so; a human corrects those.
   The one exception is the Exotel/WebRTC decision, which postdates both documents.
2. **Only edit the Status table, Setup, Running tests, and Documents sections.** Findings,
   Scope, Privacy, Pipeline and Audio acquisition change only when a human says so.
3. **A status only moves to "Working" when a test proves it.** Name the test in the
   commit message. "It ran on my machine" is not a status change.
4. **Never add a number this repo did not produce.** Figures under Findings carry a
   source; anything without one does not go in, and *ID not verified* markers stay until
   a human removes them.
5. **Keep the Status table honest, especially about what is broken.** A README that
   overstates readiness costs more than one that is out of date.
6. Update in the same commit as the change, not afterwards.
7. Do not add badges, a roadmap, an acknowledgements section, or a features list that
   duplicates the tables above.
