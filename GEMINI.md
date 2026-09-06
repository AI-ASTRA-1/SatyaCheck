# GEMINI.md

Project context for Gemini CLI and Google Antigravity.

Read **`AGENTS.md` in the repo root** — it is the single source of truth for ownership,
environment, architecture, settled facts, and constraints. This file only adds
tool-specific notes.

Above AGENTS.md sit the **SIH deck and the project report**. They are authoritative for
scope, architecture, numbers and claims; anything contradicting them is wrong and gets
fixed. Agents do not edit those two documents.

To load AGENTS.md automatically instead of duplicating it, set in your Gemini CLI
settings:

```json
{ "context": { "fileName": ["AGENTS.md", "GEMINI.md"] } }
```

Antigravity also scans `.agents/` — if you keep a copy there, symlink it rather than
forking the content. Two drifting instruction files is worse than none.

---

## Antigravity specifics

- **Do not run the browser or web-search tools for anything in this repo.** Model names,
  thresholds and metrics are pinned in AGENTS.md; searching produces plausible-looking
  numbers that then end up in a slide. This includes the four citations marked *ID not
  verified* — a human confirms those on arXiv, not you.
- **Follow the Definition of done in AGENTS.md.** A code change is delivered only with the
  module smoke test run and its result reported, and the matching committed doc
  (`README.md`, module docstring/README, AGENTS.md) updated in the same change.
- **Round 1 scope only.** Virtual-number routing, Family Vault, transcript scam-script
  detection, payment blocking and on-device inference are Round 2 — described, not built.
- Artifacts (plans, walkthroughs) are for you, not for us. They do not count as the doc
  update — the committed README or docstring does. Do not commit artifacts.
- The sandbox is not our environment. Anything that runs there must also run on
  **Python 3.14.7** locally — see the Environment section of AGENTS.md before installing.
- Context compaction triggers around 135k tokens. Before a long task, state which folder
  you own for that task, so it survives compaction.

## Claims discipline

These outlive compaction because they are the ones that get us marked down:

- We **warn**; we do not "detect deepfakes". The human decides.
- Detection in the real world is unsolved. Lab **2.85%** becomes **35.24%** on real-world
  multilingual audio. Lead with that gap.
- Matching the Family Vault does **not** prove a caller is genuine — a clone is built to
  match the voiceprint.
- No voice data on a ledger. Tamper-evidence anchors only.
- Never write "real time" if the audio only arrives as recordings.

## Multi-agent / persona pipelines

If you use `.agents/` personas, every persona inherits the ownership table. A "backend"
persona still may not edit `nlp_rag/`. Ownership is per-folder, not per-role.

## Token discipline

- No preamble, no restating the request, no summary of completed work unless asked.
- Do not echo file contents you just wrote.
- One task per turn.
- Uncertain → one clause saying so. Never fabricate an API, flag, or metric.
