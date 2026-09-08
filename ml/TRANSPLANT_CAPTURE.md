# Channel transplant, capture procedure

Four recordings. Roughly 30 minutes with the rig set up, and it is the measurement
the H+4 gate is waiting on. Rules 3, 4 and 5 all read `delta_genuine_phone` and none
of them can be evaluated until these exist.

## What this measures and why it has to be done this way

The speech is held constant and only the acquisition channel varies. Same speaker,
same accent, same words, same generator down each column; the only difference is how
the audio reached the file.

|  | A: original file | B: speaker to phone | C: B through Exotel |
|---|---|---|---|
| IFD `pc` bonafide | have it, 0.0290 | **record** | **record** |
| IFD `pc` deepfake | have it, 0.8487 | **record** | **record** |

`pc` is the subject because it is the cleanest separation this checkpoint shows on
audio that is not ours: 0.029 against 0.847, a gap of 0.82. If that collapses, it
collapsed for one reason.

**Record both classes. Not just the genuine one.** Replaying only the bonafide clip
cannot tell these two apart:

- the channel makes *genuine* audio look fake, which channel-replay augmentation
  fixes, and our own rt60 result (0.758 to 0.137) is precedent that it works, or
- the channel raises *every* score, which means the model is measuring distance from
  its training distribution and augmentation would move both classes together.

Those are Rule 3 and Rule 4. They lead to opposite decisions, and one recording
cannot distinguish them.

## The rig

```
laptop  ->  speaker  ->  air  ->  phone microphone  ->  file
                                        |
                                        +->  (path C) place a call through Exotel,
                                             capture what the backend receives
```

Path B is the phone recording the speaker directly. Path C is that same acoustic
path continuing through the telephony channel.

## Controls, and they are the whole experiment

These five must be **identical** across all four recordings. If any of them varies,
the deltas measure that variation as well as the channel, and the result cannot be
read. Set them once, write them down, do not touch them until all four are captured.

| Control | Why it matters |
|---|---|
| speaker volume setting | level is a cue this model has been caught using before |
| phone model | device voice processing differs per handset and is the leading hypothesis |
| distance from speaker, cm | changes both level and the direct-to-reverberant ratio |
| room | room reflections took known-genuine audio from 0.005 to 0.992 once already |
| background noise level | an obvious confound, and free to hold constant |

Practical notes:

- Do all four in **one session** without moving anything. Coming back tomorrow means
  a different room temperature, a different chair position and a different result.
- Play the four source clips back to back without adjusting anything between them.
- Do not use a phone call app's own recorder for path B; use a plain voice recorder,
  so path B is the microphone and path C is the microphone plus the network.
- **Turn nothing on to "improve" the audio.** No noise suppression toggle, no voice
  isolation, no enhancement. If the handset applies it anyway that is part of what we
  are measuring, but nothing should be enabled deliberately.

## Files to produce

Put them in `data/replay/` with exactly these names. The tool looks them up by name.

```
data/replay/pc_bonafide_phone.wav      path B, genuine
data/replay/pc_deepfake_phone.wav      path B, deepfake
data/replay/pc_bonafide_exotel.wav     path C, genuine
data/replay/pc_deepfake_exotel.wav     path C, deepfake
```

Any format ffmpeg can read. They are canonicalised to 16 kHz mono s16le by the same
decode every other row in the diagnosis goes through, so no conversion is needed
first.

**One thing that would invalidate path C.** `ml/README.md` records that a single
8 kb/s hop turns every genuine caller into a maximum-confidence alert, and that
re-encoding upward recovers nothing. If path C is captured from an Exotel *recording
export* rather than the live stream, it measures the export codec and not the
channel. Capture what the backend receives from the stream.

## The conditions file, required

Write `data/replay/capture_conditions.json` before running the tool. It refuses to
score any replayed capture without it, because a confounded experiment that produces
numbers is worse than one that produces none.

```json
{
  "speaker_volume": "60%, system slider, unchanged across all four",
  "phone_model": "<make and model>",
  "distance_cm": "30",
  "room": "<which room, door open or closed, soft furnishings>",
  "background_noise": "<quiet, fan off, no traffic> or a dB reading if you have one"
}
```

Every value is written into the `notes` column of each replayed row, so the controls
travel with the numbers rather than living in someone's memory.

## Then run

```
.venv\Scripts\python.exe -m ml.tools.transplant
```

It writes `data/results/transplant.csv`, prints the four deltas and the separation
before and after, and exits non-zero while any cell is missing.

## Reading the result

The gate rules are applied in order, first match wins.

| Pattern | Meaning | Branch |
|---|---|---|
| `delta_genuine_phone` > 0.40 and `delta_spoof_phone` < 0.15 | the channel pushes genuine into the spoof class and leaves spoof alone | A, retrain |
| both deltas > 0.40 | the whole distribution moved; augmentation moves it back together and separation does not improve | B, no retrain |
| `delta_genuine_phone` < 0.15 | the transplant did not reproduce the failure, so the cue is something else | B, no retrain, record as OPEN |

**Two cautions on the arithmetic, both worth knowing before the numbers arrive.**

`overlap` is 0.0 by construction with one clip per class, so it will report 0.0
whatever happens, including the case where the classes invert. Read the `gap` the
tool prints beside it, which is negative when the ordering is backwards. Passing
`--subject pc --subject alia --subject cb` and capturing those too would make
`overlap` mean something, at the cost of three times the recording.

`delta_spoof_phone` cannot exceed 0.152, because `pc_deepfake` already scores 0.8487
and the score is capped at 1.0. Rule 4 as written asks for it to exceed 0.40, which
is arithmetically impossible on this subject. If both classes do saturate upward,
that will show as `delta_spoof_phone` near +0.15 with the spoof score at ~1.0, and it
should be read as Rule 4 rather than as Rule 3's "spoof stayed put". Rule 3's
`< 0.15` threshold sits exactly on that boundary, so **check the absolute path B
scores, not only the deltas**, before calling it.
