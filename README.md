# SATYACHECK

**Real Voice. Real Person. Real-Time Protection.**

Smart India Hackathon 2026 · Problem Statement **SIH26104** · Team **AI ASTRA**
PS title: AI-Powered Real-Time Detection and Prevention of Voice Cloning Impersonation Attacks
Theme: Blockchain & Cybersecurity · PS Category: Software

> A controlled live-warning prototype now. Real-world deployment after validation.

**Where this file comes from.** Everything below is taken from two documents: the SIH 2026
idea presentation (the deck) and the SIH 26104 project report. Nothing else. The one
addition is the audio acquisition decision of 2026-09-06, which appears in neither and is
marked as such where it occurs. If you want to add repo state (what is built, what is
broken, environment, ownership, test counts), add it in a clearly separated section and
label it as repo state rather than mixing it into the claims below.

---

## What it does

A system that listens to a phone call while it is happening and, roughly once a second,
answers one question: how likely is it that this voice is machine-generated? If the answer
crosses a threshold, the person on the call is warned before money is transferred or an OTP
is read aloud.

Three points the report puts first, because they are the ones most often described wrongly:

1. **We analyse sound, not words.** A transcript is useless for spotting a fake voice; the
   giveaways live in the audio and are destroyed by speech-to-text. We read the transcript
   too, for a separate purpose (scam-script detection).
2. **The scammer installs nothing.** The person being protected opts in. The attacker dials
   a number and their cooperation is never required.
3. **We are not claiming to solve this.** Detecting synthetic speech in the real world is an
   unsolved research problem. Section 8 of the report gives the numbers. Being straight
   about that is the strongest card with evaluators, not the weakest.

It **raises a warning**; the human decides.

---

## The attack, and why existing defences miss it

Voice cloning once needed hours of studio audio. It now needs roughly **30 seconds**, and
the tools are free. Harvest a voice, clone it, call under pressure (urgency, secrecy,
isolation), and money moves. SATYACHECK sits between the pressure call and the payment,
the only point where a warning still changes the outcome.

| Existing defence | What it checks | Why a clone gets past |
|---|---|---|
| Caller ID | The number on screen | Numbers are spoofable, and the number may be genuine |
| Recognising the voice | Does this sound like my son | Yes. That is the point of cloning |
| Call back to verify | Ring the real number | Works, but the script is built to stop you ("don't hang up") |
| Security question | Something only they know | Leaked personal data is cheap |
| Spam-call apps | Is the number blocklisted | Checks the number, never the voice |

Every one of these checks metadata or human judgement. None examines the sound.

---

## How detection works

Checks run **in parallel on a copy** of the audio. Each returns evidence, not a verdict. A
risk engine fuses them with call context into a single **0 to 100** score.

| Check | What it answers | Model |
|---|---|---|
| Machine fingerprints | Is the waveform synthetic | XLS-R + AASIST |
| Speaker identity | Is this who they claim to be | ECAPA-TDNN |
| Rhythm and pitch | Is the prosody anomalous | openSMILE |
| What is being said | Is this a scam script | speech-to-text then language model |

Report section 4 groups these as three signal families; the architecture in section 6 and
the deck's technical approach both show the four checks above.

XLS-R carries the multilingual front end: Hindi, English, Tamil, Marathi, Bengali and more.
AASIST-L (~85K params) runs on CPU. All inference is local, so there is no external API to
fail on demo day, and the models are open source with public checkpoints, so there is
nothing to license.

**Why read the transcript at all?** Because what is being said is independent evidence. A
voice can be real and the call still a scam (a coerced relative, a hired mule), and a cloned
voice reading a shopping list is not an emergency. Two channels that can disagree are more
useful than one confident channel.

---

## Architecture

```
call source → audio ingestion → live pipeline → four AI checks → risk fusion → response → evidence
```

| Stage | Contents | Budget |
|---|---|---|
| 01 Call source | See Audio acquisition below | |
| 02 Audio ingestion | Unpacking, codec handling (Opus / G.711 / AMR), 20 ms frames | |
| 03 Live pipeline | WebSocket, short buffer (Redis Streams), silence filtering | under 20 ms |
| 04 Four AI checks | In parallel, on a copy | under 180 ms |
| 05 Risk fusion | AI signals plus number, location, time and past history, into 0 to 100 | under 30 ms |
| 06 Response | On-screen warning, SMS or escalation, stop the payment or force call-back or second factor | under 50 ms |
| 07 Evidence | Alert fingerprint, sealed record, handed to NCRP / 1930 | |

**Spoken word to warning on screen: under 400 ms, nine times out of ten.** Bridging through
a virtual number adds roughly 100 to 330 ms over a direct call.

Three rules the risk engine keeps: the score updates continuously during the call rather
than once at the start; call context is part of fusion, not an afterthought; and policy
rules are per customer, because a bank is not a family. The 0 to 100 score is the output;
what it triggers is configurable per deployment.

Detection runs **out-of-band on a copy**. The audio does not pass through the models on its
way to the listener. If the models fail mid-call the call continues unprotected; it can
never be dropped or altered.

**Stack:** WebRTC · Python · PyTorch · WebSocket · FastAPI · React Native

---

## Audio acquisition

> **This section postdates both authoritative documents.** It records a team decision of
> **2026-09-06** and appears in neither the deck nor the report. It is not a contradiction
> to be "fixed" against them. The report's section 5 describes V1 (our own calling app,
> for the demo) and V2 (virtual-number routing, listed there under Round 2); this decision
> supersedes that framing for the acquisition layer only.

Two paths deliver call audio. They differ in nothing else.

```
Primary:   Exotel → audio stream ┐
                                 ├→ SATYACHECK backend → AI checks → risk engine → app / overlay
Fallback:  WebRTC → audio stream ┘
```

**Primary, Exotel.** Exotel is the telephony infrastructure. Incoming calls to the protected
user arrive through it, Exotel streams the call audio to our backend, and the call itself
continues normally through Exotel. The caller installs nothing.

**Fallback, WebRTC.** If the Exotel integration fails, or its call and audio streaming prove
too limited, we establish the audio channel over WebRTC and run the identical backend. This
exists so the complete system can still be demonstrated with the telephony integration down.

**The invariant.** Exotel and WebRTC are acquisition layers only. The backend, the AI checks,
the risk engine and the app contract are the same on both. Transport-specific handling stops
at ingestion (stage 02); nothing below it may branch on which transport delivered the audio.
Adding a third acquisition layer later should require no change below stage 02.

The risk result (genuine or synthetic, plus the risk level) goes to the SATYACHECK app,
which draws the warning over whatever app is in the foreground, so the user sees it mid-call
without switching apps. Identical on both paths.

**Unverified and blocking:** whether the telephony provider can stream call audio *during*
the call rather than handing over a recording afterwards. The report flags this as unchecked.
If it is recordings only, the primary path degrades to chunked near-real-time analysis and we
say so in those words rather than claiming "real time". The WebRTC fallback exists precisely
because this is open.

---

## Scope

Round 1 must exist and must demo. Round 2 is described, not built. Do not present a Round 2
item as working. This split is from report section 11, amended for acquisition by the
decision above.

| Round 1, built | Round 2, described |
|---|---|
| Audio acquisition (Exotel primary, WebRTC fallback) | Family Vault enrolment and consent flow |
| Detection model on that stream, score updating live | Transcript-based scam-script detection |
| Risk display with a clear warning state | Payment-blocking integration with a bank |
| Training pipeline with phone compression and noise built in | On-device inference |
| Evaluation on unseen data, including Indian-accented genuine speech | |
| Alert fingerprinting and the sealed record | |

Saying "this part is built, this part is designed, this part is research" reads as competent.
Implying everything works reads as untested.

---

## Training and evaluation rules

From the deck's challenge and mitigation pairs and report sections 7 and 8. These are the
difference between working and not working, not optional polish.

- **Train directly on 8 kHz G.711 and AMR-NB.** Phone compression destroys exactly the detail
  the models rely on.
- **Train on noisy audio as well as clean.**
- **Train across corpora; score only on unseen data**, never on data resembling the training set.
- **Watermark both classes or neither.**
- **Build and publish our own Indian-accent false-positive benchmark.** No existing benchmark
  covers it, and a system that cries wolf on real Indian English is worse than useless here.
- **Report cost-weighted metrics** (ASVspoof 5 standard), not a bare EER. Missing a fraud and
  annoying a real customer are not equally bad mistakes.

---

## Findings worth knowing

**Lab accuracy does not survive the real world.** Detectors reporting **2.85%** equal error
rate in the lab (Tak et al., Odyssey 2022, `arXiv:2202.12233`) degrade to **35.24%** on
real-world multilingual audio across 14 languages and 7 platforms (ML-ITW benchmark, Wuhan
University, *ID not verified*). Roughly a twelvefold increase in mistakes. That gap is the
project. The benchmark authors were blunt about the cause: bigger models did not close it,
because these systems learn the quirks of the generators they were trained against and the
world keeps producing new ones.

**Watermarking naively is worse than not watermarking.** Training where only the fakes carry
a watermark teaches the model to look for the watermark instead of for synthesis. Adding a
watermark to a real person's voice then pushed error from about **16%** to **75%**
(Fraunhofer AISEC, *ID not verified*). Watermarks go on both classes or neither.

**Noise-aware training recovers real ground.** Retraining on noisy audio recovered roughly
**10 to 15 percentage points** in the harder conditions (NTU Singapore, *ID not verified*).

**The attack works on people.** In a survey experiment with roughly **4,100** US adults,
about **16.5%** said they would comply with an AI voice scam, rising to as much as **36%** in
the relative-in-distress scenario (Harvard Kennedy School / SEAS with Meta, *ID not
verified*). Carry the caveat: US sample, stated intent, not Indian behaviour. For Indian
fraud figures use I4C, NCRP or RBI with the financial year attached, never a security
vendor's marketing page.

**The Family Vault does not prove a caller is genuine.** A clone is built to match the real
person's voiceprint; that is the objective of cloning. Three outcomes, not two: no match
(someone else claiming to be family), match but synthetic (a clone of a real family member,
the dangerous case), match and human (probably genuinely them). The vault reliably catches a
different person impersonating family; catching a clone of an enrolled person needs the
synthetic-speech check too.

Four sources above are marked *ID not verified*. A human confirms them on arXiv before any
goes on a slide. A wrong citation on a references slide is worse than a missing one.

---

## Privacy, evidence and the blockchain answer

These are product constraints, not paperwork.

- **Embeddings, never audio.** Enrolled voices are stored as numbers; the recording is
  deleted immediately and the voiceprint can be deleted on request.
- **No call recordings at rest.** Audio is analysed as it flows and then discarded.
- **Evidence layer.** Each alert event is fingerprinted (not the audio, not the transcript),
  the fingerprints are folded into a Merkle tree, and the root is published where it cannot
  be quietly rewritten. That proves a single alert existed and predates the transfer, without
  exposing any other person's call. Handed to NCRP / 1930 on request.
- **No voice data on the ledger.** Putting it there would breach DPDP data minimisation.
  Tamper-evident, not on-chain. That single sentence is the blockchain answer.
- **Voiceprints are personal data under the DPDP Act 2023.** Consent must be explicit and
  revocable, and deletion must actually delete.
- **Never add a feature that modifies the call.** No injected audio, no synthetic speech into
  the stream. Observing is defensible; altering is not.
- One model is small enough to run on the phone itself, so a version of this can work without
  sending audio anywhere. Round 2.

**Still unread:** the current TRAI and DoT positions on live voice analysis, and the current
DPDP text on biometric data. The report flags these as unverified rather than assumed. Do not
assert compliance.

---

## Impact

| Audience | What it protects |
|---|---|
| Banks and financial institutions | Fund-transfer approvals, fraud exposure |
| Enterprises and organisations | Privileged approvals, confidential calls |
| Government agencies | Trusted critical communication, public safety |
| Individuals and general public | Voice impersonation scams, users under pressure |

Social: safer and more trusted voice communication. Economic: intervention before transfers,
approvals or disclosure. Cybersecurity: a reusable AI security layer for telecom, banking,
enterprise and government voice workflows. Operational: continuous risk scoring enabling
configurable alerts, callback, MFA, escalation and workflow automation.

Cost driver is the per-minute forwarding leg, modelled per user. Buyers: banks under RBI
fraud duties, contact centres, helplines. Pilot-ready on a single bank inbound line in 6 to 9
months.

---

## The demo plan

Order matters. It decides the round.

1. A **genuine Indian-accented call**, score stays low. Proving we do not flag real people is
   the harder and more convincing half, and most teams skip it.
2. A **cloned voice** being caught.
3. Deliberately, a **badly degraded clone** where the score wobbles, then explain what we
   measured and what training recovers.

Volunteering a weakness with a number attached is the strongest move available.

---

## References

| Paper | Why it matters | Reference |
|---|---|---|
| AASIST, Jung et al., ICASSP 2022 | Main detection architecture; a tiny version runs on a phone | `arXiv:2110.01200` |
| End-to-end anti-spoofing with RawNet2, Tak et al., 2021 | Comparison baseline | `arXiv:2011.01108` |
| Spoofing detection with wav2vec 2.0 and data augmentation, Tak et al., Odyssey 2022 | The design we build on, and the lab figure | `arXiv:2202.12233` |
| ASVspoof 2021 overview, Yamagishi et al. | How far performance drops on unmatched test data | `arXiv:2109.00537` |
| ASVspoof 2021 in the wild, Liu et al., 2023 | Compression-aware training separates winners from losers | `10.1109/TASLP.2023.3285283` |
| ASVspoof 5, Wang et al., 2024 | Current evaluation standard, adversarial attacks | `arXiv:2408.08739` |
| Real-world generalisation benchmark (ML-ITW), Wuhan University | The 35.24% figure | *ID not verified* |
| Noise-aware detection and SNR benchmarks, NTU Singapore | The 10 to 15 point recovery | *ID not verified* |
| AudioSeal, ICML 2024 | The watermarking approach we reference | `arXiv:2401.17264` |
| The watermark shortcut, Fraunhofer AISEC | Why naive watermark training breaks everything | *ID not verified* |
| Automating voice phishing attacks, Harvard Kennedy School / SEAS with Meta | The compliance figures | *ID not verified* |
| Does audio deepfake detection generalize, Müller et al., 2022 | Earlier statement of the same problem | `arXiv:2203.16263` |

**Research gap we claim:** existing work focuses on spoofing and deepfake detection in
isolation. We extend it into a real-time security framework combining voice authenticity,
conversational context, dynamic risk scoring, temporal analysis and intervention.

---

## Roles

Each teammate opens their role file, reads it, and pastes the "Start here" block into
their coding agent. See [`roles/ROLES.md`](roles/ROLES.md) for the index.

---

## Documents

| Document | Contents |
|---|---|
| SIH 2026 idea presentation (deck) | **Authoritative**: solution, technical approach, feasibility, impact, references |
| SIH 26104 project report | **Authoritative**: full architecture, research findings, scope split, glossary, reading list |
| `AGENTS.md` | Instructions for coding agents |
| `CLAUDE.md` | Claude Code specifics; imports `AGENTS.md` |
| `GEMINI.md` | Gemini CLI / Antigravity pointer to `AGENTS.md` |

The deck and the report are not committed to this repo and are not edited by agents.

---

## Maintaining this file

1. **The deck and the report win.** If this file contradicts either, this file is wrong, so
   fix it. If a change would contradict them, stop and say so; a human corrects those. The
   one exception is the acquisition decision above, which postdates both.
2. **Never add a number this repo did not produce**, and never a claim neither document
   supports. Figures under Findings carry a source, and *ID not verified* markers stay until
   a human removes them.
3. **Repo state goes in its own section, labelled as such.** What is built, what is broken,
   the environment, folder ownership and test counts are not claims from the deck or the
   report and must not read as if they were.
4. **A status only moves to "working" when a test proves it.** Name the test in the commit
   message.
5. Update in the same commit as the change, not afterwards.
6. Do not add badges, a roadmap, an acknowledgements section, or a features list duplicating
   the tables above.

## Repo state (not claims from the deck or the report)

The following describes the repository layout and ownership as of this commit. It is not a
claim from the deck or the report.

### Layout and ownership

| Directory | Owner | Contents |
|---|---|---|
| `contracts/` | Backend lead (editor) / all review | Schema-only Pydantic types for the seven-stage pipeline |
| `acquisitions/exotel/` | Flex E | Exotel SDK to AudioChunk |
| `acquisitions/webrtc/` | Flex E | WebRTC/RTP to AudioChunk (fallback) |
| `backend/app/ingestion/` | Backend lead | Stage 02: decode and normalize to CanonicalAudioChunk |
| `backend/app/pipeline/` | Backend lead | Stage 03: buffer, silence filter |
| `backend/app/fusion/` | Backend lead | Stage 05: risk fusion engine |
| `backend/app/response/` | Backend lead | Stage 06: WebSocket dispatch of AppMessage |
| `backend/app/evidence/` | Flex F | Stage 07: alert fingerprint, Merkle |
| `ml/checks/machine_fingerprint/` | ML A | XLS-R + AASIST check |
| `ml/checks/speaker_identity/` | ML A | ECAPA-TDNN check |
| `ml/checks/prosody/` | ML B | openSMILE check |
| `ml/checks/stt_llm/` | ML B | STT then LLM check |
| `ml/runner/` | ML B | CheckRunner (180 ms deadline) |
| `app/` | RN/Expo lead | React Native + Expo overlay |
| `docs/` | Backend lead | interfaces.md (single written source of truth) |
| `tests/` | Backend lead | transport invariant + contracts smoke |

### Environment

- Python 3.13.15 (pinned via `.python-version`, managed by uv)
- Node v22.23.2, npm 11.12.1
- uv 0.12.1 for dependency management

### Tests

Two tests exist and pass:
- `tests/test_contracts_smoke.py` (8 tests): import verification, JSON round-trips, framing rules
- `tests/test_transport_invariant.py` (2 tests): AST-walk enforcement of the transport invariant

Run: `uv run pytest tests/ -q`
