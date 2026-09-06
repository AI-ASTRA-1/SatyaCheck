# SATYACHECK

Real-time detection of AI-cloned voices during live calls.

Smart India Hackathon 2026 · Problem Statement 26104 · Team AI ASTRA
AICTE Cyber Security Cell · Theme: Blockchain & Cybersecurity

---

## What it does

Listens to a live call and answers one question every second: **how likely is it that
this voice is machine-generated?** If the answer crosses a threshold, the person on the
call is warned — before a transfer is approved or an OTP is read aloud.

Four checks run in parallel on a **copy** of the audio. Each returns evidence, not a
verdict. A separate risk engine fuses them into one calibrated score.

| Check | What it answers | Module |
|---|---|---|
| Machine fingerprints | Is the waveform synthetic? | `audio_ml/` |
| Speaker identity | Is this who they claim to be? | `audio_ml/` |
| Rhythm & pitch | Is the prosody anomalous? | `audio_ml/` |
| What is being said | Is this a scam script? | `nlp_rag/` |

Detection runs **out-of-band**. If the models fail mid-call, the call continues
unprotected — it can never be dropped or altered.

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
| Android call-screen overlay | **Working** — three states, auto-speakerphone, raw mic capture |
| Telephony routing (V2) | **Not built** — designed, not implemented |
| Family Vault | **Not built** — planned |

**Calibration caveat:** current calibration was fitted against a placeholder lexical
encoder, not BGE-m3. Confidence figures derived from it are provisional.

---

## Layout and ownership

Folder ownership is absolute. Do not edit outside your folder — open a request instead.

```
audio_ml/      A (Srujan)  speaker verification, VAD, anti-spoof, Android app
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

A red suite blocks the commit. Never `xfail` or delete a test to get a green run.

---

## Findings worth knowing

**Simulated degradation is not a substitute for real phone audio.** We tested the
condition-matched 8 kHz enrollment hypothesis and it was falsified — genuine
phone-degraded audio outperformed simulated degradation by roughly 14.6%. We publish
this rather than bury it.

**Lab accuracy does not survive the real world.** Published detectors reporting ~2.85%
equal error rate on ASVspoof 2021 DF degrade to ~35% on real-world multilingual audio
(ML-ITW, Wuhan University). Any claim we make is measured on unseen data or not made.

**Watermarking naively is worse than not watermarking.** Training on data where only the
fakes carry a watermark produces a shortcut; watermarking a genuine voice then pushes
error from ~16% to ~75% (Fraunhofer AISEC). Watermarks go on both classes or neither.

---

## Privacy and legal constraints

These are product constraints, not paperwork.

- **Embeddings, never audio.** Enrolment recordings are destroyed after the voiceprint.
- No call recordings at rest. Analysis is in-flight.
- Evidence layer stores a hash of the alert event — no audio, no transcript.
- Voiceprints are personal data under the DPDP Act 2023 (Rules notified November 2025).
  Consent must be explicit; deletion must actually delete.
- **Never add a feature that modifies the call.** No injected audio, no synthetic speech
  into the stream. Our legal basis is one-party consent — our user is a genuine
  participant. Observing is defensible; altering is not.

Never commit: real audio, voiceprints, `.env`, keys, `corpus/heldout/`.

---

## Documents

| File | Contents |
|---|---|
| `AGENTS.md` | Instructions for coding agents — ownership, constraints, settled facts |
| `CLAUDE.md` | Claude Code specifics; imports `AGENTS.md` |
| `GEMINI.md` | Gemini CLI / Antigravity pointer to `AGENTS.md` |
| `PRD.md` | Product requirements |
| `PLAN.md` | Build plan and milestones |

---

## Maintaining this file

Agents may update this README. Rules:

1. **Only edit the Status table, Setup, Running tests, and Documents sections.** Findings
   and Privacy sections change only when a human says so.
2. **A status only moves to "Working" when a test proves it.** Name the test in the
   commit message. "It ran on my machine" is not a status change.
3. **Never add a number this repo did not produce.** Figures under Findings carry a
   source; anything without one does not go in.
4. **Keep the Status table honest, especially about what is broken.** A README that
   overstates readiness costs more than one that is out of date.
5. Update in the same commit as the change, not afterwards.
6. Do not add badges, a roadmap, an acknowledgements section, or a features list that
   duplicates the table above.
