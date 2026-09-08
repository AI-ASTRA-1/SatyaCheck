export interface Stat {
  value: string
  label: string
  source?: string
  verified: boolean
  caveat?: string
}

export const heroStats: Stat[] = [
  { value: '~30s', label: 'of audio is enough to clone a voice', verified: true },
  { value: '~1/s', label: 'the risk score updates, continuously, for the life of the call', verified: true },
]

export const gapStats: Stat[] = [
  {
    value: '2.85%',
    label: 'lab equal error rate, ASVspoof 2021 DF',
    source: 'Tak et al., Odyssey 2022 · arXiv:2202.12233',
    verified: true,
  },
  {
    value: '35.24%',
    label: 'real-world equal error rate across 14 languages and 7 platforms, ML-ITW benchmark',
    source: 'Wuhan University',
    verified: false,
    caveat: 'ID not verified. A human confirms this citation before it is presented as fact.',
  },
]

export const proofStats: Stat[] = [
  {
    value: '~85K',
    label: 'parameters in AASIST-L, runs on CPU',
    source: 'Jung et al., ICASSP 2022 · arXiv:2110.01200',
    verified: true,
  },
  { value: '<400ms', label: 'spoken word to warning on screen, p90', verified: true },
  { value: '100-330ms', label: 'added by a virtual-number bridge', verified: true },
  { value: '6-9 months', label: 'to pilot-ready on a single bank inbound line', verified: true },
]
