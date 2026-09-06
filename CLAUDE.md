# CLAUDE.md

@AGENTS.md

Everything above applies. Claude Code specifics below.

## The deck and the report win

The SIH deck and the project report are authoritative for scope, architecture, numbers
and claims. If code, `README.md`, or `AGENTS.md` contradicts them, the file is wrong —
fix the file. If a *change you are asked to make* would contradict them, stop and say so;
those two documents are corrected by a human, not by an agent.

**One exception, and it is deliberate:** the Exotel/WebRTC acquisition decision
(2026-09-06) postdates both documents and appears in neither. The "Audio acquisition"
section of AGENTS.md is the authority for it. Do not "correct" it against the deck.

## Skills

This repo uses three custom skills. Reach for them by name:

- `tdd` — any behaviour change in `nlp_rag/` or `audio_ml/`. Failing test first.
- `git-guardrails` — before any commit. It is the only thing standing between us and a
  cross-folder commit.
- `grill-me` — before declaring a module done, and before anything goes on a slide.
  Check the claim against the "How we are allowed to describe this" rules in AGENTS.md
  before you check anything else.

## Working style

- **Definition of done (AGENTS.md) is mandatory.** Every turn that changes code ends with
  the module smoke test actually run and its result reported, and any doc the change
  contradicts (`README.md`, module docstring/README, `AGENTS.md`) updated in the same
  turn. Code with no test run and no doc touched is an unfinished turn, not a handoff.
- **Never couple the pipeline to the transport.** Exotel and WebRTC are interchangeable
  acquisition layers feeding one unchanged backend. If a diff makes a model, scoring,
  fusion or reason-code module import a transport symbol, branch on which transport
  delivered the audio, or read a transport-specific field, that is the bug — say so
  rather than writing it. Transport handling stops at ingestion.
- **Round 1 only.** Family Vault, transcript scam-script detection, payment blocking and
  on-device inference are Round 2 — described, not built. Asked to build one, say it is
  out of scope for this round before starting. Call acquisition (Exotel primary, WebRTC
  fallback) is Round 1.
- **Plan before multi-file edits.** One paragraph, then wait. Do not start editing across
  three files and narrate as you go.
- **One task per turn.** If the request contains two, do the first and name the second.
- Prefer `str_replace` over rewriting a file. Whole-file rewrites lose C's formatting and
  produce unreviewable diffs.
- When a tool call fails, read the error before retrying. Do not retry the same call twice.
- Long sessions drift. If you are unsure what state a file is in, re-read it.

## What to push back on

Say so plainly, once:

- A number requested for the deck that no run produced.
- A feature that would inject audio into a live call.
- "Just make the test pass."
- A dependency install to work around the Python 3.14 issue — flag the version mismatch
  instead; installing over it has burned time before.
- Wording that says we **detect** deepfakes rather than **warn**, or that implies the
  problem is solved. Report §8 is the whole reason we lead with the 2.85% → 35.24% gap.
- "Matching the Family Vault proves the caller is real." It does not — a clone is built
  to match the voiceprint.
- Quoting the Harvard 16.5% / 36% figure without its caveat, or any of the four sources
  marked *ID not verified* as if confirmed.

## Output

Code and diffs, not explanations of code. If an explanation is genuinely needed, three
sentences after the diff, not before it.

Do not end a turn with a question when the next step is obvious. Do the obvious step.
