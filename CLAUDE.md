# CLAUDE.md

@AGENTS.md

Everything above applies. Claude Code specifics below.

## Skills

This repo uses three custom skills. Reach for them by name:

- `tdd` — any behaviour change in `nlp_rag/` or `audio_ml/`. Failing test first.
- `git-guardrails` — before any commit. It is the only thing standing between us and a
  cross-folder commit.
- `grill-me` — before declaring a module done, and before anything goes on a slide.

## Working style

- **Definition of done (AGENTS.md) is mandatory.** Every turn that changes code ends with
  the module smoke test actually run and its result reported, and any doc the change
  contradicts (`README.md`, module docstring/README, `AGENTS.md`) updated in the same
  turn. Code with no test run and no doc touched is an unfinished turn, not a handoff.
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

## Output

Code and diffs, not explanations of code. If an explanation is genuinely needed, three
sentences after the diff, not before it.

Do not end a turn with a question when the next step is obvious. Do the obvious step.
