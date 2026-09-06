# SATYACHECK — agent instructions

Real-time detection of AI-cloned voices during live calls. SIH 2026, PS 26104, team AI ASTRA.
Four-person repo. **Folder ownership is absolute** — see Ownership below.

---

## Response rules

- Answer in the fewest tokens that fully answer. No preamble, no recap of the request, no summary of what you just did unless asked.
- Do not restate code you just wrote. A diff or a filename is enough.
- No "Great question", no "You're absolutely right", no emoji.
- Uncertain → say so in one clause and move on. Never invent an API, a flag, or a metric.
- Disagree when the instruction is wrong. Say why once, then do it their way if they repeat it.
- Read before you write. Never propose an edit to a file you have not opened in this session.

## Never do

- Touch a folder you do not own (below). Propose the change and stop.
- `git push`, force-push, rebase a shared branch, or amend a pushed commit.
- Add a dependency without asking. The environment is fragile — see Environment.
- Weaken, skip, or `xfail` a test to make a suite pass. Report the failure.
- Commit real audio, voiceprints, `.env`, keys, or anything under `corpus/heldout/`.
- Write a number into a doc, README, or slide that no test or logged run produced.
- Hand back a code change with the tests unrun or the docs stale. See Definition of done.

---

## Definition of done

A code change is not finished until all three are true. Do not open a commit, or say a
task is complete, with any of them missing.

1. **Code** — the change itself, smallest diff that works.
2. **Tests run** — actually execute them, do not reason about whether they would pass.
   Run the smoke test for every module you touched; run the full `nlp_rag/` suite (191
   tests) if you changed a contract or a shared helper. Report the outcome — pass count,
   or the failing test and its output. New logic ships with its test in the same change;
   a bug fix ships with the failing test written first. If you cannot run the tests, say
   so in one clause — never imply they passed.
3. **Docs updated** — if the change touches behaviour, a public function or its
   signature, a flag, a threshold, a CLI command, a dependency, or an architecture
   decision, update the doc that describes it in the *same* change: `README.md`, the
   touched module's docstring or README, and this file if a settled fact or the
   ownership table moved. A doc that now contradicts the code is a regression, not a
   follow-up.

---

## Ownership

| Path | Owner | Contents |
|---|---|---|
| `audio_ml/` | A (Srujan) | ECAPA-TDNN speaker verification, Silero VAD, anti-spoof, Android/Flutter app |
| `nlp_rag/` | B | corpus, ASR, retrieval, markers, scoring, reason codes, warnings, thresholds |
| `server/` | C | API layer, backend integration |
| `contracts.py`, `config.py` | C | **frozen** — read, never edit |

Cross-folder need → write the request in the PR description or ask. Do not reach across.

---

## Environment

Python **3.14.7** in practice. Docs say 3.11. This mismatch is the single biggest source of
lost time in this repo.

Known-broken on 3.14, do not assume these work:
- `faiss`, `faster-whisper`, `sentence-transformers`, `indic_transliteration` — not installed
- anti-spoof has **no working checkpoint**; the branch returns a neutral `0.5` / `"uncertain"`
- `embed.py` and `asr.py` in `nlp_rag/` are **unwired adapter shells**

If a task depends on any of the above, say so before starting rather than after failing.

---

## Facts that are settled — do not re-derive or contradict

- **Speaker thresholds:** `SPEAKER_MATCH_THRESHOLD = 0.85`, `SPEAKER_UNKNOWN_FLOOR = 0.60`.
  Calibrated on real audio. Changing either requires re-running the 12-scenario regression.
- **Negative result, published:** condition-matched 8 kHz *enrollment* was falsified.
  Genuine phone-degraded audio beat simulated degradation by ~14.6%. Do not write copy
  claiming simulated codec degradation is equivalent to real phone audio.
- **Calibration caveat:** current calibration was fitted against a placeholder lexical
  encoder, not BGE-m3. Any confidence figure derived from it is provisional.
- **Anti-spoof is not working.** Say "uncertain", never imply detection is live.

---

## Architecture (what fits where)

```
call source → ingestion → live pipeline → four checks → risk fusion → response → evidence
```

Four checks run in parallel on a copy of the audio:

| Check | Module | Answers |
|---|---|---|
| Machine fingerprints | XLS-R + AASIST (`audio_ml/`) | is the waveform synthetic |
| Speaker identity | ECAPA-TDNN (`audio_ml/`) | is this who they claim |
| Rhythm & pitch | openSMILE (`audio_ml/`) | prosodic anomaly |
| What is being said | ASR → local LLM (`nlp_rag/`) | scam script pattern |

**Models emit evidence. The risk engine owns the decision.** No module returns a final
security verdict; each returns structured signals plus the spans or frames that justify them.

Two rules the risk engine must keep:
- **Temporal persistence** — trigger on sustained high risk across N windows or one
  high-severity event, never on a single instantaneous score.
- **Sector + threat classification** on the output, not a bare 0–100.

Conversational intelligence is **model-agnostic and local by default**. No third-party
audio streaming — the caller is a non-consenting party.

Detection runs **out-of-band on a copy**. A model failure must degrade to "no warning",
never to a dropped or altered call.

---

## Testing

- 191 tests currently pass in `nlp_rag/`. Keep them green; a red suite blocks the commit.
- New logic needs a test in the same change. Bug fix → failing test first.
- Module smoke tests exist per module — run the one you touched, not the whole suite,
  unless you changed a contract.
- Run the tests before handing back — do not infer the result. Paste the pass count or
  the failure. This is step 2 of Definition of done, not optional.
- `eval_retrieval.py` is unwritten and `corpus/heldout/` is empty. Do not report retrieval
  quality numbers until both exist.

---

## Git

- Branch per owner. Commit small, present tense, no scope creep across folders.
- Never push. Leave the commit local and say it is ready.
- Contract change (`contracts.py`, `config.py`) → stop, describe the change, wait for C.

---

## Privacy and legal (these are product constraints, not paperwork)

- Store **embeddings, never audio**. Enrolment audio is destroyed after the voiceprint.
- No call recordings at rest. Analysis is in-flight.
- Evidence layer stores a hash of the alert event only — no audio, no transcript.
- Voiceprints are personal data under DPDP Act 2023 (Rules notified Nov 2025). Consent
  must be explicit and deletion must actually delete.
- The legal basis for V2 routing is one-party consent — our user is a genuine call
  participant. Do not add any feature that **modifies** the call (injected audio, synthetic
  speech into the stream). Observing is defensible; altering is not, and is out of scope.

---

## Where the numbers live

Reference figures used in the deck and report, with sources — do not quote any other
figure without a link:

- Lab EER 2.85% (ASVspoof 2021 DF) — Tak et al., Odyssey 2022, arXiv:2202.12233
- Real-world EER 35.24% — ML-ITW benchmark, Wuhan University
- Watermark mark-to-frame 16% → 75% — Fraunhofer AISEC
- AASIST-L ≈ 85K params — Jung et al., ICASSP 2022, arXiv:2110.01200

Anything else is unverified. Say "no verified source" rather than guessing.
