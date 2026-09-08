# ML workstream, repo state

Repo state, not a claim from the deck or the report. Owner R1. What is built, what
is a stub, and what the environment can currently do.

## Status

| Component | State |
|---|---|
| `checks/machine_fingerprint/` | Check layer plus two scorers: `SslAasistScorer` (XLS-R + AASIST, the architecture the deck describes, default) and `AasistScorer` (AASIST alone, CPU comparison). Runs end to end through `ml/tools/score_file.py`. Neither pretrained checkpoint discriminates on our audio yet; see Findings. |
| `checks/speaker_identity/` | Docstring only. Probed but not built: `ml/tools/speaker_probe.py` measures ECAPA-TDNN cosine similarity, and the answer was that it does not separate our clone from its target. See Findings before spending effort here. |
| `checks/prosody/` | Docstring only. |
| `checks/stt_llm/` | Round 2 spike, evidence channel wired end to end. `check.py` is `SttLlmCheck` (implements `contracts.checks.Check`): transcribe the batch, run `analyze()`, emit `SttLlmSignal(script_risk, script_category)`; short window or thin transcript is SKIPPED, a transcriber error is FAILED with no signal. The transcript is a local var in `run()`, discarded on return. `asr.py` is the `Transcriber` seam plus `FasterWhisperTranscriber` (faster-whisper small, English pinned, greedy, VAD on, `condition_on_previous_text` off; loads on CUDA float16 or CPU int8, local weights only). `llm.py` is the `ScriptLLM` seam, system prompt and defensive JSON parser feeding an llm-to-rules-to-none chain that never raises and never guesses mid-range. `tactics.py` is the rules scorer (stdlib only): five tactic scores plus an `intent` in [0, 1] with a refusal/disclaimer strip for Exotel's mixed mono stream. On the 20 hand-written transcripts in `eval_transcripts.py`, rules `intent` separates cleanly: scam 0.83 to 1.00, ordinary 0.00 to 0.33 (n=20, one author, English only). The evidence threshold (0.5) is provisional and uncalibrated. `ml/tools/transcribe_file.py` runs a wav through the check window by window. ASR survives G.711 and AMR-NB but not the 8 kb/s mp3 export, and the English language pin breaks on the non-English real calls; see Findings. Tests: `test_stt_llm_script.py`, `test_stt_llm_llm.py`, `test_stt_llm_check.py`. Not built: the rolling transcript buffer (stage 03, R2's folder) and the concrete local LLM client. |
| `runner/` | Docstring only. Owned by R2, not R1. |
| `augment/` | Built and tested: G.711 mu-law/A-law in numpy, AMR-NB and Opus via ffmpeg, random gain, dynamic range compression, noise at controlled SNR. |
| `train/` | Built and tested: ASVspoof 2019 LA dataset with the phone channel applied per epoch, fine-tuning loop, EER. |
| `eval/` | Built and tested: EER, DET curve, normalised cost-weighted DCF with deployment presets. |
| calibration | Not started. |
| `BENCHMARK_FORMAT.md` | File format, metadata and labelling spec. Applies now; the 30-plus speaker benchmark it describes is a later phase. |
| `RECORDING_SESSIONS.md` | Field guide for whoever runs the session: room, device, 6-speaker protocol. |
| `RECORDING_SCRIPTS.md` | Printable handout, one card per speaker, four takes each. |

**What has been measured, and what has not.** There are now EER figures on a labelled
dataset: ASVspoof 2019 LA dev, heard through the phone channel, plus an n=40 spot
check on the held-out eval split. There is still **no Indian-accent false positive
rate** and no full eval-split EER. Single-clip scores under Findings are anecdotes
from individual files, not results, and are labelled as such.

Every EER here is a **dev** number. Dev is used to pick a checkpoint, so quoting it
as the system's accuracy would be reporting a figure chosen on the data it was
selected against. A full eval-split figure, via `ml/tools/evaluate.py`, is what
belongs on a slide.

**And the headline caveat:** good ASVspoof numbers do not transfer to our own
recordings. See "Fine-tuning works in-domain and does not transfer" below before
quoting any of them.

### Scope decision, 2026-09-07

The population-level Indian-accent false positive rate is a **later phase**.
Recruiting 30 or more speakers does not fit the time available, so this round
records the **6 team members only: 90 seconds each, one session, one device**, plus
a separate clone-source take from whoever the demo clones and one handset spot
check.

What that supports: the three demo items, and a within-speaker paired study of how
much a genuine speaker's score moves through G.711, AMR-NB, Opus and each SNR level.
Six paired speakers all shifting the same direction reach about `p = 0.031` on a sign
test, which is a real result.

What it does not support: a false positive rate. Six speakers with a clean sweep
bound the true rate at only about 50%. Nothing from these recordings is described as
a false positive rate, and every figure drawn from them states `n = 6 speakers`,
however many analysis windows went into it.

## Running it

```
.venv\Scripts\python.exe -m ml.tools.score_file sample.wav
.venv\Scripts\python.exe -m ml.tools.score_file sample.wav --window-ms 4000
```

The file must be 16 kHz mono 16-bit PCM. Anything else and the tool prints the
ffmpeg command that converts it. The tool builds a real `CanonicalAudioBatch` and
goes through `MachineFingerprintCheck`, so it exercises the pipeline path rather
than calling the model directly.

Transcribe a wav through the real `SttLlmCheck`, window by window:

```
.venv\Scripts\python.exe -m ml.tools.transcribe_file call.16k.wav --show-transcript
.venv\Scripts\python.exe -m ml.tools.transcribe_file call.16k.wav --window-ms 45000
```

Same 16 kHz mono 16-bit PCM requirement. It prints status, `script_risk` and the
top tactic per window; `--show-transcript` also prints the text, which the check
itself discards. Debug tool, nothing persisted.

Speaker embeddings, for the identity check rather than the fingerprint check:

```
.venv\Scripts\python.exe -m ml.tools.speaker_probe --rec-dir <dir of 16 kHz wavs>
```

Runs on CPU by default so it can be used while the GPU is training. It reports
pairwise cosine similarity grouped into same-speaker, different-speaker and
clone-vs-target, because a single genuine-versus-clone number cannot distinguish a
different speaker from a different recording channel. Result recorded below.

## Findings, 2026-09-07

Small samples, no labelled corpus, so these are measurements rather than an
evaluation. They are reported because they decide what to build next.

### Neither pretrained model separates genuine from synthetic on our audio

Three genuine Indian-accented phone recordings and one synthetic clip, scored over
**speech-active windows across the whole file**:

| Clip | AASIST | XLS-R + AASIST |
|---|---|---|
| spk_01 genuine | 0.87 | 0.43 |
| spk_02 genuine | 0.54 | 0.64 |
| spk_03 genuine | 0.78 | 0.92 |
| SAPI TTS synthetic | 0.99 | 1.00 |

Genuine speakers reach 0.92 while synthetic sits at 1.00. There is no threshold that
separates them, and no input-scaling policy changes that: `none`, per-window unit
variance and fixed gain targets from 0.02 to 0.10 all give the same picture.

This is the generalisation gap the project leads with, in its most severe form. The
published checkpoint was fine-tuned on ASVspoof 2019 LA, which is clean studio
speech, and applied to real phone audio it calls almost everything synthetic.

### The AASIST-only score tracks loudness, not content

Sweeping the same clips to fixed active-speech RMS targets:

| clip | 0.010 | 0.020 | 0.040 | 0.080 | 0.160 |
|---|---|---|---|---|---|
| spk_01 genuine | 0.024 | 0.141 | 0.396 | 0.640 | 0.873 |
| spk_03 genuine | 0.029 | 0.130 | 0.546 | 0.815 | 0.935 |
| SAPI TTS synthetic | 0.010 | 0.018 | 0.205 | 0.740 | 0.999 |

Rows are the same function of level, and below 0.16 the synthetic clip scores
**lower** than the genuine speakers. Any apparent discrimination from this checkpoint
on unmatched audio should be assumed to be a level artifact until proven otherwise.
`ml/tests/test_ssl_aasist.py::test_score_is_level_invariant` exists to stop this
recurring in the ported model.

### Two corrections, recorded because the wrong versions were briefly believed

- An earlier note attributed the false positives to **AGC / dynamic range
  compression**. That was wrong. The compand filter used to test it also applied
  makeup gain, and level was doing the work. Crest factor does not separate these
  clips at all; the control has the lowest crest factor of any of them.
- An earlier run of the ported model appeared to score genuine speakers at 0.03 to
  0.35. That run scored only the first three windows of each file, which are quiet
  lead-ins. Over speech-active windows the scores are 0.43 to 0.92.

### Root cause found: the model equated "no room" with "genuine", 2026-09-08

The explanation for everything above, and the first finding tonight that points at a
fix rather than a limitation.

Twelve **known-bonafide** ASVspoof eval utterances, scored with the checkpoint that
gets 2.12% EER on that same split, with nothing changed but added reverberation:

| Condition | mean P(synthetic) |
|---|---|
| dry, as recorded | **0.005** |
| rt60 0.2 s, wet 0.5 | 0.744 |
| rt60 0.4 s, wet 0.5 | 0.930 |
| rt60 0.7 s, wet 0.5 | **0.992** |
| microphone spectral tilt, no reverb | 0.018 |

**A room takes known-genuine audio from 0.005 to 0.992.** Spectral tilt does nothing,
so the cue is specifically room reflections, not microphone colouration.

**Why this explains the inversion.** ASVspoof bonafide is close-mic studio speech
with almost no reverberation, and every spoof in it is synthesised from that same
clean material. Anechoic is the only acoustic world the model has seen, so it learned
"no room implies genuine". Our recordings have rooms in them and read as synthetic. A
TTS clone is anechoic by construction and is acoustically *closer to ASVspoof
bonafide than a real person in a room is*. Hence a genuine speaker at 0.910 against a
commercial clone of him at 0.808. The model was applying a rule nobody meant to teach
it.

**The fix**, in `ml/augment/room.py`: convolve with a synthetic impulse response
(exponentially decaying noise, rt60 0.15 to 0.7 s, variable wet mix), FFT-based for
speed, applied **before** the codec because a microphone hears reflections and the
network then encodes what the microphone heard.

Applied to **both classes**. Augmenting only bonafide would teach "reverb means
genuine", the same mistake with the sign flipped, for exactly the reason watermarks
go on both classes or neither.

**Two bugs the tests caught before this reached training**, both of which would have
taught the model something wrong:

- Reflections arrived *before* the direct sound and louder than it, because the
  impulse response was filled with noise from sample 0. That is shaped noise, not a
  room. Fixed by making the response causal with the direct path dominant.
- Mixing dry and wet changed loudness by up to **-9 dB**, worst at wet 0.5, because
  the two are only partly correlated. "Amount of room" would have doubled as
  "quieter", and level is a cue this model has already been caught using. The mix is
  now level-matched to the dry signal; `random_gain` owns level.

**Scale warning.** Once the dev set contains rooms, the previous checkpoint scores
12.48% where it scored 3.12% without them. Those two numbers describe different
evaluation sets and must never be compared. Every dev EER quoted from here on is on
the room-augmented set.

### The detector is inverted on our speaker, 2026-09-08

The decisive measurement, and it settles the question the previous sections left
open. A clean recording of one team member (AAC 203 kbps, 48 kHz mono, captured
directly on the laptop with no transfer) scored against a **real voice clone of the
same person** produced with a commercial cloning tool, saying different words.

Fine-tuned AASIST, the same checkpoint that scores 2.12% EER on held-out ASVspoof:

| Clip | P(synthetic) |
|---|---|
| nik_clean, **genuine human** | **0.910** |
| nik_clone, **actual voice clone** | **0.808** |

XLS-R + AASIST shows the same ordering: genuine 0.990, clone 0.938.

**Both models rank the real person as more synthetic than a clone of him.** This is
not a threshold problem or a thin margin; the ordering is backwards.

Level was excluded as an explanation. Matching both clips to fixed active-speech RMS
targets:

| | as-is | @0.02 | @0.05 | @0.12 |
|---|---|---|---|---|
| genuine | 0.909 | 0.915 | 0.927 | 0.913 |
| clone | 0.808 | 0.707 | 0.786 | 0.806 |

The clone stays below the genuine speaker at every level.

**Recording quality was also excluded.** This clean 203 kbps, 48 kHz, directly
captured recording scores 0.910, against 0.962 for the same speaker's earlier lossy
phone capture. Better capture moved it by 0.05 and left it firmly in "synthetic".
The cause is speaker and recording domain, not codec, not level, not capture
hygiene.

**One thing did work.** Scores now barely move across a 6x level change, where the
pretrained checkpoint swung from 0.02 to 0.87 on the same audio. The random-gain
augmentation fixed the level sensitivity it was built for. It was not sufficient.

**Scope of this claim.** One speaker, one clone, one cloning tool. It does not
establish that the model is inverted in general. It does establish that for this
speaker, on this audio, neither available checkpoint can support demo item 1 (a
genuine call scoring low) or item 2 (a clone being caught), and that no threshold
fixes it because the sign is wrong.

### Correction: reverb was a real cue but not the explanation, 2026-09-08

The room augmentation did what it was built to do, and it was still not enough. The
section above claimed room reflections were the root cause of our recordings scoring
as synthetic. **That claim was too strong and is corrected here.**

Known-bonafide ASVspoof eval audio, n=12, P(synthetic) under added reverb:

| condition | before room augmentation | after |
|---|---|---|
| as-is | 0.005 | 0.006 |
| rt60 0.2 | 0.300 | **0.109** |
| rt60 0.4 | 0.461 | **0.116** |
| rt60 0.7 | 0.758 | **0.137** |

The cue is gone: the response is now nearly flat across rt60 instead of climbing to
0.758. Dev EER on the room-augmented dev set went 14.41% to 6.31% in one epoch. And
our own recordings did not move. So reverb was one cue the model was genuinely
using, removing it worked, and it does not explain the failure on our audio.

**The fix has a price, measured on held-out eval.** Same command, same clean channel,
n=71,237, the only difference being room augmentation during training:

| | original checkpoint | room-augmented |
|---|---|---|
| EER | **2.12%** | 3.51% |
| min-DCF balanced | 0.042 | 0.065 |
| min-DCF bank | 0.145 | 0.231 |
| min-DCF consumer | 0.324 | 0.432 |

Reverb robustness cost **1.39 points of in-domain EER**. That is a genuine trade,
not a collapse, and both checkpoints are kept: `models/finetuned/` holds the 2.12%
one and `models/finetuned_room/` the reverb-robust one. Quote 2.12% only from the
original, and never quote it alongside the reverb table, which the original fails.

Two epochs were run; epoch 1 was better (dev 6.31%) than epoch 2 (7.03%), so the
retained best is epoch 1. The monotonic-improvement assumption has now failed twice
on this model and should not be relied on again.

Lossy transcoding was the next candidate and it is not the cue either. Our
recordings are all AAC from phone video, which ASVspoof never contains, but the
same 12 bonafide utterances score 0.006 as-is, 0.006 through AAC 128k, 0.007 through
AAC 64k and 0.006 through MP3 128k. The model is indifferent to it.

### Every genuine speaker we have is flagged, 2026-09-08

The measurement that settles what this model can and cannot do. Room-augmented
checkpoint, epoch 1, our own recordings, speech-active windows only:

| recording | who | P(synthetic) |
|---|---|---|
| `spk_03b_source` | genuine human | 0.720 |
| `spk_01_source` | genuine human | 0.777 |
| `nik_clean` | genuine human | 0.880 |
| `spk_02_source` | genuine human | 0.900 |
| `spk_03_source` | genuine human | 0.969 |
| `nik_clone` | **actual voice clone** | 0.853 |

**Five of five genuine speakers are flagged as synthetic, and the one real clone
sits in the middle of them.** This is no longer an inversion, which at least implies
a usable signal with the sign wrong. It is the absence of any signal: the genuine
range 0.720 to 0.969 contains the clone, so no threshold separates them and no
recalibration helps.

On this sample the false-positive rate on genuine Indian-accented speech is **5/5**.
That is the honest headline for our own audio, and it should be stated with n=3
speakers, 5 recordings, 1 clone attached, because that is all it is.

**The other architecture fails the same way on our recordings**, though not on all
audio; see the IFD section below, which qualifies this. XLS-R + AASIST with the
released ASVspoof 2021 DF weights, the architecture the deck names, trained on a far
broader corpus than 2019 LA, scored on the same six recordings:

| recording | who | P(synthetic) |
|---|---|---|
| `spk_01_source` | genuine human | 0.436 |
| `spk_02_source` | genuine human | 0.678 |
| `spk_03_source` | genuine human | 0.922 |
| `spk_03b_source` | genuine human | 0.920 |
| `nik_clean` | genuine human | **0.992** |
| `nik_clone` | **actual voice clone** | 0.938 |

The highest score of any recording is a genuine human, above the real clone. Broader
pretraining did not fix it, so this is not a property of the 2019 LA corpus alone.

**What this means for the checks.** The same checkpoint scores 2.12% EER on 71,237
held-out ASVspoof eval utterances. Both numbers are real and they are not in
conflict: the model works on the distribution it was trained on and does not
transfer to ours. This is the 2.85% to 35.24% generalisation gap in `AGENTS.md`,
reproduced on our own recordings, and it is the project rather than a bug to fix
before the demo.

**What was ruled out, in order:** level and gain (fixed by `random_gain`, scores now
stable across a 6x level change), room reverberation (fixed above, cue confirmed
removed), lossy transcoding (never a cue). What remains untested is the speech
itself: ASVspoof bonafide is read English from a studio corpus, ours is Indian-accented
conversational speech on consumer microphones. Adapting to that needs genuine audio
from our own domain in training, which is a data problem, not a tuning problem.

### IFD samples: XLS-R does separate, and accent alone is not the cue, 2026-09-08

Ten sample files from the IndieFake Dataset site, 5 bonafide and 5 deepfake of the
same five Indian public figures. **n=10, one source, an anecdote and not a rate.**

P(synthetic) on the untouched source, all three models:

| clip | class | AASIST 2.12% | AASIST room | XLS-R DF |
|---|---|---|---|---|
| `alia` | bonafide | 0.939 | 0.992 | 0.461 |
| `cb` | bonafide | 0.958 | 0.985 | 0.962 |
| `madhavan` | bonafide | 0.551 | 0.872 | 0.999 |
| `pc` | bonafide | 0.560 | 0.551 | **0.029** |
| `sadhguru` | bonafide | 0.731 | 0.759 | **0.005** |
| `alia` | deepfake | 0.462 | 0.661 | 0.999 |
| `cb` | deepfake | 0.685 | 0.974 | 1.000 |
| `madhavan` | deepfake | 0.951 | 0.774 | 0.999 |
| `pc` | deepfake | 0.135 | 0.017 | 0.847 |
| `sadhguru` | deepfake | nan | nan | 0.999 |

**Both AASIST checkpoints are inverted here too**, on someone else's recordings with
an independent cloning pipeline: bonafide mean 0.748 against deepfake mean 0.558 for
the 2.12% checkpoint, 0.832 against 0.607 for the room-augmented one. That
generalises the inversion beyond our own audio and beyond our own cloning tool.

**XLS-R + AASIST is the exception and the only model showing real signal.** All five
deepfakes score 0.847 or above; three of five bonafide sit at 0.005, 0.029 and 0.461.
Roughly 5/5 detection at 2/5 false positives, or 4/5 at 1/5 if the threshold is
raised to 0.99. Poor in absolute terms, but it is discrimination rather than noise,
and it is the first of that kind we have measured.

**The format confound was checked and ruled out.** IFD bonafide arrives as 48 kHz
stereo and the deepfakes as 24 kHz mono, so container format separates the classes
perfectly and saturated 0.999 scores are exactly what a channel artifact looks like.
Passing the bonafide through the deepfake chain (48 kHz stereo to 24 kHz mono to
16 kHz mono) moved nothing: 0.456, 0.962, 0.999, 0.030, 0.005 against the originals
0.461, 0.962, 0.999, 0.029, 0.005, a maximum change of 0.005. The separation is not
a resampling artifact.

**This corrects the "accent is the remaining cue" inference.** Bonafide here is
Indian-accented and two clips score 0.005 and 0.029, so the model can accept
Indian-accented genuine speech. What it cannot accept is our own recordings, which
score 0.920 to 0.992 on the same model. IFD bonafide is broadcast-quality media
audio; ours is consumer phone capture. The remaining cue is therefore more likely
our recording channel than accent as such, and that is now an open question rather
than a settled one. It should not be written up as solved in either direction.

**One tool defect.** `sadhguru_deepfake` returns nan in most columns because no
window passes `sweep.py`'s 0.4 activity floor on a 6 s clip. The AGC and SNR columns
resolve, so the file is readable and the gate is too aggressive for short clips.
Not fixed yet.

### The Exotel channel alone destroys the detector, 2026-09-08

Two real call recordings from Exotel, the primary acquisition path. Format is
**8000 Hz mono, 8 kb/s mp3**, 99 s and 53 s. Every model saturates:

| Recording | XLS-R DF | AASIST 2.12% | AASIST room |
|---|---|---|---|
| `exotel_call_1` (24 windows) | 1.000 | 1.000 | 0.999 |
| `exotel_call_2` (13 windows) | 1.000 | 0.991 | 0.981 |

Assuming these are genuine human calls, which is what they were collected as, that
is a false-positive rate of 2/2 at maximum confidence on the transport the product
is built around.

**The cause is the bitrate, and it is not the speakers.** Known-bonafide ASVspoof
eval audio, n=8, which scores 0.000 untouched, pushed through that same channel:

| Channel | mean | median | min | flagged > 0.5 |
|---|---|---|---|---|
| as-is, 16 kHz flac | 0.000 | 0.000 | 0.000 | 0/8 |
| 16 kHz mp3 128k | 0.000 | 0.000 | 0.000 | 0/8 |
| 8 kHz mp3 64k | 0.000 | 0.000 | 0.000 | 0/8 |
| 8 kHz mp3 32k | 0.001 | 0.000 | 0.000 | 0/8 |
| 8 kHz mp3 16k | 0.299 | 0.217 | 0.000 | 1/8 |
| **8 kHz mp3 8k (Exotel)** | **0.999** | **1.000** | **0.996** | **8/8** |

Narrowband is not the problem: 8 kHz at 64 kb/s scores 0.000. Neither is mp3 as
such. There is a cliff between 32 kb/s and 8 kb/s, with 16 kb/s sitting on the edge.
Below it, genuine speech is unconditionally called synthetic.

**Two consequences, and the second is architectural.**

1. **This is fixable by augmentation, and cheaply.** The augmentation package already
   owns this class of problem. Adding low-bitrate mp3 to `PhoneChannelAugmenter` and
   retraining is the same move that fixed level and reverberation. Nothing here says
   the model cannot learn the channel; it says it has never seen it.
2. **It sharpens the open question in `AGENTS.md` about streaming.** That question
   was framed as latency: can Exotel stream during the call, or only hand over a
   recording afterwards. This makes it a correctness question as well. A live
   G.711 stream is 64 kb/s, where the model scores 0.000 and our existing G.711
   augmentation already applies. An 8 kb/s recording export is where detection
   collapses. The streaming path is not merely faster, it may be the only one on
   which this check functions at all.

**Resolved 2026-09-08: the stream is fine and transcoding is not the answer.** The
acquisition decision is that Exotel streams call audio into the backend, so the
8 kb/s mp3 above is a recording export rather than the live path. Two follow-up
questions were measured on the same n=8 known-bonafide audio:

| Condition | mean | median | min | flagged > 0.5 |
|---|---|---|---|---|
| as-is, studio 16 kHz | 0.000 | 0.000 | 0.000 | 0/8 |
| **G.711 mu-law 64k, the live stream** | **0.000** | **0.000** | **0.000** | **0/8** |
| 8 kb/s mp3, the export | 0.999 | 1.000 | 0.996 | 8/8 |
| 8 kb/s re-encoded to 64 kb/s | 0.999 | 1.000 | 0.996 | 8/8 |
| 8 kb/s re-encoded to 128 kb/s | 0.999 | 1.000 | 0.997 | 8/8 |
| 8 kb/s then G.711 mu-law 64k | 1.000 | 1.000 | 1.000 | 8/8 |

**Raising the bitrate afterwards recovers nothing.** A lossy encoder discards
information permanently; re-encoding at a higher rate wraps the damaged signal in a
larger container and preserves every artifact. 64 kb/s, 128 kb/s and G.711 all leave
the score at 0.999 or above. Passing it through G.711 afterwards is marginally worse,
not better. Upward transcoding is never restoration, and no cleanup stage can be
placed after an 8 kb/s hop to rescue it.

**The live stream needs no conversion.** G.711 mu-law at 64 kb/s scores 0.000,
identical to studio audio, and it is already in `PhoneChannelAugmenter`, so it is a
channel the model is explicitly trained through. Raw 8 kHz PCM would be equally fine.

**The engineering rule this produces.** Feed the check the stream, decoded straight
from the G.711 payload to PCM. Never let call audio touch a low-bitrate codec
anywhere between ingestion and the model, and never substitute a recording export for
the stream, including as a convenience during testing. One 8 kb/s hop anywhere in
that path is unrecoverable and turns every genuine caller into a maximum-confidence
alert.

This happens to align with the privacy rule already in `AGENTS.md`, that there are no
call recordings at rest and analysis is in-flight. The architecture that keeps us
compliant is also the only one on which this check functions.

### ASR (stt_llm) survives telephony codecs but not the 8 kb/s export, 2026-09-08

faster-whisper `small` through the real `SttLlmCheck`, one script per condition,
`--window-ms 30000`. Anecdote, n=1 speaker for the clean rows, n=2 real calls.

| Audio | Transcript quality |
|---|---|
| `spk_01_source`, clean 16 kHz studio English | near perfect, read-script recovered verbatim |
| same source through **G.711 mu-law 8 kHz** (the live-stream channel) | near perfect, indistinguishable from clean |
| same source through G.711 mu-law and AMR-NB | near perfect |
| `exotel_call_1` / `_2`, real calls, **8 kb/s mp3 export** upsampled to 16 kHz | unusable: repetition-loop hallucination ("I am a star" x15), invented names |

**Same split as the fingerprint model.** G.711 at 64 kb/s is transparent to STT
just as it is to the detector; the 8 kb/s mp3 export destroys both. The engineering
rule already in this file, feed the check the stream and never a low-bitrate export,
carries over to stt_llm unchanged.

**Two issues this surfaced that are not the codec.**

1. **`language="en"` is pinned and the real calls are not English.** They are
   code-switched Kannada / Telugu, and forcing English produces romanised nonsense
   regardless of bitrate. **Decided 2026-09-08: English only for this round.** The
   pin stays; auto-detect flips language mid-call on Hinglish and each flip changes
   transcript style, and multilingual STT is out of scope for now. No multilingual
   claim is made for this channel. Non-English calls fall to issue 2.
2. **`small` still produces repetitive output on badly degraded or non-English
   audio** despite `condition_on_previous_text=False`. The `min_words` gate only
   catches short hallucinations. **Partly addressed:** `looks_like_asr_noise` in
   `tactics.py` abstains (source "none") when the distinct-word ratio is below
   0.30 (pure loops) or the repeated word-pair ratio is above 0.15 (a phrase
   repeated among other junk). It gates both `analyze_rules` and `analyze()`, so a
   noisy transcript never reaches the LLM.

   Measured over 30 s windows, repeated word-pair ratio: genuine read-script 0.00,
   genuine spontaneous speech up to 0.10 across four speakers and four codecs, the
   non-English Exotel-call windows 0.08, 0.16, 0.39, 0.44. With the tool, all
   seven genuine windows pass and three of the four Exotel windows are skipped.
   The fourth (ratio 0.08) is garbled but not repetitive; it passes the guard and
   scores `intent` 0.0 only because no English tactic keyword matched its
   romanised text, which is luck, not coverage. n=4 speakers, one script, two real
   calls. Not a WER measurement and not a benchmark; the thresholds are
   provisional.

### No simulable channel degradation reproduces the failure, 2026-09-08

Individual effects had each been ruled out separately, which leaves the possibility
that a *combination* is what flips the score. It is not. Studio-clean ASVspoof
bonafide, n=8, scored with XLS-R + AASIST as degradations are stacked toward our own
recording conditions:

| Condition | mean | max | flagged > 0.5 |
|---|---|---|---|
| studio as-is | 0.000 | 0.000 | 0/8 |
| + reverb rt60 0.3 | 0.000 | 0.001 | 0/8 |
| + noise at 20 dB SNR | 0.000 | 0.000 | 0/8 |
| + bandlimit 300 to 3400 Hz | 0.000 | 0.000 | 0/8 |
| reverb + noise | 0.000 | 0.000 | 0/8 |
| reverb + noise + AAC 64k | 0.000 | 0.000 | 0/8 |
| **all four stacked** | **0.000** | **0.003** | **0/8** |

The model is indifferent to every channel effect we can apply in software, including
all of them at once, while scoring our own recordings 0.920 to 0.992. So the cue is
not room, not noise, not telephone bandwidth, not lossy coding, and not any
combination of them.

**What that leaves, and it is now the leading hypothesis.** The remaining difference
between our recordings and both reference corpora is the capture device itself.
Smartphone and laptop voice paths apply multi-microphone beamforming, spectral noise
suppression, automatic gain control and de-reverberation before anything is written
to a file. Those are nonlinear and partly generative; spectral suppression in
particular leaves musical-noise and phase artifacts of the same broad kind that
vocoders leave. ASVspoof and IFD bonafide are captured through professional chains
that do none of it.

**Why this matters more than a recording fix.** If device voice processing is the
cue, it is not an artifact of how we recorded, it is a property of the deployment
channel: the caller's handset applies the same processing on a real call. That would
make this a live false-positive source in production rather than a lab inconvenience,
and it is a candidate explanation for the industry gap between lab and field EER.

**Not established.** It is what remains after elimination, not something measured.
The decisive test is one script recorded twice on the same device, once through the
processed voice path and once through a path that bypasses it, scored as a pair.
Until that exists this stays a hypothesis and must not be written up as the cause.

**Consequence for post-processing.** Because every removable channel effect is
already ruled out, cleaning our existing recordings cannot help: there is no
reverb, noise or codec artifact left to strip that the model was reacting to.
Capture, not post-processing, is the only lever.

### Speaker verification does not catch this clone either, 2026-09-08

The fallback, measured so the choice is not made on assumption. ECAPA-TDNN
(`spkrec-ecapa-voxceleb`), cosine similarity between pooled speaker embeddings,
run with `ml.tools.speaker_probe`.

A single genuine-versus-clone number cannot be read, because two effects lower a
cosine similarity and one comparison cannot separate them: the speaker being
different, which is the effect we want, and the recording channel being different,
which is an artefact. Our clean recording is a person in a room on a phone; the
clone is text-to-speech. So the probe reports a **same-speaker-different-session**
ceiling, which already carries channel mismatch, and a **different-speaker** floor,
and places the clone against both.

| Group | n | mean | min | max |
|---|---|---|---|---|
| same speaker, different session | 3 | 0.6345 | 0.4888 | 0.7821 |
| clone vs its target | 3 | 0.5463 | **0.5056** | 0.5923 |
| different speaker | 9 | 0.3225 | 0.1650 | 0.4192 |

Genuine and impostor separate cleanly: floor 0.4888 against ceiling 0.4192. **The
clone group lies entirely inside the genuine range.** All three clone pairs score
above the genuine floor, so **0 of 3** fall below a threshold placed between the
genuine and impostor groups. The clone matches session 3 at 0.5923, better than the
speaker's own clean recording matches his session 2 at 0.4888.

This is `AGENTS.md` "a clone is built to match the voiceprint", now with our own
numbers rather than as a caution. Speaker verification cannot carry demo item 2: any
threshold low enough to catch this clone rejects genuine speech from the same person.

**Method note.** The first run gave one recording 2 usable segments where comparable
files gave 12, because non-overlapping windows straddled the pauses between takes in
that file, leaving its pooled embedding far noisier than the ones it was compared
against. `active_segments` now uses a quarter-segment hop; that file went to 8
segments and its similarities rose slightly (0.5947 to 0.6327, 0.4640 to 0.4888).
The ordering and the conclusion are unchanged, and both numbers are recorded here
because the first version was briefly believed.

**Scope.** n=3 speakers, 1 clone, 1 cloning tool, one language. Not a benchmark, and
not an Indian-accent false-positive rate. It measures **voiceprint match**, never
"this audio is synthetic".

### Headline result: 2.12% EER on held-out eval, 2026-09-08

Full ASVspoof 2019 LA **eval** split, clean channel, fine-tuned AASIST epoch 2
(`AASIST_phone_best.pth`). Eval is held out and its attacks A07 to A19 are mostly
generators absent from training.

```
n = 7,355 bonafide, 63,882 spoof  (71,237 total)

EER          2.12%
min-DCF      0.042   balanced(C_miss=1.0,  C_fa=1.0, P_attack=0.5)
min-DCF      0.145   bank(C_miss=10.0, C_fa=1.0, P_attack=0.01)
min-DCF      0.324   consumer(C_miss=5.0,  C_fa=2.0, P_attack=0.005)

at  1% of genuine callers flagged,  5.2% of spoofs get through
at  5% of genuine callers flagged,  0.8% of spoofs get through
at 10% of genuine callers flagged,  0.3% of spoofs get through
```

Reproduce with:

```
.venv\Scripts\python.exe -m ml.tools.evaluate --split eval --channel clean ^
  --weights %LOCALAPPDATA%\satyacheck\models\finetuned\AASIST_phone_best.pth
```

**Three things that must travel with this number.**

1. **It is not comparable to the deck's 2.85%.** That figure is Tak et al. on ASVspoof
   **2021 DF**; this is ASVspoof **2019 LA eval**. Different evaluation sets. Writing
   "we beat the published result" would be false. Say "2.12% EER on ASVspoof 2019 LA
   eval, n=71,237".
2. **The cost-weighted companion changes the story, which is why `AGENTS.md` requires
   it.** A bare 2.12% reads as solved. Under the consumer cost model, where flagging a
   real person is expensive and attacks are rare, min-DCF is 0.324: only about three
   times better than a detector that always answers the same way. Same model, same
   data, factor of eight between the balanced and consumer views.
3. **It is ASVspoof-domain audio.** The same checkpoint flags all three of our own
   recordings. See the next section.

### Fine-tuning works in-domain and does not transfer, 2026-09-08

The single most important measurement so far, and it decides how this may be
described.

After fine-tuning AASIST on ASVspoof 2019 LA through the phone channel (epoch 1,
full 25,380-utterance train split), dev EER fell from **17.50% to 6.29%**. On the
held-out **eval** split, whose attacks A07 to A19 are mostly generators absent from
training, discrimination is clean:

| ASVspoof eval, clean, n=40 each | median P(synthetic) |
|---|---|
| bonafide | 0.000 |
| spoof | 0.999 |

The same checkpoints on the three genuine Indian-accented phone recordings, as dev
EER improves from 17.50% to 6.29% to 3.12%:

| Clip | pretrained | epoch 1 | epoch 2 |
|---|---|---|---|
| spk_01 genuine | 0.87 | 0.935 | **0.832** |
| spk_02 genuine | 0.54 | 0.803 | **0.799** |
| spk_03 genuine | 0.78 | 1.000 | **0.962** |
| SAPI TTS synthetic | 0.99 | 0.999 | 0.999 |

**All three genuine speakers are flagged by every variant.** The best genuine score is
0.799 against 0.999 for the synthetic clip.

There is no clean trend across epochs: epoch 1 was worst, epoch 2 partially recovers.
A monotonic "more fine-tuning makes our recordings worse" was hypothesised and does
not hold, so it should not be claimed. What holds is the flat statement above.

On the source condition alone, a threshold at 0.98 would separate epoch 2's genuine
scores from the TTS. It collapses under any codec: through AMR-NB the genuine
speakers reach 0.986 to 0.997 against 1.000. That is a threshold fitted to four
points in one condition, not a detector, and must not be presented as one.

### All three models, same methodology, 2026-09-08

Source condition, mean over speech-active windows:

| Clip | pretrained AASIST | fine-tuned AASIST | XLS-R + AASIST |
|---|---|---|---|
| spk_01 genuine | 0.87 | 0.935 | **0.434** |
| spk_02 genuine | 0.54 | 0.803 | **0.638** |
| spk_03 genuine | 0.78 | 1.000 | **0.922** |
| SAPI TTS synthetic | 0.99 | 0.999 | 1.000 |

The model with the best ASVspoof numbers is the worst on our recordings, and the
ported XLS-R checkpoint is the only one that keeps every genuine speaker below the
synthetic clip. It is still not a working detector here: spk_03 sits at 0.922 against
1.000, and any codec pushes it to 0.98.

**Our synthetic test case is too easy, and that limits every conclusion above.** The
SAPI TTS pins at exactly 1.000 under every condition and in every model. Windows SAPI
is a formant synthesiser, nothing like a neural voice clone, so these tables measure
"can the model reject a 1990s synthesiser" rather than "can it catch a clone". A
modern clone is the missing test and could move any of these numbers.

**What this rules out.** The model is not broken, and the problem is not phone
codecs. We built G.711, AMR-NB, Opus, gain and noise augmentation specifically to
close the channel gap, trained through it, and the improvement stayed inside the
ASVspoof domain. The residual gap is speaker and recording domain: the model has
learned "bonafide means audio that looks like ASVspoof bonafide", which is clean
studio-recorded, largely Western-accented English.

**What is still open, and it is the fork in the road.** Our three recordings are
Indian-accented *and* lossy phone captures made before the recording spec existed,
with device processing probably on. Those two explanations have very different
consequences:

- If **recording quality**, clean capture fixes it and the warning path works.
- If **accent and speaker domain**, no capture change saves it, and the honest
  position is that the system is not deployable for Indian speakers without
  in-domain training data.

One clean recording, made per `RECORDING_SESSIONS.md` with processing off, separates
them. Until that exists, neither explanation may be asserted.

### Latency

XLS-R + AASIST: 27 to 37 ms per 4 s window on the RTX 4070, comfortably inside the
180 ms stage 04 budget. AASIST alone: 13 to 16 ms. Both cost seconds on the first
call because loading is lazy, which is what `warmup()` exists for.

## Augmentation

`ml/augment/` puts the phone channel on training audio in software.

| Module | What it does |
|---|---|
| `g711.py` | mu-law and A-law, ITU reference algorithm in numpy, no dependency |
| `phone_codecs.py` | AMR-NB and Opus round trips through ffmpeg, plus G.711 for cross-checking |
| `gain.py` | random gain, and dynamic range compression with named presets |
| `noise.py` | additive noise at a controlled SNR, measured on active speech |

Two decisions in here are worth knowing about, because both were forced by
measurement rather than chosen up front.

**`gain.py` exists because of the level finding.** Random gain is the cheapest
augmentation in the package and the one that addresses the failure documented under
Findings, where the pretrained score tracked loudness rather than content. A model
trained on a corpus of consistent level never learns to ignore level.

**G.711 does not match ffmpeg byte for byte, and that is correct.** This
implementation follows the ITU reference, which truncates. ffmpeg builds its encode
table by inverting the decoder and picking the nearest level. They agree on about
98.5% of samples and disagree by at most one quantisation step; measured round-trip
error is identical (0.0197 mu-law, 0.0156 A-law, versus ffmpeg's 0.0197 and 0.0157).
The tests assert that bound rather than byte-equality, because byte-equality would be
asserting ffmpeg's rounding policy rather than G.711.

Naming, and it is load-bearing: `tests/test_transport_invariant.py` AST-walks `ml/`
and fails on any attribute named `codec`, so this package says `codec_name` and
`CodecName` throughout.

## Fine-tuning through the phone channel

`ml/train/` is the Round 1 "training pipeline with phone compression and noise"
deliverable. It exists because both pretrained checkpoints failed on real audio,
which is measured above rather than assumed.

```
.venv\Scripts\python.exe -m ml.train.finetune_aasist --epochs 3 --workers 4 --no-amp
```

Corpus: ASVspoof 2019 LA at `%LOCALAPPDATA%\satyacheck\data\LA`. Train is 25,380
utterances, 2,580 bonafide and 22,800 spoof, verified against the CM protocol line
for line. The dev and eval folders hold ~140 and ~700 more flac files than their
protocols list; those are ASV speaker-enrolment utterances, not countermeasure
trials, and are correctly ignored.

**Dev is scored through the same phone channel as training.** Scoring it clean would
answer how well the model does on studio audio, which is not the question.

Three decisions worth knowing:

- **Class weighting is on.** The corpus is roughly 1:9 bonafide to spoof, and an
  unweighted loss lets the model score well by calling everything spoof. That is
  precisely the failure already observed in the pretrained checkpoints, so it is not
  a hypothetical.
- **Subprocess codecs are off by default in training.** Calling ffmpeg through
  subprocess pipes inside spawn-based DataLoader workers **deadlocks on Windows**:
  the run stalls with the GPU at 4% and no ffmpeg processes alive. It also cost 94%
  of the data-loading time (247 ms per item against 14 ms). G.711 mu-law and A-law
  are pure numpy and cover the dominant telephony codec. The loss is AMR-NB and Opus
  breadth during training; both remain available for evaluation via `ml/tools/sweep.py`,
  and for training with `allow_subprocess_codecs=True` at `num_workers=0`.
- **Mixed precision is available but not the default.** On this model it gave 5.2
  against 4.4 utterances per second, because the graph-attention operations do not
  vectorise well, so it is not worth the fp16 stability risk on an unattended run.

### Batch size is a cliff, not a slope

Measured on the 8 GB RTX 4070, forward plus backward, no data loading:

| Batch | ms/step | utterances/s | Peak GPU memory |
|---|---|---|---|
| 8 | 329 | **24.3** | 3.57 GB |
| 16 | 1820 | 8.8 | 7.11 GB |
| 32 | 32982 | 1.0 | 14.20 GB |

AASIST holds 64600 raw samples across wide convolutional feature maps, so activation
memory grows fast. Past batch 8 the card is already spilling, and throughput does not
degrade gracefully, it collapses: batch 32 needs 14.2 GB on an 8 GB card and takes 33
seconds per step.

This cost two abandoned training runs. Both showed the same misleading signature,
GPU utilisation pinned at 100% while drawing 36 to 40 W, which reads like
kernel-launch overhead and is in fact memory thrashing. **On this card, batch 8.**
Re-measure before raising it on different hardware.

### Known limitation: the dev number carries about a point of noise

`PhoneChannelAugmenter` holds its own RNG state, and every DataLoader worker receives
a *copy* of it. Which degradation lands on which dev utterance therefore depends on
the worker count, so the same checkpoint on the same dev subsample measured **16.29%
at 4 workers and 17.50% at 6**.

Consequences, and they are not cosmetic:

- Report `--workers` alongside any dev EER, or the number is not reproducible.
- Treat improvements smaller than roughly 1.5 points as noise.
- Fix before this metric is used for anything finer than "did fine-tuning help":
  seed the augmentation per utterance index rather than per augmenter instance, so
  the applied degradation is a deterministic function of the item and worker count
  stops mattering.

Training augmentation is unaffected: randomness across epochs is the point there.
This only matters for evaluation, where the channel should be fixed.

### First training result

A one-epoch run over a 960-utterance subsample moved dev EER from **18.64% to
9.80%**, both measured through the phone channel. That is a subsample, one epoch, and
not a headline number; it is evidence the loop learns the right thing. The full run
and its numbers replace this line when it finishes.

## The scorer seam

`MachineFingerprintCheck` owns status, evidence and the contract. A
`SyntheticScorer` owns the model and nothing else:

```python
class SyntheticScorer(Protocol):
    @property
    def model_name(self) -> str: ...
    @property
    def model_version(self) -> str: ...
    def score(self, pcm_s16le: bytes, sample_rate: int) -> float: ...
```

`model_name` and `model_version` are read-only, so evidence always names the model
that actually produced the score. A plain class attribute satisfies a read-only
property, so a scorer can declare them either way.

A scorer raises on failure and never returns a fallback. The check turns any
exception into `CheckStatus.FAILED` with no signal, so a model failure degrades to
"no warning". The exception message is not recorded, only its class name, because
`EvidenceItem.detail` is specified non-PII and a message can carry a path or a
number.

Status transitions and the three provisional constants
(`DEFAULT_MIN_WINDOW_MS`, `DEFAULT_DEGRADED_WINDOW_MS`,
`DEFAULT_EVIDENCE_THRESHOLD`) are documented in
`checks/machine_fingerprint/__init__.py` and `check.py`. They are configuration,
not measured results, and calibration on unseen data revisits all three.
`DEFAULT_EVIDENCE_THRESHOLD` decides which reason code labels the evidence. It is
not a policy threshold and not a decision; `synthetic_probability` is the output the
risk engine consumes.

## Model weights

Weights live **outside the repo**, at `%LOCALAPPDATA%\satyacheck\models`
(`C:\Users\<user>\AppData\Local\satyacheck\models`). Not in `ml/`, because the repo
sits inside a OneDrive folder and gigabytes of checkpoints would sync-upload. Nothing
here is committed.

Downloaded 2026-09-07, sizes measured on disk:

| Model | Directory | Size | Used by | Python 3.13 |
|---|---|---|---|---|
| wav2vec2 XLS-R 300m (HuggingFace) | `wav2vec2-xls-r-300m/` | 1211 MB | machine_fingerprint front end | yes, through transformers |
| AASIST and AASIST-L (clovaai) | `aasist/` | 1.7 MB, weights plus model code | machine_fingerprint back end | yes, pure PyTorch |
| ECAPA-TDNN (SpeechBrain) | `spkrec-ecapa-voxceleb/` | 85 MB | speaker_identity | yes |
| faster-whisper small | `faster-whisper-small/` | 464 MB | stt_llm, local STT only | yes |
| wav2vec2 XLS-R 300m (fairseq) | `fairseq/xlsr2_300m.pt` | 3632 MB | Tak et al. reproduction only | **no** |
| SSL-AASIST fine-tuned, LA-trained | `Best_LA_model_for_DF.pth` | 1213 MB | Tak et al. reproduction only | **no** |

Total on disk 6.45 GB. Every size above was measured after download, and each file
matched the `content-length` the server advertised.

### Corpus

ASVspoof 2019 LA at `%LOCALAPPDATA%\satyacheck\data\LA`, roughly 8 GB extracted.
Train counts were verified line for line against the CM protocol before any training
ran.

A warning worth keeping, because it nearly cost a night: a download from the official
Edinburgh host via `aria2c` produced a file of **exactly** the right byte count that
was not a valid zip. aria2 preallocates the full size, so matching size proves
nothing about completeness; the leftover `.aria2` control file was the real signal.
Verify an archive by opening it, not by measuring it.

openSMILE needs no download; it ships its feature-set configs with the package.
The scam-script LLM is deliberately not chosen yet, because stt_llm is priority 5
and a Round 1 evidence channel only.

### Two paths for the machine fingerprint check, on purpose

**Path A, ours, runs on the pinned interpreter.** HuggingFace XLS-R as the front end
plus the AASIST back end, both importable on Python 3.13. The clovaai AASIST weights
are pretrained on ASVspoof 2019 LA and give a working detector immediately. Our own
fine-tuning through G.711 and AMR-NB replaces them, and that is the Round 1 training
deliverable.

**Path B, the published reproduction, is now ported rather than reproduced.**
`SslAasistScorer` runs the published XLS-R + AASIST architecture with its fine-tuned
checkpoint on Python 3.13, with the fairseq front end replaced by HuggingFace
`Wav2Vec2Model`.

The key mapping was derived from ground truth rather than written from memory: the
repository holds both the original fairseq `xlsr2_300m.pt` and HuggingFace's
converted `facebook/wav2vec2-xls-r-300m`, which are the same weights under different
names, so matching them tensor by tensor yields an exact mapping (429 of 429, none
transposed). It is stored beside the weights as `ssl_aasist/fairseq_to_hf.json`.

**The port mechanism is verified.** Building the encoder both ways from the same
pretrained weights, HuggingFace's own `from_pretrained` against our mapping applied
to the fairseq file, produces bit-identical features: max absolute difference
0.000e+00 over 422 tensors, 0 missing. Whatever the model does, it is not a loading
bug.

What is **not** verified is equivalence of the full pipeline against the published
one, which would need the Python 3.7 fairseq environment to generate reference
scores. Until that exists, describe this as matching the published architecture,
never as reproducing the published number.

## Tests

ML tests live here because `tests/` at the repo root belongs to R2.

```
.venv\Scripts\python.exe -m pytest ml -q          # this workstream
.venv\Scripts\python.exe -m pytest ml tests -q    # plus the transport invariant
```

The second is not optional. `tests/test_transport_invariant.py` AST-walks `ml/` and
fails on any attribute named `codec` or `transport`, and on importing `Codec`,
`AudioChunk`, `StreamOpen`, `StreamClose` or `Transport`. Augmentation code must
therefore use `codec_name` and `CodecName`, never `codec` and `Codec`.

## Environment, measured 2026-09-07

| Fact | Value |
|---|---|
| GPU | RTX 4070 Laptop, 8188 MiB, driver 616.56 |
| Python | 3.13.15, `.venv` built by uv 0.12.1 |
| Installed | pydantic, pytest, ruff, mypy, numpy 2.5.3, torch 2.11.0+cu128, torchaudio 2.11.0+cu128, transformers, soundfile 0.14.0, speechbrain 1.1.1 |
| Added 2026-09-08 | speechbrain 1.1.1 for ECAPA-TDNN, plus hyperpyyaml, joblib, scipy, sentencepiece, requests, ruamel-yaml, cloudpickle |
| Added 2026-09-08 (stt_llm) | faster-whisper 1.2.1 for local STT, with ctranslate2 4.8.2, av 18.1.0, onnxruntime 1.29.0, flatbuffers, protobuf. Owner-approved; also added to the `ml` extra in `pyproject.toml` |
| FLAC decoding | `soundfile`, not torchaudio. torchaudio 2.11 delegates decoding to `torchcodec`, which is a heavier dependency than reading a FLAC warrants |
| CUDA | available, `torch.cuda.is_available()` is True and reports the 4070 |
| `uv` | 0.12.10 at `%USERPROFILE%\.local\bin\uv.exe`. README repo state says 0.12.1 |
| ffmpeg | `C:\ffmpeg\ffmpeg.exe`, with `libopencore_amrnb`, `libopus`, `pcm_mulaw`, `pcm_alaw` |
| Disk | C:, 26.5 GB free of 928.8 GB, one volume, after 6.45 GB of weights and the torch install |

Installing needs `--system-certs`, because something on this machine intercepts TLS
and uv's bundled certificate store rejects the substituted issuer:

```
uv pip install --system-certs --python .\.venv\Scripts\python.exe <package>
```

**speechbrain was installed with `--no-deps`, deliberately.** It declares a torch
requirement, and resolving it would have been free to replace the cu128 build with
the CPU wheel from PyPI. A training run was holding those DLLs open at the time, so
on Windows that either fails mid-install or leaves the venv broken. Its remaining
dependencies were installed explicitly and none of them touches torch:

```
uv pip install --native-tls hyperpyyaml joblib scipy sentencepiece requests
uv pip install --native-tls --no-deps speechbrain
```

Verified after each step that `torch.__version__` was still `2.11.0+cu128` and
`torch.cuda.is_available()` still True. If speechbrain is ever reinstalled normally,
check the torch build before trusting any GPU number.

torch and torchaudio came from `--index-url https://download.pytorch.org/whl/cu128`,
since the default PyPI wheel on Windows is CPU-only. That index is not recorded in
`pyproject.toml`, so a fresh `uv sync --extra ml` on another machine would install
the CPU build instead. Recording it is a shared-config change and `pyproject.toml`
is not R1's file; raised with R2 in `QUESTIONS.md`.

Three consequences worth writing down:

- **`audioop` was removed from the standard library in Python 3.13**, so there is no
  built-in G.711. The augmentation pipeline implements mu-law and A-law directly and
  cross-checks the output against ffmpeg `pcm_mulaw`.
- **Storage is not the constraint people expect.** Running pretrained checkpoints
  costs roughly 2 to 3 GB. A labelled eval set for a first EER (In-the-Wild alone)
  is roughly 8 GB, and a training corpus for fine-tuning through phone codecs
  (ASVspoof 2019 LA train) is roughly another 8 GB. The 150 to 200 GB figure covers
  breadth (ASVspoof 5, MLAAD, ASVspoof 2021 DF eval) that comes later. Every size
  here is approximate and unverified; check before pulling.

## What R1 may not touch

`contracts/`, `backend/`, `acquisitions/`, `app/`, `tests/`, `docs/`. Contract
questions and repo-wide doc corrections go to R2 through `QUESTIONS.md`.
