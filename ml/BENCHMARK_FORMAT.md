# Indian-accent benchmark, recording format specification

A specification, not code, and it exists before any recording is collected. Owner
R1. Re-recording a speaker because the format was wrong is expensive and sometimes
impossible.

> **Status, decided 2026-09-07: the population-level false positive rate is a later
> phase.** Recruiting 30 or more speakers does not fit the time available, so the
> current round records the 6 team members only. See
> [`RECORDING_SESSIONS.md`](RECORDING_SESSIONS.md) section 1 for what 6 speakers can
> and cannot support.
>
> **The file format, metadata and labelling rules below apply to the 6-speaker
> recordings too**, and that is the point of settling them now. Recording the team
> in this format means those sessions become the first rows of the benchmark rather
> than something that has to be redone.

## Why this benchmark exists

No public benchmark covers Indian-accented speech for synthetic-speech detection.
The claim it is meant to support is narrow and specific: **how often do we raise a
warning on a real person?** Proving we do not flag real people is the harder and
more convincing half of the demo, and it is the half most teams skip.

It is not a training set. Training uses ASVspoof, In-the-Wild and MLAAD. This is
held-out evaluation data, and it must never be trained on.

## What to record, and what not to bother with

| Purpose | Recording needed | Why |
|---|---|---|
| Demo item 1, genuine call scores low | yes, team voices | a stranger's voice from a public corpus is not a demo |
| Demo item 2, a clone gets caught | a clone of one team voice | derived from the genuine recording, not a separate session |
| Demo item 3, degraded clone wobbles | none, generated in software | codec and noise are applied to item 2 |
| Indian-accent false positive rate | yes, many speakers | the number this benchmark exists to produce |
| Training the detector | no | public corpora are larger and already labelled |
| Evaluating on unseen data generally | no | In-the-Wild and ASVspoof eval sets |

Genuine speech is the scarce half. Clones are cheap once genuine audio exists,
because roughly 30 seconds is enough to clone a voice.

## Capture format

Record the master as high quality as the equipment allows and degrade in software.
You can always throw detail away; you can never put it back.

| Property | Value |
|---|---|
| Container | WAV, uncompressed PCM |
| Sample rate | 48000 Hz |
| Bit depth | 24-bit, or 16-bit if the device cannot do 24 |
| Channels | mono, one speaker per file |
| Level | peak between -12 and -6 dBFS, no clipping, no limiter, no noise gate |
| Processing | none. No noise suppression, no AGC, no EQ, no "voice enhancement" |

Phone and laptop capture apps often apply noise suppression and automatic gain by
default. Turn it off. Those are exactly the nonlinear processing steps that change
what a synthetic-speech detector sees, and leaving them on silently makes every
recording a different condition.

The 16 kHz mono 16-bit derivative that the pipeline consumes is generated, never
recorded directly:

```
ffmpeg -i master.wav -ac 1 -ar 16000 -sample_fmt s16 derived_16k.wav
```

## Recording conditions

One clean master per utterance, in the quietest room available. Noise and codec
degradation are applied afterwards in software at controlled SNR, so that every
speaker gets identical treatment and any condition can be regenerated. Recording in
a noisy room instead throws away the clean reference and makes the SNR unknown.

Capture every speaker on the **same single device**, so the recording chain is not a
variable. A phone recording uncompressed beats a laptop built-in microphone: it is
near-field, the hardware is usually better, and laptop drivers often apply processing
that cannot be fully disabled. A USB microphone is better still if one is available,
and then that one is used for everybody.

Device variation across speakers is a real effect and belongs in the later
multi-speaker phase, where enough speakers exist for it to be separable from
speaker-to-speaker differences. With a handful of speakers it is a confound, not a
signal, so hold it constant instead. See `RECORDING_SESSIONS.md` for the settings and
the ten-second test that catches a processed input.

Also capture a few seconds of **room tone**, the room with nobody speaking, on the
same device in the same session. Adding noise at a controlled SNR requires knowing
the baseline that is already there, and this is the only recording of it.

## Content per speaker

Minimum 90 seconds of usable speech per speaker, in utterances of 10 to 20 seconds.
The detector's native window is about 4 seconds, so 90 seconds gives roughly 20
independent windows per speaker rather than one.

Cover four categories, because a false positive rate measured only on calm read
speech will not survive a real call:

1. **Read speech, neutral.** Any published passage, same passage across speakers.
2. **Spontaneous speech.** Answer a question, unscripted.
3. **Urgent or stressed speech.** Scam calls are urgent by construction, and
   stressed prosody is a plausible false-positive trigger. Record it deliberately.
4. **Code-switched speech.** English mixed with the speaker's other language, which
   is how a great many Indian phone calls actually sound.

Do not have speakers read scam scripts. That is the transcript channel, it is Round
2, and it has nothing to do with whether the voice is synthetic.

## Speaker metadata

Collect the minimum that supports the claim, and no more. Every field here is
personal data under the DPDP Act 2023.

| Field | Values | Why it is needed |
|---|---|---|
| `speaker_id` | opaque, e.g. `spk_014` | never a name, never a phone number |
| `l1` | first language | the accent claim rests on this |
| `region` | state or region | accent varies within India |
| `age_band` | one of `18-30`, `31-45`, `46-60`, `60+` | band, never a date of birth |
| `gender` | self-described, free text, optional | pitch range differs; optional and self-described |
| `device_class` | `usb_mic`, `laptop_builtin`, `phone_handset` | a real source of variation |

Names, phone numbers, addresses and email addresses are not collected. The mapping
from `speaker_id` to a person, if one is kept at all, is kept outside the dataset
and outside the repo.

## Labelling schema

File name:

```
<speaker_id>_<category>_<take>_<condition>.wav

spk_014_urgent_03_clean.wav
spk_014_urgent_03_g711.wav
spk_014_urgent_03_amrnb.wav
spk_014_urgent_03_snr10.wav
```

`category` is `read`, `spontaneous`, `urgent`, `codeswitch`, or `roomtone` for the
silence captured at the head of each session. `condition` is `clean` for the master
derivative and a generated tag for everything else, so a derived file is always
traceable to its master.

The `roomtone` file is not speech and is never scored. It is the recording of the
room's background noise on the same device, which is what makes an SNR figure mean
something rather than being computed against an unmeasured baseline.

A single `manifest.csv` at the dataset root is the authority:

| Column | Notes |
|---|---|
| `path` | relative to the dataset root |
| `speaker_id` | |
| `label` | `bonafide` or `spoof`. No third value |
| `category` | read, spontaneous, urgent, codeswitch, roomtone |
| `condition` | clean, g711, amrnb, opus, snr20, snr10, snr5 |
| `source_path` | the master this was derived from, empty for a master |
| `duration_s` | |
| `sample_rate` | of this file |
| `l1`, `region`, `age_band`, `gender`, `device_class` | speaker metadata |
| `clone_tool` | for spoof rows only, which system generated it |
| `clone_source_path` | for spoof rows only, the audio the clone was built from |
| `consent_ref` | reference to the signed consent record |

`label` has exactly two values because that is what an EER needs. A clone of an
enrolled speaker is still `spoof`; the three-outcome Family Vault distinction lives
in the speaker identity check, not in this label.

## Making the cloned half

- **Clone only team members who have consented to being cloned specifically.**
  Consent to being recorded is not consent to having your voice cloned. Never clone
  a third party, a public figure, or anyone outside the team.
- **Build the clone from a different recording than the one you evaluate against.**
  Cloning from a file and then testing against that same file measures nothing.
- **Record `clone_tool` for every spoof row.** A detector's performance varies
  enormously by generator, and a result that does not say which generator produced
  the fakes is not interpretable.
- **Check the tool for watermarking before generating in bulk.** If the tool
  watermarks its output and the genuine recordings carry no watermark, the model
  learns the watermark instead of the synthesis. Watermarks go on both classes or
  neither. This has been measured to push error from roughly 16% to 75% in the
  published work, and it is silent when it happens.

## How many speakers

More than feels necessary. A false positive rate is a proportion, and a proportion
from a handful of speakers carries almost no information.

The arithmetic is worth internalising: if zero false positives occur across `n`
speakers, the 95% upper bound on the true rate is roughly `3/n`. Thirty speakers
with a clean sweep still only supports "under about 10%". Ten speakers supports
"under about 30%", which is not a claim worth making, and six supports "under about
50%", which is not a result at all.

So: **30 speakers is a floor, not a target**, and whatever the number is, report it
next to the rate. A false positive rate quoted without its speaker count is not a
result.

### Windows are not speakers

Each speaker yields many 4-second analysis windows, and those windows are not
independent samples. Windows from one person are one person. Every figure derived
from this data states the speaker count in the same sentence, however many windows
went into it. Reporting several hundred windows as several hundred samples is the
single easiest way to turn a defensible result into an indefensible one.

### What is measurable before there are 30 speakers

A within-speaker paired design needs far fewer people, because each speaker acts as
their own control. Score the identical utterance clean, then through each codec and
each SNR level, and the quantity measured is the **score shift under phone
conditions** rather than a population rate. Speaker-to-speaker variation, which is
what ruins small-sample rates, cancels out.

With `n` paired speakers all shifting in the same direction, a two-sided sign test
gives `2 * (1/2)^n`, so six speakers reach about `p = 0.031`. That is a real result
at small `n`. It says nothing about how often a new caller is flagged, and it must
never be described as if it did.

### Sourcing the genuine half without recruiting

The 30-plus speakers do not all have to be recorded by us. Existing Indian-accented
speech corpora may supply the genuine side. Candidates to evaluate, **none of them
verified, and each needs a licence and redistribution check by a human before use**:
Svarah (AI4Bharat), IndicTTS (IIT Madras), Mozilla Common Voice filtered on Indian
accent metadata, and NPTEL lecture speech.

Using an ASR corpus this way does not contradict "no existing benchmark covers it".
That statement is about synthetic-speech *detection* benchmarks. Drawing genuine
Indian-accented audio from an ASR corpus in order to build the missing detection
benchmark is consistent with it. What such corpora will not give you is phone-channel
audio, which is why the codec and noise simulation is applied to them exactly as it
is to our own recordings.

## Privacy and consent

These are product constraints, not paperwork, and they apply to the benchmark
exactly as they apply to the product.

- Consent is explicit, written, and revocable. `consent_ref` in the manifest points
  to the record.
- Revocation means deletion, and deletion must actually delete: masters, every
  derived condition, and any voiceprint computed from them.
- **No audio is committed to this repository.** The root `.gitignore` blocks `*.wav`,
  `*.flac`, `*.mp3`, `*.opus` and `*.amr`, but the rule is the rule regardless of what
  the ignore file catches. The dataset lives outside the repo, alongside the model
  weights.
- Voiceprints derived from these recordings are personal data under the DPDP Act
  2023. Store embeddings, never audio, anywhere the product touches.
- This is held-out evaluation data. Never train on it, and never report a figure
  measured on data resembling the training set.

## Open, and blocking for any published false positive rate

- Which cloning tool or tools generate the spoof half, and whether each watermarks.
- Whether the benchmark is published, and if so under what licence and with what
  consent wording, since publishing recordings of identifiable people is a stronger
  commitment than using them internally.
- Whether phone-handset captures are worth the extra session time, or whether
  software codec simulation from a clean master covers it. Answering this needs a
  measurement, not an opinion: score the same utterance captured on a handset
  against the software-degraded master and compare.
