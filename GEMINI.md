# GEMINI.md

Project context for Gemini CLI and Google Antigravity.

Read **`AGENTS.md` in the repo root** — it is the single source of truth for ownership,
environment, architecture, settled facts, and constraints. This file only adds
tool-specific notes.

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
  numbers that then end up in a slide.
- **Follow the Definition of done in AGENTS.md.** A code change is delivered only with the
  module smoke test run and its result reported, and the matching committed doc
  (`README.md`, module docstring/README, AGENTS.md) updated in the same change.
- Artifacts (plans, walkthroughs) are for you, not for us. They do not count as the doc
  update — the committed README or docstring does. Do not commit artifacts.
- The sandbox is not our environment. Anything that runs there must also run on
  **Python 3.14.7** locally — see the Environment section of AGENTS.md before installing.
- Context compaction triggers around 135k tokens. Before a long task, state which folder
  you own for that task, so it survives compaction.

## Multi-agent / persona pipelines

If you use `.agents/` personas, every persona inherits the ownership table. A "backend"
persona still may not edit `nlp_rag/`. Ownership is per-folder, not per-role.

## Token discipline

- No preamble, no restating the request, no summary of completed work unless asked.
- Do not echo file contents you just wrote.
- One task per turn.
- Uncertain → one clause saying so. Never fabricate an API, flag, or metric.
