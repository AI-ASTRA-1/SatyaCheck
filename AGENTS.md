# SATYACHECK, agent instructions

Real-time warning on AI-cloned voices during live calls.
SIH 2026 · Problem Statement **SIH26104** · Theme Blockchain & Cybersecurity · PS Category
Software · Team **AI ASTRA**.
*Real Voice. Real Person. Real-Time Protection.*

**The deck and the project report are the source of truth for scope, architecture, numbers
and claims.** Where this file, `README.md`, or any code comment disagrees with them, they win
and the file is wrong, so fix the file. Do not invent a fact that appears in neither.

**What this file deliberately does not contain.** Repo state: what is built, what is broken,
the Python environment, folder ownership, frozen files, thresholds and test counts. Those are
not claims from the deck or the report. If the team wants them here, a human adds them in a
clearly separated "Repo state" section. Until then, do not infer them, and do not assume a
module works because this file does not say it is broken. Check the code.

---

## Response rules

- Answer in the fewest tokens that fully answer. No preamble, no recap of the request, no
  summary of what you just did unless asked.
- Do not restate code you just wrote. A diff or a filename is enough.
- No "Great question", no "You're absolutely right", no emoji.
- Uncertain, then say so in one clause and move on. Never invent an API, a flag, or a metric.
- Disagree when the instruction is wrong. Say why once, then do it their way if they repeat it.
- Read before you write. Never propose an edit to a file you have not opened in this session.
- No em dashes in prose you write into this repo.

## Never do

- `git push`, force-push, rebase a shared branch, or amend a pushed commit.
- Add a dependency without asking.
- Weaken, skip, or `xfail` a test to make a suite pass. Report the failure.
- Commit real audio, voiceprints, `.env`, keys, or held-out evaluation data.
- Write a number into a doc, README, or slide that no test or logged run produced.
- Write a claim the deck or the report does not support. See the next section.
- Hand back a code change with the tests unrun or the docs stale. See Definition of done.

---

## How we are allowed to describe this

The report is explicit that overclaiming is the fastest way to lose this. These are wording
rules, not style preferences.

- **Never "our system detects deepfakes."** It raises a warning; the human decides. The
  problem statement title and the deck use the word detection; that is the PS wording, not a
  claim about our output.
- **Never "solved."** Detecting synthetic speech in the real world is an unsolved research
  problem. Report section 8 leads with that gap rather than hiding it.
- **Never "real time" if the audio arrives as recordings.** If the provider cannot stream
  during the call, we degrade to near-real-time chunked analysis and say so in those words.
- **We analyse sound, not words.** A transcript is useless for spotting a fake voice; the
  giveaways live in the audio and are destroyed by speech-to-text. We read the transcript
  too, for the separate purpose of scam-script detection.
- **The scammer installs nothing.** The person being protected opts in. The attacker's
  cooperation is never required.
- **Matching the Family Vault does not prove a caller is genuine.** A clone is built to match
  the voiceprint.
- Current status is **a controlled live-warning prototype. Real-world deployment after
  validation.**
- Figures marked *ID not verified* are not confirmed. Do not present them as confirmed, and
  do not go looking for confirmation on the web; a human checks them on arXiv.

---

## Architecture, seven stages

```
call source → audio ingestion → live pipeline → four AI checks → risk fusion → response → evidence
```

| Stage | Contents | Budget |
|---|---|---|
| 01 Call source | See Audio acquisition | |
| 02 Audio ingestion | Unpacking, codec handling (Opus / G.711 / AMR), 20 ms frames | |
| 03 Live pipeline | WebSocket, short buffer (Redis Streams), silence filtering | under 20 ms |
| 04 Four AI checks | In parallel, on a copy | under 180 ms |
| 05 Risk fusion | AI signals plus number, location, time, past history, into 0 to 100 | under 30 ms |
| 06 Response | Warning, SMS or escalation, stop the payment or force call-back or second factor | under 50 ms |
| 07 Evidence | Alert fingerprint, sealed record, NCRP / 1930 | |

Spoken word to warning on screen: **under 400 ms, p90**. A virtual-number bridge adds roughly
**100 to 330 ms**.

Four checks, in parallel, on a **copy** of the audio:

| Check | Model | Answers |
|---|---|---|
| Machine fingerprints | XLS-R + AASIST | is the waveform synthetic |
| Speaker identity | ECAPA-TDNN | is this who they claim |
| Rhythm and pitch | openSMILE | prosodic anomaly |
| What is being said | speech-to-text then language model | scam script pattern |

Report section 4 groups these as three signal families; section 6 and the deck both show the
four checks above. XLS-R carries the multilingual front end (Hindi, English, Tamil, Marathi,
Bengali and more). AASIST-L (~85K params) runs on CPU. All inference is local, no external
API to fail on demo day. Models are open source with public checkpoints, nothing to license.

**Models emit evidence. The risk engine owns the decision.** No module returns a final
security verdict; each returns structured signals plus what justifies them.

Three rules the risk engine must keep:

- **Continuous scoring.** The score updates throughout the call, roughly once a second, never
  a single decision at the start.
- **Call context is part of fusion**, alongside the model signals.
- **Policy rules are per customer.** A bank is not a family. The 0 to 100 score is the output;
  what it triggers is configurable per deployment.

Detection runs **out-of-band on a copy**. The audio does not pass through the models on its
way to the listener. A model failure degrades to "no warning", never to a dropped or altered
call.

**Stack (deck, slide 3):** WebRTC · Python · PyTorch · WebSocket · FastAPI · React Native.

---

## Audio acquisition, Exotel primary and WebRTC fallback

**Team decision recorded 2026-09-06. It appears in neither the deck nor the report, and this
section is the authority for it.** It is not a contradiction to be "fixed" against those
documents. It supersedes the report's section 5 framing (V1 our own calling app, V2
virtual-number routing) for the acquisition layer only, and moves acquisition into Round 1,
where the report had placed virtual-number routing in Round 2. Everything else in sections 5
and 11 stands.

```
Primary:   Exotel → audio stream ┐
                                 ├→ SATYACHECK backend → AI checks → risk engine → app / overlay
Fallback:  WebRTC → audio stream ┘
```

- **Primary, Exotel.** Exotel is the telephony infrastructure. The protected user's incoming
  calls arrive through it; Exotel streams the call audio to our backend while the call itself
  continues normally through Exotel. The caller installs nothing.
- **Fallback, WebRTC.** If the Exotel integration fails, or its streaming turns out to be
  limited in ways we cannot work around, we establish the audio channel over WebRTC and run
  the identical backend, so the complete system can still be demonstrated end to end.

### The invariant

**The backend, the AI checks, the risk engine and the app contract do not change between
paths.** Both transports terminate at the same audio-stream interface. Enforceable in review:

- No model, scoring, fusion or reason-code module may import a transport symbol, branch on
  which transport delivered the audio, or read a transport-specific field.
- Transport-specific handling stops at ingestion (stage 02).
- A change that makes one path behave differently from the other is a bug, unless the
  difference is a documented codec or sample-rate property of the transport itself.
- Adding a third acquisition layer later must require no change below stage 02. If it would,
  the boundary has already leaked.

### Delivery back to the user

The risk result (genuine or synthetic, plus risk level) goes to the SATYACHECK app, which
draws the warning over whatever application is in the foreground, so the user sees it during
the call without switching apps. Same on both paths.

### Business shape

The per-minute forwarding leg is the cost driver, modelled per user. Buyers: banks under RBI
fraud duties, contact centres, helplines. Pilot-ready on a single bank inbound line in 6 to 9
months.

---

## Scope, build Round 1 and describe Round 2

Report section 11, amended for acquisition by the decision above. Do not build a Round 2 item,
and do not present one as working.

| Round 1, must exist and must demo | Round 2, described not built |
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

## Facts that are settled, do not re-derive or contradict

- **The generalisation gap is the project.** Lab 2.85% becomes 35.24% on real-world
  multilingual audio. Lead with it.
- **Phone compression destroys the detail the models rely on.** Train through it.
- **Watermarks go on both classes or neither.** Training where only fakes carry a watermark
  teaches the model to look for the watermark instead of for synthesis.
- **The Family Vault does not prove a caller is genuine.** Three outcomes, not two: no match
  (a different person impersonating family), match but synthetic (a clone of an enrolled
  person, the dangerous case), match and human. Never write "we store family voices so we can
  detect fakes."
- **No voice data on a ledger.** Only tamper-evidence anchors. Putting voice on-chain would
  breach DPDP data minimisation; that sentence is the blockchain answer.
- **The acquisition layer is swappable; the backend is not.**
- **Roughly 30 seconds of audio is enough to clone a voice.** The score updates roughly once a
  second.

---

## Open questions, do not assume and do not paper over

The report flags these as unverified. Each is blocking for any claim built on it.

- **Can the telephony provider stream call audio during the call**, not just hand over a
  recording afterwards? Unconfirmed against current documentation. The primary path rests on
  it. If it is recordings only, that path degrades to chunked near-real-time analysis and we
  say so in those words. The WebRTC fallback is the mitigation, not a second product.
- **TRAI and DoT positions** on live voice analysis: specific clauses unread. Do not assert
  compliance.
- **Current DPDP text on biometric data**: flagged in the report as needing a human read.
- **Bridge cost and delay** are real line items, not rounding errors.
- **Four citations are marked *ID not verified*.** A human looks these up on arXiv. This is
  not an agent web-search task. A wrong citation on a references slide is worse than a
  missing one.

---

## Training data and evaluation rules

From the deck's challenge and mitigation pairs and report sections 7 and 8.

- **Train directly on 8 kHz G.711 and AMR-NB.** Push training audio through phone-quality
  compression before the model sees it.
- **Train on noisy audio too.** Retraining on noise recovered roughly 10 to 15 percentage
  points in the harder conditions.
- **Train across corpora, score only unseen data.** Never report a figure measured on data
  resembling the training set.
- **Watermark both classes or neither.**
- **Build and publish our own Indian-accent false-positive benchmark.** No existing benchmark
  covers it.
- **Report cost-weighted metrics** (ASVspoof 5 standard), not a bare EER.

---

## Definition of done

A code change is not finished until all three are true. Do not open a commit, or call a task
complete, with any of them missing.

1. **Code.** The change itself, smallest diff that works.
2. **Tests run.** Actually execute them, do not reason about whether they would pass. Run the
   smoke test for every module you touched; run the full suite if you changed a contract or a
   shared helper. Report the outcome: pass count, or the failing test and its output. New
   logic ships with its test in the same change; a bug fix ships with the failing test written
   first. If you cannot run the tests, say so in one clause. Never imply they passed.
3. **Docs updated.** If the change touches behaviour, a public function or its signature, a
   flag, a threshold, a CLI command, a dependency, or an architecture decision, update the doc
   that describes it in the *same* change. If the change contradicts the deck or the report,
   stop and say so; those are corrected by a human, not by an agent. A doc that now
   contradicts the code is a regression, not a follow-up.

---

## The demo plan, this decides the round

Order matters.

1. A **genuine Indian-accented call**, score stays low. Proving we do not flag real people is
   the harder and more convincing half; most teams skip it.
2. A **cloned voice** being caught.
3. Deliberately, a **badly degraded clone** where the score wobbles, then explain what we
   measured and what training recovers.

Volunteering a weakness with a number attached is the strongest move available.

---

## Git

- Commit small, present tense, no scope creep.
- Never push. Leave the commit local and say it is ready.

---

## Privacy and legal, product constraints not paperwork

- Store **embeddings, never audio.** Enrolment audio is deleted immediately after the
  voiceprint is made, and the voiceprint is deletable on request.
- **No call recordings at rest.** Analysis is in-flight.
- **Evidence layer:** fingerprint each alert event, fold the fingerprints into a Merkle tree,
  publish the root where it cannot be quietly rewritten. This proves a single alert existed
  and predates the transfer, without exposing any other person's call. No audio, no
  transcript, no voice data on the ledger. Handed to NCRP / 1930 on request.
- **Voiceprints are personal data under the DPDP Act 2023.** Consent explicit and revocable;
  deletion must actually delete.
- Our legal basis is one-party consent: our user is a genuine call participant. **Never add a
  feature that modifies the call** (injected audio, synthetic speech into the stream).
  Observing is defensible; altering is not.

---

## Where the numbers live

Every figure the deck and the report use, with its source. Do not quote any other figure, and
do not drop the caveats.

**Verified IDs**

- Lab EER **2.85%** (ASVspoof 2021 DF), Tak et al., Odyssey 2022, `arXiv:2202.12233`
- AASIST-L **~85K params**, runs on CPU, Jung et al., ICASSP 2022, `arXiv:2110.01200`
- RawNet2 baseline, Tak et al., 2021, `arXiv:2011.01108`
- ASVspoof 2021 overview, Yamagishi et al., `arXiv:2109.00537`
- ASVspoof 2021 in the wild, Liu et al., 2023, `10.1109/TASLP.2023.3285283`
- ASVspoof 5, current evaluation standard, Wang et al., 2024, `arXiv:2408.08739`
- AudioSeal, localized watermarking, ICML 2024, `arXiv:2401.17264`
- Does audio deepfake detection generalize, Müller et al., 2022, `arXiv:2203.16263`

**ID not verified, confirm before any of these goes on a slide**

- Real-world EER **35.24%** (14 languages, 7 platforms), ML-ITW benchmark, Wuhan University.
  The 2.85% to 35.24% gap is the project.
- Watermark error **16% to 75%**, Fraunhofer AISEC.
- Noisy-training recovery of **10 to 15 percentage points**, NTU Singapore.
- Voice-scam compliance **16.5%** overall, up to **36%** in the relative-in-distress scenario,
  n roughly 4,100, Harvard Kennedy School / SEAS with Meta. **Caveat that travels with the
  number:** US sample, stated intent, not Indian behaviour. For Indian fraud figures use I4C,
  NCRP or RBI with the financial year attached, never a security vendor's marketing page.

**Other figures stated in the documents:** roughly 30 seconds of audio is enough to clone a
voice; the score updates roughly once a second; a virtual-number bridge adds roughly 100 to
330 ms; pilot-ready on a single bank inbound line in 6 to 9 months.

Anything else is unverified. Say "no verified source" rather than guessing.
