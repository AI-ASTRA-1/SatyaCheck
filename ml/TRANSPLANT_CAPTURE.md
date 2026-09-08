# Channel transplant, capture procedure

Ten recordings. Roughly 30 minutes with the rig set up, and it is the measurement
the H+4 gate is waiting on. Rules 3, 4 and 5 all read `delta_genuine_phone` and none
of them can be evaluated until these exist.

## What this measures and why it has to be done this way

The speech is held constant and only the acquisition channel varies. Same speaker,
same accent, same words, same generator down each column; the only difference is how
the audio reached the file.

|  | A: original file | B: speaker to phone | C: B through Exotel |
|---|---|---|---|
| bonafide, 5 subjects | have them | **record** | derived in software |
| deepfake, 5 subjects | have them | **record** | derived in software |

**Record all five subjects, ten clips, not just `pc`.** Two reasons, both from
measurements already in `ml/README.md`:

- The `pc` clips are 5.10 s and 5.06 s, which is **one analysis window each**. A
  single window's score moves nearly the full 0 to 1 range with where the window
  starts, so a delta between two one-window scores is one draw, not a measurement.
  Five paired subjects average that out.
- `overlap` is 0.0 by construction at one clip per class. It only carries
  information from two clips per class upward.

And a third reason, visible only once all five were scored together:

```
path A, all five subjects
  genuine  n=5  0.0046 to 0.9993
  spoof    n=5  0.1279 to 0.9995
  overlap  0.8714
  gap      -0.8714
```

**`pc` is the one subject of five where this model separates at all.** Picking it
because it has the cleanest separation is selecting on the outcome. The paired
per-subject delta is still the right statistic, since each subject is its own
control, but "separation before" across the set is 0.87 overlap, not the +0.82 gap
`pc` alone suggests. Anything written up from `pc` alone must say it is one subject.

Ten clips is about a minute more playback in the same session.

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
laptop  ->  speaker  ->  air  ->  phone microphone  ->  file      (path B)
                                                          |
                                              G.711 mu-law in software  (path C)
```

Path B is the phone recording the speaker directly, with a plain voice recorder and
no call involved. Path C continues from it, see below.

## Controls, and they are the whole experiment

These five must be **identical** across all ten recordings. If any of them varies,
the deltas measure that variation as well as the channel, and the result cannot be
read. Set them once, write them down, do not touch them until all ten are captured.

| Control | Why it matters |
|---|---|
| speaker volume setting | level is a cue this model has been caught using before |
| phone model | device voice processing differs per handset and is the leading hypothesis |
| distance from speaker, cm | changes both level and the direct-to-reverberant ratio |
| room | room reflections took known-genuine audio from 0.005 to 0.992 once already |
| background noise level | an obvious confound, and free to hold constant |

Practical notes:

- Do all ten in **one session** without moving anything. Coming back tomorrow means
  a different room position and a different result.
- Record each clip as its own file: start recorder, play clip, stop recorder. Do not
  move the phone between takes. Starting and stopping a recorder does not disturb the
  controls; picking the phone up does.
- Use a **plain voice recorder**, never a call app's recorder. Path B has to be the
  microphone alone, or path B and path C become the same measurement.
- Mark the phone's position with tape so it cannot drift over ten takes.
- **Turn nothing on to "improve" the audio.** No noise suppression toggle, no voice
  isolation, no enhancement. If the handset applies it anyway that is part of what we
  are measuring, but nothing should be enabled deliberately.

## Files to produce

Put them in `data/replay/` with exactly these names. The tool looks them up by name.

```
data/replay/alia_bonafide_phone.wav        data/replay/alia_deepfake_phone.wav
data/replay/cb_bonafide_phone.wav          data/replay/cb_deepfake_phone.wav
data/replay/madhavan_bonafide_phone.wav    data/replay/madhavan_deepfake_phone.wav
data/replay/pc_bonafide_phone.wav          data/replay/pc_deepfake_phone.wav
data/replay/sadhguru_bonafide_phone.wav    data/replay/sadhguru_deepfake_phone.wav
```

Ten files, path B only. Path C is derived from these in software, see below. If a
real Exotel capture ever becomes possible it goes in as `<name>_exotel.wav`, and the
tool prefers it over the simulation automatically.

Any format ffmpeg can read. They are canonicalised to 16 kHz mono s16le by the same
decode every other row in the diagnosis goes through, so no conversion is needed
first.

## Path C, and why it is simulated

**There is no Exotel streaming adapter.** `acquisitions/exotel/__init__.py` is a
docstring, and `AGENTS.md` still lists "can the provider stream call audio during the
call, or only hand over a recording afterwards" as open and blocking.

So the only Exotel audio obtainable today is a **recording export**, and
`ml/README.md` already measured that: 8 kHz mono at 8 kb/s mp3, where known-bonafide
ASVspoof audio scores 0.999 on 8 of 8 clips, and re-encoding upward recovers nothing.
A path C captured from an export would measure that codec cliff, which is already
characterised, rather than the acquisition channel, and it would move both classes
for a reason that has nothing to do with the channel.

`--simulate-exotel` derives path C from each path B recording through G.711 mu-law at
64 kb/s, which is what `ml/README.md` records the live stream as carrying and which
scores 0.000 on known-bonafide audio, identical to studio.

**What it models:** the codec of the live leg, only. **What it does not model:**
network jitter, packet loss, the bridge's gain handling, and any resampling inside
the provider. Every simulated row carries `channel: phone_g711_sim` and says
SIMULATED in its notes, so it can never be read as a real call.

**No gate rule reads path C.** Rules 3, 4 and 5 all read `delta_genuine_phone`, which
is path B. Path C is context, not a decision input, so simulating it costs nothing
the gate depends on.

## The conditions file, required

Write `data/replay/capture_conditions.json` before running the tool. It refuses to
score any replayed capture without it, because a confounded experiment that produces
numbers is worse than one that produces none.

```json
{
  "speaker_volume": "60%, system slider, unchanged across all ten",
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
.venv\Scripts\python.exe -m ml.tools.transplant --all-subjects --simulate-exotel
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

`overlap` is 0.0 by construction with one clip per class. `--all-subjects` fixes it;
with one subject the tool now says so, rather than letting 0.0 read as healthy
separation. `gap` is printed beside it either way and goes negative when the classes
invert.

**`delta_spoof` is capped by how high the path A spoof score already is.** Four of the
five deepfakes score 0.85 or above, so their `delta_spoof_phone` cannot exceed 0.15
whatever the channel does. Rule 4 asks for it to exceed 0.40, which is arithmetically
impossible on four of five subjects, and a spoof cell saturating to 1.0 lands on Rule
3's `< 0.15` "spoof stayed put" threshold instead. Rules 3 and 4 lead to opposite
decisions.

So **read the absolute path B scores, not only the deltas.** If the path B spoof
scores sit at 1.0 the distribution saturated, which is Rule 4, even though the delta
is small. `sadhguru_deepfake` at 0.1279 is the only subject with room to move and is
the one to watch.
