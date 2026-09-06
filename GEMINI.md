# GEMINI.md

Project context for Gemini CLI and Google Antigravity.

Read **`AGENTS.md` in the repo root**. It is the single source of truth for architecture,
scope, settled facts, claims discipline and constraints. This file only adds tool-specific
notes.

Above `AGENTS.md` sit the **SIH deck and the project report**. They are authoritative for
scope, architecture, numbers and claims; anything contradicting them is wrong and gets fixed.
Agents do not edit those two documents.

**Exception:** the Exotel/WebRTC acquisition decision (2026-09-06) postdates both and appears
in neither. `AGENTS.md` "Audio acquisition" is the authority there. Do not "correct" it
against the deck, and do not search the web for Exotel capabilities; that check is a human
task against Exotel's own documentation.

**Gap you must not fill by guessing:** `AGENTS.md` deliberately carries no repo state, because
repo state is in neither authoritative document. It does not tell you which modules work, what
the Python version is, who owns which folder, or how many tests exist. Silence there is not
permission to assume. Read the code, and say so before starting if a task depends on an
environment fact you cannot verify.

To load `AGENTS.md` automatically instead of duplicating it, set in your Gemini CLI settings:

```json
{ "context": { "fileName": ["AGENTS.md", "GEMINI.md"] } }
```

Antigravity also scans `.agents/`. If you keep a copy there, symlink it rather than forking the
content. Two drifting instruction files is worse than none.

---

## Antigravity specifics

- **Do not run the browser or web-search tools for anything in this repo.** Model names,
  budgets and metrics are pinned in `AGENTS.md`; searching produces plausible-looking numbers
  that then end up in a slide. This includes the four citations marked *ID not verified*: a
  human confirms those on arXiv, not you.
- **Follow the Definition of done in `AGENTS.md`.** A code change is delivered only with the
  module smoke test run and its result reported, and the matching committed doc updated in the
  same change.
- **Round 1 scope only.** Family Vault, transcript scam-script detection, payment blocking and
  on-device inference are Round 2, described and not built. Call acquisition (Exotel primary,
  WebRTC fallback) is Round 1.
- **The transport is not the pipeline.** Exotel and WebRTC are swappable acquisition layers
  feeding one unchanged backend. Nothing below ingestion may import a transport symbol or
  branch on which transport delivered the audio.
- Artifacts (plans, walkthroughs) are for you, not for us. They do not count as the doc
  update; the committed README or docstring does. Do not commit artifacts.
- The sandbox is not our environment. Verify anything you install against the local
  environment before relying on it.
- Context compaction triggers around 135k tokens. Before a long task, state which area you are
  working in, so it survives compaction.

## Claims discipline

These outlive compaction because they are the ones that get us marked down:

- We **warn**; we do not "detect deepfakes". The human decides. The problem statement title
  uses the word detection; that is the PS wording, not a claim about our output.
- Detection in the real world is unsolved. Lab **2.85%** becomes **35.24%** on real-world
  multilingual audio. Lead with that gap.
- Matching the Family Vault does **not** prove a caller is genuine; a clone is built to match
  the voiceprint. Three outcomes, not two.
- No voice data on a ledger. Tamper-evidence anchors only, because voice on-chain would breach
  DPDP data minimisation.
- Never write "real time" if the audio only arrives as recordings. Whether the telephony
  provider streams audio mid-call is still unconfirmed, so this is a live risk, not a
  hypothetical.
- The four *ID not verified* sources stay marked until a human clears them.

## Multi-agent and persona pipelines

If you use `.agents/` personas, every persona inherits the same rules. A persona is not a
licence to widen scope, skip the Definition of done, or make a claim the deck and the report
do not support.

## Token discipline

- No preamble, no restating the request, no summary of completed work unless asked.
- Do not echo file contents you just wrote.
- One task per turn.
- Uncertain, then one clause saying so. Never fabricate an API, flag, or metric.
- No em dashes.
