# SATYACHECK — agent instructions

Real-time detection of AI-cloned voices during live calls.
SIH 2026 · Problem Statement **SIH26104** · Theme Blockchain & Cybersecurity · PS Category Software · Team **AI ASTRA**.
*Real Voice. Real Person. Real-Time Protection.*

Four-person repo. **Folder ownership is absolute** — see Ownership below.

**The deck and the project report are the source of truth for scope, architecture,
numbers and claims.** Where this file, `README.md`, or any code comment disagrees with
them, they win and the file is wrong — fix it. Do not invent a fact that appears in
neither.

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
- Write a claim the deck or the report does not support. See How we are allowed to describe this.

---

## How we are allowed to describe this

The report is explicit that overclaiming is the fastest way to lose this. These are
wording rules, not style preferences.

- **Never "our system detects deepfakes."** It *raises a warning*; the human decides.
- **Never "solved."** Detecting synthetic speech in the real world is an unsolved
  research problem. Report §8 leads with that gap rather than hiding it.
- **Never "real time" if the audio arrives as recordings.** If the telephony provider
  cannot stream during the call, we degrade to near-real-time chunked analysis and say
  so in those words.
- **We analyse sound, not words.** A transcript is useless for spotting a fake voice —
  the giveaways live in the audio and are destroyed by speech-to-text. We read the
  transcript too, for the separate purpose of scam-script detection.
- **The scammer installs nothing.** The person being protected opts in and forwards
  their own number. The attacker's cooperation is never required.
- Current status is **a controlled live-warning prototype. Real-world deployment after
  validation.**

---

## Ownership

| Path | Owner | Contents |
|---|---|---|
| `audio_ml/` | A (Srujan) | ECAPA-TDNN speaker verification, Silero VAD, anti-spoof, React Native app |
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

**Stack (deck, slide 3):** WebRTC · Python · PyTorch · WebSocket · FastAPI · React Native.
All inference is **local** — no external API to fail on demo day. Models are open-source
with public checkpoints; nothing to license.

---

## Scope — build Round 1, describe Round 2

Report §11. Do not build a Round 2 item, and do not present one as working.

| Round 1 — must exist and must demo | Round 2 — described, not built |
|---|---|
| Calling app, two parties connected, audio copied to our server | Virtual-number routing for ordinary calls (V2) |
| Detection model on that stream, score updating live | Family Vault enrolment and consent flow |
| Risk display with a clear warning state | Transcript-based scam-script detection |
| Training pipeline with phone-compression and noise built in | Payment-blocking integration with a bank |
| Evaluation on unseen data, incl. Indian-accented genuine speech | On-device inference |
| Alert-fingerprinting and the sealed record | |

Saying "this part is built, this part is designed, this part is research" reads as
competent. Implying everything works reads as untested.

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
- **The Family Vault does not prove a caller is genuine.** A good clone is *built* to
  match the real person's voiceprint — that is the objective of cloning. Matching the
  vault reliably catches a **different person** impersonating family; catching a **clone
  of an enrolled person** needs the synthetic-speech check as well. Never write "we store
  family voices so we can detect fakes." Three outcomes, not two (report §9).
- **Watermarks go on both classes or neither.** Training where only the fakes carry a
  watermark teaches the model to look for the watermark instead of for synthesis.
- **No voice data on a ledger.** Only tamper-evidence anchors. Putting voice on-chain
  would breach DPDP data minimisation — that sentence is the blockchain answer.

---

## Architecture — seven stages

```
call source → audio ingestion → live pipeline → four AI checks → risk fusion → response → evidence
```

| Stage | Contents |
|---|---|
| 01 Call source | Incoming phone call, custom calling app, or a forwarded ordinary call |
| 02 Audio ingestion | Audio unpacking, codec handling (Opus / G.711 / AMR), **20 ms** frames |
| 03 Live pipeline | WebSocket → short audio buffer (Redis Streams) → silence filtering → live processing |
| 04 Four AI checks | Run in parallel on a copy — see table below |
| 05 Risk fusion | AI signals + call context → risk score **0–100** |
| 06 Response | User warning → verify / escalate → transaction protection |
| 07 Evidence | Incident fingerprint → tamper-evident record → verifiable evidence |

Four checks, in parallel, on a **copy** of the audio:

| Check | Module | Answers |
|---|---|---|
| Machine fingerprints | XLS-R + AASIST (`audio_ml/`) | is the waveform synthetic |
| Speaker identity | ECAPA-TDNN (`audio_ml/`) | is this who they claim |
| Rhythm & pitch | openSMILE (`audio_ml/`) | prosodic anomaly |
| What is being said | speech-to-text → language model (`nlp_rag/`) | scam script pattern |

XLS-R carries the multilingual front end — Hindi, English, Tamil, Marathi, Bengali and
more. AASIST-L (~85K params) runs on CPU.

**Models emit evidence. The risk engine owns the decision.** No module returns a final
security verdict; each returns structured signals plus the spans or frames that justify them.

Three rules the risk engine must keep:
- **Continuous scoring** — the score updates throughout the call (roughly once a second),
  never a single decision taken at the start.
- **Call context is part of fusion** — number, location, time, past history, alongside the
  model signals.
- **Policy rules are per customer** — a bank is not a family. The 0–100 score is the
  output; what it triggers is configurable per deployment.

Conversational intelligence is **model-agnostic and local by default**. No third-party
audio streaming — the caller is a non-consenting party.

Detection runs **out-of-band on a copy**. A model failure must degrade to "no warning",
never to a dropped or altered call.

### Latency budget (report §6)

| Segment | Budget |
|---|---|
| Ingestion → live pipeline | < 20 ms |
| Four AI checks | < 180 ms |
| Risk fusion | < 30 ms |
| Response | < 50 ms |
| **Spoken word → warning on screen** | **< 400 ms, p90** |

Bridging through a virtual number adds a further **~100–330 ms** over a direct call.

---

## Getting the audio — V1 and V2

- **V1 (demo):** both parties on our own app; a media relay copies the audio to our
  models. End-to-end controllable, and useless in reality — a scammer will never install
  our app.
- **V2 (the deployable answer):** the protected user forwards their own number to a
  virtual number we control. It answers, dials them back, bridges the two legs, and we
  hear the call. The attacker dialled a number that happened to forward.

The per-minute forwarding leg is the **cost driver**, modelled per user. Buyers: banks
under RBI fraud duties, contact centres, helplines. Pilot-ready on a single bank inbound
line in 6–9 months.

---

## Open questions — do not assume, do not paper over

The report flags these as unverified. Treat each as blocking for any claim built on it.

- **Can the telephony provider stream audio *during* the call**, not just hand us a
  recording afterwards? Unconfirmed in current provider documentation. If recordings
  only, we degrade to chunked near-real-time and must say so.
- **TRAI and DoT positions** on live voice analysis — specific clauses unread. Do not
  assert compliance.
- **Bridge cost and delay** are real line items, not rounding errors.
- **Four citations are marked *ID not verified*** (below). A human looks these up on
  arXiv and confirms them; this is not an agent web-search task. A wrong citation on a
  references slide is worse than a missing one.

---

## Training data and evaluation rules

From the deck's challenge/mitigation pairs and report §7–8. These are the difference
between working and not working, not optional polish.

- **Train directly on 8 kHz G.711 and AMR-NB.** Phone networks destroy exactly the fine
  detail the models rely on. Push training audio through phone-quality compression before
  the model sees it.
- **Train on noisy audio too.** Retraining on noise recovered roughly 10–15 percentage
  points in the harder conditions (NTU Singapore).
- **Train across corpora, score only unseen data.** Never report a figure measured on
  data resembling the training set.
- **Watermark both classes or neither.**
- **Build and publish our own Indian-accent FPR benchmark.** No existing benchmark covers
  it, and a system that cries wolf on real Indian English is worse than useless here.
  This is what the empty `corpus/heldout/` is blocking.
- **Report cost-weighted metrics** (ASVspoof 5 standard), not a bare EER — missing a
  fraud and annoying a real customer are not equally bad mistakes.

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
   ownership table moved. If the change contradicts the deck or the report, stop and say
   so — those are corrected by a human, not by an agent. A doc that now contradicts the
   code is a regression, not a follow-up.

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
- Cost-weighted metrics on unseen data, never a bare EER on familiar data.

---

## The demo plan (report §11) — this decides the round

Order matters:

1. A **genuine Indian-accented call**, score stays low. Proving we do not flag real
   people is the harder and more convincing half; most teams skip it.
2. A **cloned voice** being caught.
3. Deliberately, a **badly degraded clone** where the score wobbles — then explain what
   we measured and what training recovers.

Volunteering a weakness with a number attached is the strongest move available.

---

## Git

- Branch per owner. Commit small, present tense, no scope creep across folders.
- Never push. Leave the commit local and say it is ready.
- Contract change (`contracts.py`, `config.py`) → stop, describe the change, wait for C.

---

## Privacy and legal (these are product constraints, not paperwork)

- Store **embeddings, never audio**. Enrolment audio is destroyed after the voiceprint.
- No call recordings at rest. Analysis is in-flight.
- Evidence layer: hash each alert event → fold the hashes into a Merkle tree → publish
  the root where it cannot be quietly rewritten. This proves a single alert existed,
  and that it predates the transfer, **without exposing any other person's call**. No
  audio, no transcript, no voice data on the ledger. Handed to NCRP / 1930 on request.
- Voiceprints are personal data under DPDP Act 2023 (Rules notified Nov 2025). Consent
  must be explicit, revocable, and deletion must actually delete.
- The legal basis for V2 routing is one-party consent — our user is a genuine call
  participant. Do not add any feature that **modifies** the call (injected audio, synthetic
  speech into the stream). Observing is defensible; altering is not, and is out of scope.

---

## Where the numbers live

Every figure used in the deck and the report, with its source. Do not quote any other
figure without a link, and do not drop the caveats.

**Verified IDs**

- Lab EER **2.85%** (ASVspoof 2021 DF) — Tak et al., Odyssey 2022, `arXiv:2202.12233`
- AASIST-L **≈85K params**, runs on CPU — Jung et al., ICASSP 2022, `arXiv:2110.01200`
- RawNet2 baseline — Tak et al., 2021, `arXiv:2011.01108`
- ASVspoof 2021 overview — Yamagishi et al., `arXiv:2109.00537`
- ASVspoof 2021 in the wild — Liu et al., 2023, `10.1109/TASLP.2023.3285283`
- ASVspoof 5 (current evaluation standard) — Wang et al., 2024, `arXiv:2408.08739`
- AudioSeal (localized watermarking) — ICML 2024, `arXiv:2401.17264`
- Does audio deepfake detection generalize? — Müller et al., 2022, `arXiv:2203.16263`

**ID not verified — confirm before any of these go on a slide**

- Real-world EER **35.24%** (14 languages, 7 platforms) — ML-ITW benchmark, Wuhan
  University. The most important paper we have read; the 2.85% → 35.24% gap *is* the
  project.
- Watermark mark-to-frame **16% → 75%** — Fraunhofer AISEC
- Noisy-training recovery of **10–15 percentage points** — NTU Singapore
- Voice-scam compliance **16.5%** overall, up to **36%** in the relative-in-distress
  scenario, n≈4,100 — Harvard Kennedy School / SEAS with Meta. **Caveat that must travel
  with this number:** US sample, reporting what they think they *would* do, not what
  Indian users actually did. For Indian fraud figures use I4C, NCRP or RBI with the
  financial year attached — never a security vendor's marketing page.

**Other figures stated in the documents:** ~30 seconds of audio is enough to clone a
voice; the score updates roughly once a second.

Anything else is unverified. Say "no verified source" rather than guessing.
