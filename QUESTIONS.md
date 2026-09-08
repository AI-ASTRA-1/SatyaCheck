# Questions

Blocked on something your self-check and fallback did not resolve? Append a question
below using the format from `roles/ROLES.md`. R2 answers once a day.

---

## R1 (ML) - 2026-09-07

**Blocked on:** Nothing. This is the ML confirmation of the open decision in
`docs/interfaces.md` section 10, so R2 can close it.
**What I tried:** Checked the input specification of every model in the four checks.
XLS-R / wav2vec2, ECAPA-TDNN and local STT all take 16 kHz mono. `CANONICAL_SAMPLE_RATE
= 16000` is correct and needs no change.
**What I need:** R2 to mark that decision confirmed. One caveat travels with it, and
it belongs in the prose rather than the constant: telephony audio upsampled from
8 kHz carries no energy above 4 kHz, so the models have to be trained through exactly
that path. That is a training requirement on R1, not a contract change.

## R1 (ML) - 2026-09-07

**Blocked on:** `README.md` Repo state now understates the test count, and I may not
edit it.
**What I tried:** Added the machine fingerprint check with 15 tests under `ml/tests/`.
`.venv\Scripts\python.exe -m pytest ml tests -q` reports 25 passed. Repo state still
says "Two tests exist and pass" and lists only R2's two suites.
**What I need:** R2 to update the Repo state Tests section, and to note that ML tests
live under `ml/` because `tests/` is R2's folder. `ml/README.md` carries the ML side.
Current count is 40 passed across `ml` and `tests`. Repo state also records uv 0.12.1;
the installed version is now 0.12.10.

## R1 (ML) - 2026-09-07

**Blocked on:** `pyproject.toml` does not record where the CUDA torch wheels come
from, and it is not R1's file.
**What I tried:** Installed with
`uv pip install --system-certs --index-url https://download.pytorch.org/whl/cu128 torch torchaudio`,
giving torch 2.11.0+cu128 with CUDA working on Python 3.13.15. The default PyPI wheel
on Windows is CPU-only, so a fresh `uv sync --extra ml` on another machine silently
installs a build that cannot train. `--system-certs` is also required here because
something intercepts TLS and uv's bundled certificate store rejects the issuer.
**What I need:** The cu128 index recorded in `pyproject.toml` so the ML environment is
reproducible off this machine, and a note that `--system-certs` is required here.

## R1 (ML) - 2026-09-08 - AFFECTS WHAT THE DEMO AND DECK MAY CLAIM

**Blocked on:** Nothing technical. This is a measurement the whole team needs before
the demo, because it changes what we can honestly say on stage.

**What I tried:** Built the phone-channel augmentation (G.711, AMR-NB, Opus, gain,
noise), fine-tuned AASIST on the full ASVspoof 2019 LA train split through it, and
scored the result three ways.

Result: the fine-tuned model is **excellent in-domain and unusable on our own
recordings**.

- ASVspoof dev EER through the phone channel: 17.50% to 6.29%.
- ASVspoof held-out eval, unseen attacks A07-A19: bonafide median 0.000, spoof
  median 0.999. Clean separation.
- The same checkpoint on our three genuine Indian-accented phone recordings: 0.935,
  0.803, 1.000. All three flagged as synthetic. One is tied with the TTS.

Fine-tuning made ASVspoof better and our own recordings **worse**. The residual gap
is not the phone channel, which is what the augmentation addressed; it is speaker and
recording domain. The model has learned that bonafide means audio resembling ASVspoof
bonafide, which is clean studio-recorded, largely Western-accented English.

**What I need, three things:**

1. **Demo item 1 does not currently work** ("a genuine Indian-accented call, score
   stays low"). Whoever is scripting the demo needs to know now, not on stage. The
   deck's own thesis, the 2.85% to 35.24% generalisation gap, is exactly what we
   reproduced, so the honest version of the demo is strong. But it is a different
   demo.
2. **One clean recording decides which demo we give.** Our three recordings are
   Indian-accented *and* lossy phone captures with device processing probably on.
   If recording quality is the cause, clean capture fixes it. If accent and speaker
   domain, nothing about capture helps. Sixty seconds of clean audio answers it.
3. **No claim of a working detector may go on a slide** until the above resolves.
   Under `AGENTS.md` "how we are allowed to describe this", we can say we raise a
   warning, we reproduced the published model, and we measured where it fails. We
   cannot say it detects cloned voices on Indian phone audio, because we measured
   that it does not.

Everything is written up in `ml/README.md` under Findings, with the numbers and the
methodology.

## R1 (ML) - 2026-09-07 - PRIVACY, please action

**Blocked on:** The root `.gitignore` does not stop real voice recordings being
committed, and `.gitignore` is not R1's file.
**What I tried:** Three team recordings arrived as `.mp4` and `.mpeg`. The root
ignore list covers `*.wav`, `*.mp3`, `*.flac`, `*.opus` and `*.amr`, but not the
video-container extensions phone recorders actually produce, so `git status` listed
them as trackable and a `git add .` would have committed them. `AGENTS.md` forbids
committing real audio, and these are identifiable people who consented to a
recording session, not to publication. Added `ml/.gitignore` covering `*.mp4`,
`*.mpeg`, `*.m4a`, `*.aac`, `*.ogg`, `*.webm`, `*.3gp` and friends, which protects
this machine. The root `.gitignore` ignores nested `.gitignore` files, so mine will
never reach anyone else.
**What I need:** The same patterns added to the root `.gitignore`, so every machine
is covered rather than just this one. Until then, anyone who pulls this repo and
drops an `.mp4` recording into it can commit it by accident.

## R1 (ML) - 2026-09-07

**Blocked on:** Nothing, but `ml/runner/` is R2's folder and needs a one-line change
or the 180 ms budget is missed on the first scoring tick of every call.
**What I tried:** Model loading is lazy, so the first scored window costs about 2 s
for AASIST and longer for XLS-R, against warm costs of 13 to 16 ms and 27 to 37 ms
respectively. Added `warmup()` to the `SyntheticScorer` protocol and implemented it on
both scorers; it loads the model and runs one throwaway window.
**What I need:** The stage 04 runner to call `warmup()` on every check at startup,
before any call is accepted. R1 exposes it, R2 wires it.

## R1 (ML) - 2026-09-07

**Blocked on:** `transformers` is declared in the `ml` extra but numpy, speechbrain,
opensmile and faster-whisper are not, and `pyproject.toml` is not R1's file.
**What I tried:** Installed numpy and transformers into the venv directly. speechbrain,
opensmile and faster-whisper are approved by the ML lead but not yet installed.
**What I need:** R2 to decide whether the cu128 index belongs in `pyproject.toml`
(a `[tool.uv.sources]` entry or an index declaration) so the ML environment is
reproducible, and whether numpy should join the `ml` extra. numpy is installed and in
use by `ml/` now.

