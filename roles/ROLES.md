# Role briefs

Each teammate opens their own file, reads it, and pastes the "Start here" block into
their coding agent. No coordination needed to start. Work proceeds in your folder; do
not edit anyone else's.

| File | Role | Folder owned |
|---|---|---|
| [R1.md](R1.md) | ML | `ml/checks/`, augmentation, calibration, benchmark |
| [R2.md](R2.md) | Backend | `contracts/`, `backend/app/`, `ml/runner/`, `tests/`, `docs/` |
| [R3.md](R3.md) | Acquisition | `acquisitions/` |
| [R4.md](R4.md) | RN/Expo app | `app/` |
| [R5.md](R5.md) | Web dashboard A | `web/dashboard-a/` |
| [R6.md](R6.md) | Web dashboard B | `web/dashboard-b/` |

R2 owns the evidence layer and the runner. There is no separate owner for either.
R2 reviews all PRs and answers QUESTIONS.md once a day.

## QUESTIONS.md

If you are blocked and your self-check and fallback did not help, append a question
to `QUESTIONS.md` at the repo root. Use this format:

```
## [your name] - [date]

**Blocked on:** one sentence
**What I tried:** what you already attempted
**What I need:** who should answer, or what fact is missing
```

R2 answers questions once a day. Do not wait; switch to the fallback task listed in
your role file and check back.

## Rules that apply to everyone

- Edit only your own folder. An agent that touches another folder breaks someone
  else's work without warning.
- Do not edit `contracts/` unless you are R2. Contracts are the shared interface; R2
  reviews all contract changes.
- Do not add dependencies without asking.
- Do not commit real audio, voiceprints, `.env`, keys, or evaluation data.
- No em dashes in prose.
