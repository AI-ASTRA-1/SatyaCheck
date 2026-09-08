# FROZEN, the diagnosis config for H+0 to H+4

Every diagnostic run between H+0 and H+4 uses exactly this configuration. Nothing in
this file may change until the H+4 gate has been evaluated. If experiment 1 runs on
one config and experiment 3 on another, nothing has been measured.

Every field below was read out of the running code, not written from memory. The
reproduction command that produced them is at the bottom.

```
checkpoint_path       : C:\Users\Nkroc\AppData\Local\satyacheck\models\Best_LA_model_for_DF.pth
checkpoint_sha256     : 1cf904f1d84c867c278cd42161df5367939d61cc28bfefd239bc995af59c2804
checkpoint_bytes      : 1271642081
model_id              : xlsr-aasist
model_version         : tak2022-LA-for-DF-hfport
input_sample_rate     : 16000
resample_method       : ffmpeg -ac 1 -ar 16000 -sample_fmt s16 (swresample default, NOT soxr)
vad_implementation    : ml/eval/activity.py, 20 ms frame RMS against a per-file gate
                        at 0.15 of the 95th-percentile frame RMS. No external VAD.
vad_activity_floor    : 0.4
window_s              : 4.0375   (64600 samples, fixed by the published model)
hop_s                 : 4.0375   ordinary path, non-overlapping
                        1.009375 sparse fallback, a quarter hop
threshold             : 0.5      evidence-label cut point only, not a decision
preprocessing_chain   : see below
torch_version         : 2.11.0+cu128
frozen_at             : 2026-09-08T09:52:56+00:00
frozen_commit         : f1e83a8d0209a1acb70912dbe6e286e3a4b9763e
```

## Preprocessing chain, in order

Stated in full because it is what makes rows from different experiments comparable.

```
1.  ffmpeg -ac 1 -ar 16000 -sample_fmt s16     decode and canonicalise
2.  int16 little-endian / 32768.0              to float32 in [-1, 1)
3.  select_windows(x, 64600)                   speech-active window selection
4.  _tile_pad to exactly 64600 samples         repeat, then truncate (published `pad`)
5.  (x - mean) / (std + 1e-7)                  per-window zero-mean unit-variance
6.  Wav2Vec2Model (XLS-R 300m front end)       last_hidden_state
7.  AASIST back end                            2 logits
8.  softmax(dim=1), column 0                   P(synthetic)
9.  mean over selected windows                 the file score
```

Steps 4, 5 and 8 are inside `SslAasistScorer.score`. Step 3 is the only step this
repo chose; every other step is fixed by the published model.

**Step 5 is not optional.** XLS-R uses a layer-norm feature extractor and was
pretrained on zero-mean unit-variance waveforms. Without it the score tracks input
loudness rather than content, which `ml/README.md` records as measured and severe.

**Step 9 is the step that is not well defined on short files.** See "Which 4 s window
you score decides the answer" in `ml/README.md`: one 6 s clip scores 0.0024 to 0.9972
depending on where the window starts. Any figure from a clip under about 15 s must
state which windowing produced it. `ml/tools/score_file.py` uses fixed 4000 ms
windows from the start of the file and does **not** follow this chain at step 3; it
is not the frozen path and its numbers are not comparable to these.

## Fixed constants

| Constant | Value | Where |
|---|---|---|
| `SSL_INPUT_SAMPLES` | 64600 | `ml/checks/machine_fingerprint/ssl_aasist.py` |
| `SPOOF_CLASS_INDEX` | 0 | same |
| `normalize_input` | `True` | same, constructor default |
| `FRAME_SAMPLES` | 320 (20 ms) | `ml/eval/activity.py` |
| `ACTIVITY_FLOOR` | 0.4 | same |
| `GATE_FRACTION` | 0.15 | same |
| `DEFAULT_MIN_WINDOW_MS` | 1000 | `ml/checks/machine_fingerprint/check.py` |
| `DEFAULT_DEGRADED_WINDOW_MS` | 3000 | same |
| `DEFAULT_EVIDENCE_THRESHOLD` | 0.5 | same |

## Weights outside the repo

`Best_LA_model_for_DF.pth` is the published Tak et al. LA-trained SSL-AASIST
checkpoint, loaded through the HuggingFace-ported front end. The two supporting files
are outside the repo and outside `frozen_commit`, so they are hashed here:

| File | SHA256 |
|---|---|
| `ssl_aasist/model.py` | `08b2b99b9cc0e90732746471325185f2eb144795ee35338e0a02951015a856c6` |
| `ssl_aasist/fairseq_to_hf.json` | `f1bf1d0fe39c3de8a95f25e98f969cdf001c0598b9b94d265b51964d056d442b` |

`wav2vec2-xls-r-300m/` supplies the `Wav2Vec2Config` only; the weights come from the
fine-tuned checkpoint above, not from that directory.

## Why this checkpoint and not the other two

`%LOCALAPPDATA%\satyacheck\models\finetuned\AASIST_phone_best.pth` (the 2.12% EER
checkpoint) and `finetuned_room\AASIST_phone_best.pth` are **not** frozen and produce
none of the gate numbers. `xlsr-aasist` is frozen because it is the only model that
shows separation on independent audio (IFD `pc` bonafide 0.029 against deepfake
0.847), and the transplant experiment needs a separation that can collapse. Both
AASIST checkpoints are inverted on IFD and would give a transplant with nothing to
measure.

**The anchors in the H+0 brief mixed three checkpoints.** For the record, the
`xlsr-aasist` values from `ml/README.md` are the only ones that apply here:

| Audio | Channel | xlsr-aasist |
|---|---|---|
| ASVspoof eval bonafide | studio | 0.000 |
| IFD `pc` bonafide | broadcast | 0.029 |
| IFD `pc` deepfake | generated | 0.847 |
| own genuine recordings, 5 | consumer phone | 0.436 to 0.992 |
| `nik_clone` | generated | 0.938 |

`0.005 to 0.006` on ASVspoof, and the `0.720 to 0.969` genuine range with the clone
at `0.853`, are AASIST figures. They are not regression checks for this config.

## Environment

| Fact | Value |
|---|---|
| Python | 3.13.15 |
| torch | 2.11.0+cu128, CUDA available |
| GPU | NVIDIA GeForce RTX 4070 Laptop |
| numpy | 2.5.3 |
| transformers | 5.16.1 |
| ffmpeg | `N-121547-g0a4bd6cc23-20251028`, `C:\ffmpeg\ffmpeg.exe` |

ffmpeg is built with libsoxr, but no `-resampler` flag is passed, so resampling uses
the swresample default. Passing `-resampler soxr` would be a different chain and a
different set of numbers.

## Reproducing this file

```
.venv\Scripts\python.exe -m ml.tools.frozen_config
certutil -hashfile %LOCALAPPDATA%\satyacheck\models\Best_LA_model_for_DF.pth SHA256
git rev-parse HEAD
```

Every CSV under `data/results/` carries `checkpoint` and `frozen_commit` columns.
A row's `frozen_commit` is the commit the run was made at, which is provenance, not
a claim. The claim that the run used *this* config is enforced separately, by
`ml/tests/test_frozen_config.py`: it fails at any commit where the code has drifted
from the fields above. So a row is comparable with another row when both their
commits pass that test, and the checkpoint hash is unchanged.

The `frozen_commit` field in the block above is different: it is the commit the
config was read at, `f1e83a8`, the parent of the commit that adds this file. A file
cannot name its own commit.
