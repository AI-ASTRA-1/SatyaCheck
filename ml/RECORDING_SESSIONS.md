# Recording sessions: where, what to say, how many people

Companion to [`BENCHMARK_FORMAT.md`](BENCHMARK_FORMAT.md), which specifies the file
format. This one is the field guide for actually running a session. Owner R1.

Print it or keep it open during recording. The person running the session should not
need to ask anyone anything.

---

## 1. How many people

**Current scope, decided 2026-09-07: the 6 team members only.** Recruiting outside
speakers does not fit the time available. The population-level false positive rate
is a later phase, and `BENCHMARK_FORMAT.md` is its specification.

That decision is workable, but it changes what the recordings can be used to say,
and the difference is not cosmetic.

### What 6 speakers can and cannot support

| Can | Cannot |
|---|---|
| All three demo items | A false positive rate |
| A paired within-speaker study of score shift across codecs and SNR | Any claim about speakers outside the team |
| A direction-of-effect result with a real significance value | A number to put on a slide as "our false positive rate" |
| The clone source for demo item 2 | Anything about accents nobody on the team has |

With zero false positives across 6 speakers, the 95% upper bound on the true rate is
roughly `3/6`, that is **about 50%**. A rate computed from 6 people is not a weak
result, it is not a result.

### The design that does work at n=6: pair every speaker with themselves

Do not compare speakers to each other. Compare each speaker's identical utterance
across conditions, so every speaker is their own control:

```
clean master -> G.711 -> AMR-NB -> Opus -> SNR 20 -> SNR 10 -> SNR 5
```

The quantity measured is **how much a genuine speaker's score moves when the audio
goes through a phone**, not how often anyone gets flagged. That question is
answerable with 6 people because the comparison is within-speaker, and the
speaker-to-speaker variation that ruins small-sample rates cancels out.

It even carries a legitimate significance value. If all 6 speakers' scores move in
the same direction under a given condition, a two-sided sign test gives
`2 * (1/2)^6`, about **p = 0.031**. That is a defensible statistical claim from six
people, and it is exactly the "volunteer a weakness with a number attached" move the
demo plan asks for.

### The trap: windows are not speakers

Six speakers at 90 seconds each yields well over a hundred 4-second analysis windows,
and more still once every codec and SNR condition is counted. It will be tempting to
report those as that many samples. **They are not independent.** Windows from one
person are one person, and the same utterance through seven conditions is one
utterance. Any figure derived from this data reports `n = 6 speakers` in the same
sentence, however many windows went into it. A judge who knows statistics will ask,
and having the answer ready is worth more than the inflated number.

### Session budget, decided 2026-09-07

**90 seconds per speaker, one session, one device.** Time is the binding constraint.

- **90 s of usable speech each**, split across the four categories in section 3.
- **One session.** No second visit, so day-to-day voice variation is uncontrolled
  and unmeasured. Write that down as a limitation rather than leaving it implied.
- **One device for all six**, a phone recording uncompressed. Same handset, same room,
  same position, so the recording chain is not a variable. Details in section 2.
- **The clone-source take is extra and separate.** It is not part of the 90 s, and
  only the one or two people being cloned for the demo need it. Cloning from the same
  audio you later evaluate against measures nothing.
- **Record the metadata honestly.** If all six share a first language, that is a
  limitation to write down, not to leave for someone else to notice.

Ninety seconds gives roughly 22 non-overlapping 4-second windows per speaker. That
is enough for a stable per-speaker mean, which is what the paired design needs.
Where more analysis points help, slide the window with a 1 s hop instead of stepping
4 s. That is legitimate for estimating one speaker's mean and is **not** a way to
increase `n`: overlapping windows are less independent, not more.

### What 90 seconds costs

Four categories inside 90 s is about 20 seconds each, roughly 5 windows. Comparisons
**across conditions** hold up, because those are paired on identical audio.
Comparisons **across categories**, such as "urgent speech scores higher than read
speech", do not: 5 windows per cell is too noisy to claim anything. If a
category-level result turns out to matter later, it needs its own longer session.

### Later, when the false positive rate is actually built

The spread and count requirements live in `BENCHMARK_FORMAT.md`. The short version:
30 speakers is the floor and 50 a target, across at least 5 first languages, because
the 95% upper bound with a clean sweep is roughly `3/n`. Recording all of those is
not the only route; public Indian-accented corpora may supply the genuine side
without any recruiting, which is noted there as an option needing a licence check.

---

## 2. Where to record

### Pick the room by its sound, not its label

You want low reverberation and a low noise floor. A soft, small, cluttered room
beats a large clean one every time.

| Good | Bad |
|---|---|
| Bedroom with a bed, curtains, wardrobe | Classroom or lecture hall |
| A parked car with the engine off | Lab or computer room, fan noise |
| Small room with soft furnishings, clothes, cushions | Corridor, stairwell, atrium |
| A wardrobe or a corner behind hanging clothes | Kitchen, bathroom, anywhere tiled |

A parked car is genuinely one of the best options available to a student team:
enclosed, heavily upholstered, almost no reverb, and you can move it away from
noise.

### The clap test, ten seconds

Stand where the speaker will sit and clap once, hard. If you hear a ring, a slap
back off a wall, or the sound hanging on after the clap, the room is too live. Add
soft material or move. Do this once per room, not once per speaker.

### Before the first take

- Air conditioning, fans and coolers **off**. Not low. Off.
- Fluorescent and cheap LED lights off if they buzz, work by daylight.
- Every phone in the room on **airplane mode**, not silent, including the one doing
  the recording. Airplane mode does not stop it recording, and it does stop a call or
  a notification landing in the middle of a take. Silent mode stops neither the
  interruption nor the buzzing that cellular radio induces in nearby microphones.
- Close windows. Note traffic, construction, birds, and generators, and wait them
  out rather than recording through them.
- Fridge and water pump off if they are audible.

### Microphone and position

- 15 to 20 cm from the mouth, roughly a hand span.
- **Slightly off to one side**, not straight in front of the lips. This is what
  stops plosive pops on "p" and "b" more than any filter.
- **Find the phone's microphone first.** It is usually a pinhole on the bottom edge,
  not the earpiece. Aim that end at the speaker and keep fingers off it.
- **Do not hold the phone in your hand while speaking.** Hand tremor and grip changes
  are recorded as low-frequency rumble and are unrecoverable. Prop it against a book,
  rest it on a folded cloth, or have the session runner hold it steady. Whatever you
  choose, do it the same way for all six.
- Same distance and same mounting for every speaker. Varying either changes level and
  room tone and becomes a hidden variable.
- A cheap pop filter helps. So does a single layer of cloth stretched over a wire
  loop, at zero cost.
- Speaker seated, feet flat, still. Chair creaks land in the recording too.

### Turn the processing off. This is the step people skip

Recording apps apply noise suppression, automatic gain and echo cancellation by
default, and these are exactly the nonlinear processes that change what a
synthetic-speech detector sees. Leave them on and every recording becomes a silently
different condition, in a way nobody notices until the results make no sense.

The app settings and the ten-second test that catches a processed input are in the
device section below. Get that right once, before speaker one, and it holds for the
whole session.

Target peaks between -12 and -6 dBFS. Never let it clip. If the meter touches the
top, move the phone slightly further away and re-record; clipping cannot be undone.

### Device: one phone, for all six speakers

**Use a phone, not a laptop, and use the same phone for everyone.**

A modern phone microphone beats almost any laptop built-in, and it is held near-field
so it captures far less room. Laptop microphones are far-field, usually mediocre, and
frequently have noise suppression and beamforming applied in the driver that cannot
be fully disabled. Use a USB microphone instead only if someone actually owns one.

One device for all six matters as much as which device. Same phone, same room, same
position, so the recording chain is not a variable. Passing one handset around costs
nothing and removes an entire confound.

| Setting | Value |
|---|---|
| Format | WAV or another uncompressed format, never a voice-note codec |
| Sample rate | 48 kHz, or the highest the app offers |
| Channels | mono if the app allows it, otherwise convert afterwards |
| Distance | 15 to 20 cm, held steady, slightly off to one side of the mouth |
| Enhancement | off, see below |

On iPhone, Voice Memos with Audio Quality set to Lossless and **Enhance Recording
turned off**. On Android the recorder apps vary too much to name one, so pick any app
that can save uncompressed WAV at 48 kHz with no noise reduction, and then verify it
with the test below rather than trusting the description.

Never record through WhatsApp, Zoom, Meet or Teams. All of them apply heavy
processing and a lossy codec, and some of it cannot be turned off.

**The ten-second test that catches a processed input.** Record 10 seconds of the room
with nobody speaking, then 10 seconds of normal talking, in one take. Listen to the
background noise underneath the speech. If the background drops away when the speech
starts and swells back in the gaps, the app is applying noise suppression. Find
another app. That pumping is exactly the kind of nonlinear artefact that changes what
a synthetic-speech detector sees.

### One handset-versus-simulation spot check

Every degraded condition is generated in software from the clean master. Whether that
resembles a real phone channel is an open question in `BENCHMARK_FORMAT.md`, and one
recording is the cheapest partial answer available.

If a landline or a second phone is to hand, have **one** speaker repeat the read
passage through an actual call while it is recorded at the far end. Two extra minutes,
one person. It will not settle the question, but it shows whether simulated G.711 and
a real phone leg are in the same neighbourhood or nowhere near each other.

---

## 3. What to say

90 seconds of usable speech per speaker, across four categories.

**One continuous recording per speaker, split into four files afterwards.** Do not
stop the recorder between takes. Phone input gain settles over the first second or
two of a new recording, so four separate recordings can land at four slightly
different levels, and level is precisely the kind of hidden variable that ruins a
paired comparison. One recording is one gain state. It also removes any chance of
forgetting to press record.

**A gap goes between every take, not only at the start and end of the recording.**
The gaps are the cut markers. Without one at each boundary there is no way to find
where take 2 ends and take 3 begins except by listening through.

The whole session file for one speaker looks like this:

```
[5 s room tone, nobody speaks at all]
"take one"    [3 s silence]  speech 1  [3 s silence]
"take two"    [3 s silence]  speech 2  [3 s silence]
"take three"  [3 s silence]  speech 3  [3 s silence]
"take four"   [3 s silence]  speech 4  [3 s silence]
stop
```

Each announcement sits inside silence on both sides, so the cut lands in the quiet
and takes the runner's voice with it, without clipping the speaker's first word.

### The gaps are also the noise floor reference

Do not skip the 5 seconds of room tone at the head, and do not trim the gaps away
when splitting more tightly than necessary. Adding noise at a controlled SNR requires
knowing the room's existing noise level, measured **on the same device in the same
room**, and these silent stretches are the only recording of that you will have.
Without them the SNR figures are computed against a baseline nobody measured.

Save the leading room tone as its own file per speaker,
`spk_NN_roomtone_00_clean.wav`, alongside the four takes.

If a take goes wrong, do not restart the whole session. Finish the remaining takes,
then record the bad one again at the end as its own short file and use that one.

| Category | Target | Why it is in the set |
|---|---|---|
| 1 Read, neutral | 25 s | identical text for all six, the only cross-speaker control |
| 2 Spontaneous | 25 s | real rhythm and disfluency, unlike read speech |
| 3 Urgent | 20 s | stressed prosody is a plausible false-positive trigger |
| 4 Code-switched | 20 s | how Indian phone calls actually sound, covered by no corpus |

Slightly over is fine, slightly under is not. Trim in post, never pad.

### Two rules that override everything below

**Never record real personal data.** No real OTPs, account numbers, card numbers,
addresses, or anyone's actual phone number. The digits below are invented and
should stay invented.

**Never record fraud-usable content.** These voices get cloned. A cloned voice
saying "transfer the money now, do not hang up" is not a test asset, it is a
working attack tool. We need urgent *prosody*, and we do not need urgent
*instructions*. The prompts below are built to give the first without the second.

### Category 1: read speech, neutral (25 s)

Same passage for every speaker, so the passage is not a variable. It is built around
what a call actually contains: digits, amounts, names and questions, rather than a
literary passage that shares nothing with the target domain. About 60 words, which
lands near 25 s at a normal pace.

> Good morning. My name is Ravi Sharma and I am calling from the district office
> near the railway station. The train number is one two four seven and it reaches
> the city at half past six. Last month the total came to two lakh forty thousand
> rupees. Could you confirm whether the meeting is on Thursday or Friday? Thank you
> very much.

Read it at a normal speaking pace. Not a newsreader voice, not a performance.
Speakers should use their own name pronunciation habits and not attempt an accent.

### Category 2: spontaneous speech (25 s)

Pick one prompt and let them talk. Unscripted speech has different rhythm and
disfluency from read speech, and a detector that only ever sees read speech is
being tested on the easy case.

- Describe how you travel to college or work, step by step.
- What did you eat yesterday, and who cooked it?
- Explain the rules of a game or sport you like to someone who has never seen it.
- Describe the street you grew up on.
- What is the most useful app on your phone and why?
- Talk about a film or show you finished recently, without spoiling the ending.

Do not interrupt. A pause of two or three seconds is fine and is realistic. If they
dry up before 25 seconds, ask one follow-up question and keep recording.

### Category 3: urgent or stressed speech (20 s)

Scam calls are urgent by construction, and stressed prosody is a plausible reason a
detector would flag a real person. It must be in the benchmark. None of these
prompts produce audio that is useful to a fraudster.

- You are 20 minutes late to meet a friend. Explain why, while walking fast.
- You have just missed your train. Tell someone what happened and what you will do.
- You have lost your bag somewhere on campus. Describe it and ask them to look.
- Your neighbour's tap has been running for an hour. Tell them, urgently.
- You are about to miss a submission deadline. Explain the situation out loud.

Ask for genuine urgency in the voice, not acting. Standing up helps. Slightly raised
volume, faster rate, and a higher pitch are exactly the features we want captured.

### Category 4: code-switched speech (20 s)

This is how an enormous number of Indian phone calls actually sound, and no public
benchmark covers it.

- Explain the read passage above to a family member, in the way you would naturally
  say it, mixing languages as you normally do.
- Describe your journey home, switching languages the way you would with a friend.
- Give directions from the recording room to the nearest tea stall.

Tell them explicitly not to keep it in one language. Natural mixing is the point.

### Additional take: clone source (60 s, from consenting team members)

Separate from everything above, and used only as input to the cloning tool. It must
not be reused as evaluation audio, because building a clone from a file and then
testing against that same file measures nothing.

Content can be any of the above categories. Roughly 30 seconds is enough to clone a
voice; 60 gives margin.

---

## 4. Session runsheet, about 10 minutes per person

90 s of speech, but the session is not 90 s. Consent, metadata, level check and
listen-back are what make the recordings usable, and they are where the time goes.
Six people in roughly an hour, plus one-off room setup.

1. **Consent first, before the microphone is on.** Two separate permissions:
   recording, and cloning. Cloning is only asked of the one or two people whose voice
   the demo clones. Written, signed, revocable, and the reference goes in the manifest
   as `consent_ref`.
2. **Metadata.** `speaker_id` (opaque, e.g. `spk_014`), first language, region, age
   band, self-described gender if they wish, device class. No names, no numbers.
3. **Level check.** 10 seconds of talking, watch the meter, adjust gain, listen back
   on headphones. Check for hum, hiss, clipping and room ring.
4. **Record one continuous file**, takes 1 to 4 in order, announcing each take number
   and leaving 3 seconds of silence either side. Do not stop between takes.
5. **Listen back to at least part of the recording before the speaker leaves.** This
   is the step that saves the session. A speaker who has gone home cannot be
   re-recorded.
6. **Save the continuous file as `spk_NN_session.wav`** and keep it. It is the
   archival master and is never deleted, even after splitting.
7. **Split and label** using the naming scheme in `BENCHMARK_FORMAT.md`, then add the
   manifest rows. Files named later are files named wrongly.

### Splitting the session file

Cut in the silent gaps. Audacity makes the gaps easy to see and is the simpler route
for whoever has not used ffmpeg. On the command line, PCM WAV is sample-addressable so
a stream copy cuts exactly, with no re-encoding and no quality loss:

```
ffmpeg -i spk_01_session.wav -ss 00:00:04 -to 00:00:29 -c copy spk_01_read_01_clean.wav
```

Four cuts per speaker, 24 files from six sessions. Do not resample here: the split
files stay at the 48 kHz capture rate and remain the masters. The 16 kHz pipeline
version and every codec and SNR condition are generated from them later.

Trim the runner's voice out with the gap. If a take number is audible at the head of a
split file, the cut was too early.

### What makes a take unusable

Redo it rather than keeping it:

- any clipping
- a phone notification, a door, a vehicle horn, another person's voice
- the speaker laughing mid-sentence or breaking character in an urgent take
- short of its target in the section 3 table by more than about a quarter
- the recorder was on a processed input after all, audible as pumping background
  noise that rises and falls with the voice

---

## 5. What happens to the recordings

Nothing about the degraded conditions is recorded live. G.711, AMR-NB, Opus and
every SNR level are generated in software from the clean master, so that every
speaker gets identical treatment and any condition can be regenerated from scratch.
That pipeline is the next thing R1 builds.

Storage rules, from `BENCHMARK_FORMAT.md` and `AGENTS.md`, and they are not
negotiable: recordings live outside this repository, no audio is ever committed,
this is held-out evaluation data that is never trained on, and revocation means the
masters, every derived file and any voiceprint computed from them are actually
deleted.
