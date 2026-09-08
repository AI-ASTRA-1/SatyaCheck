import type { CheckName, ReasonCode } from '../types/risk'

export const checkLabels: Record<CheckName, string> = {
  machine_fingerprint: 'Machine fingerprint (XLS-R + AASIST)',
  speaker_identity: 'Speaker identity (ECAPA-TDNN)',
  prosody: 'Prosody (openSMILE)',
  stt_llm: 'Script pattern (STT + LLM)',
}

export const reasonLabels: Record<ReasonCode, string> = {
  fingerprint_synthetic: 'Waveform looks synthetic',
  fingerprint_genuine: 'Waveform looks genuine',
  voiceprint_no_enrolment: 'No enrolled voiceprint to compare (expected in Round 1)',
  voiceprint_no_match: 'Voice does not match an enrolled speaker',
  voiceprint_match: 'Voice matches an enrolled speaker',
  voiceprint_match_synthetic: 'Matches an enrolled voiceprint, but looks synthetic',
  prosody_anomaly: 'Rhythm and pitch look anomalous',
  prosody_normal: 'Rhythm and pitch look normal',
  script_risk_high: 'Script matches a known scam pattern',
  script_risk_absent: 'No scam-script pattern detected',
  context_high_risk: 'Call context looks high risk',
  context_low_risk: 'Call context looks low risk',
  insufficient_audio: 'Not enough audio yet',
  degraded_check: 'A check ran in a degraded state',
}
