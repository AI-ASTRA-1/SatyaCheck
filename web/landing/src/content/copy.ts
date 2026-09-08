export interface ScrollStoryStepData {
  visual: 'acquisition' | 'copy' | 'checks' | 'fusion' | 'evidence'
  eyebrow: string
  heading: string
  body: string
}

export const copy = {
  nav: {
    brand: 'SatyaCheck',
    links: [
      { href: '#how-it-works', label: 'How it works' },
      { href: '#the-gap', label: 'The gap' },
      { href: '#scope', label: 'Roadmap' },
    ],
    cta: 'Open the dashboard',
  },
  hero: {
    eyebrow: 'SIH26104 · Team AI ASTRA',
    headline: 'A live warning when the voice on the call might not be real.',
    sub: "SatyaCheck raises a warning during a live call when a voice looks synthetic. It never decides for you, and it never touches the call itself. A controlled live-warning prototype, not a finished product.",
    ctaPrimary: 'See how it works',
    ctaSecondary: 'Open the dashboard',
  },
  problem: {
    eyebrow: 'Why this matters',
    heading: 'The scammer installs nothing. Only you opt in.',
    body: 'A cloned voice needs about 30 seconds of audio and no cooperation from the person being protected. SatyaCheck listens on a copy of the call your side receives, the same way a fraud line would, and never requires the caller to install or agree to anything.',
  },
  howItWorks: {
    eyebrow: 'How it works',
    heading: 'Seven stages, one continuous score.',
    intro: 'Every stage is budgeted in milliseconds. The score updates roughly once a second for the life of the call, never as a single verdict at the start.',
    steps: [
      {
        visual: 'acquisition',
        eyebrow: '01 · Call source',
        heading: 'The call arrives through Exotel, or WebRTC if it must.',
        body: 'Exotel is the primary path: the protected call streams to SatyaCheck while continuing normally through Exotel. If that streaming is limited, WebRTC is the fallback. Either way, the caller installs nothing.',
      },
      {
        visual: 'copy',
        eyebrow: '02-03 · Ingestion and pipeline',
        heading: 'Detection runs on a copy. The live call is never touched.',
        body: 'Audio is decoded, framed, and buffered out-of-band. If a model fails, the call degrades to no warning, never to a dropped or altered call.',
      },
      {
        visual: 'checks',
        eyebrow: '04 · Four checks, in parallel',
        heading: 'Machine fingerprint, speaker identity, prosody, script pattern.',
        body: 'Four models run in parallel, on the copy, inside a shared 180ms budget. Each returns evidence, never a verdict.',
      },
      {
        visual: 'fusion',
        eyebrow: '05 · Risk fusion',
        heading: 'One continuous score, 0 to 100, updated roughly once a second.',
        body: 'The risk engine folds in the four checks alongside call context, number reputation, and history. It is the only place a decision is made.',
      },
      {
        visual: 'evidence',
        eyebrow: '06-07 · Response and evidence',
        heading: 'A warning is shown as a state. Every alert is sealed.',
        body: 'The risk level drives the warning; the score is never re-derived on screen. Each alert is fingerprinted and folded into a Merkle tree with a published root.',
      },
    ] satisfies ScrollStoryStepData[],
  },
  fourChecks: {
    eyebrow: 'Four checks, in parallel',
    heading: 'Every check emits evidence. Only the risk engine decides.',
    intro: 'No single model returns a final verdict. Four checks run in parallel, on a copy of the audio, inside a shared 180ms budget.',
    checks: [
      { name: 'Machine fingerprint', model: 'XLS-R + AASIST', question: 'Is the waveform itself synthetic?' },
      {
        name: 'Speaker identity',
        model: 'ECAPA-TDNN',
        question: 'Is this who they claim to be? No enrolment store yet, so a neutral state is expected, not a gap.',
      },
      { name: 'Prosody', model: 'openSMILE', question: 'Does the rhythm and pitch look anomalous?' },
      {
        name: 'Script pattern',
        model: 'Speech-to-text, then a language model',
        question: 'Does the script match a known scam pattern? The transcript itself is never stored.',
      },
    ],
  },
  gap: {
    eyebrow: 'The honest number',
    heading: 'Lab conditions are not the real world.',
    body: "Detecting synthetic speech in the real world, across accents, phone networks, and languages, remains an unsolved research problem. This is the gap the project exists to close, not a gap we're hiding.",
  },
  scope: {
    eyebrow: 'Scope, honestly',
    heading: 'What is built for this round, and what is described for the next.',
    rows: [
      { round1: 'Audio acquisition (Exotel primary, WebRTC fallback)', round2: 'Family Vault enrolment and consent flow' },
      { round1: 'Detection model on the live stream, score updating continuously', round2: 'Transcript-based scam-script detection' },
      { round1: 'Risk display with a clear warning state', round2: 'Payment-blocking integration with a bank' },
      { round1: 'Training pipeline with phone compression and noise built in', round2: 'On-device inference' },
      { round1: 'Evaluation on unseen data, including Indian-accented genuine speech', round2: '' },
      { round1: 'Alert fingerprinting and the sealed record', round2: '' },
    ],
  },
  evidence: {
    heading: 'Nothing is stored that does not need to be.',
    body: "SatyaCheck stores voice embeddings, never raw audio. Enrolment audio is deleted immediately after a voiceprint is made. Every alert is fingerprinted and folded into a Merkle tree with a published root, so a single alert can be proven to exist and predate a transfer, without exposing anyone else's call. No voice data ever goes on a ledger.",
  },
  cta: {
    heading: 'See the live risk view.',
    body: 'The dashboard is a fallback web view of the same risk signal the mobile app shows during a call. The mobile app is the primary experience.',
    button: 'Open the dashboard',
  },
  footer: {
    status: 'A controlled live-warning prototype. Real-world deployment after validation.',
    credit: 'Team AI ASTRA · SIH26104 · Blockchain and Cybersecurity',
  },
}
