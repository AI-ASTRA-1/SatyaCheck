function tick(score, verdict, confidence, reasons, contributing, degraded = []) {
  return { score, verdict, confidence, reasons, contributing, degraded }
}

export const scenarios = {
  'genuine-call': {
    ticks: [
      tick(8, 'genuine', 0.9, ['fingerprint_genuine', 'voiceprint_no_enrolment', 'prosody_normal', 'script_risk_absent'], [
        'machine_fingerprint',
        'speaker_identity',
        'prosody',
        'stt_llm',
      ]),
      tick(6, 'genuine', 0.92, ['fingerprint_genuine', 'prosody_normal'], ['machine_fingerprint', 'prosody']),
      tick(9, 'genuine', 0.88, ['fingerprint_genuine', 'context_low_risk'], ['machine_fingerprint']),
      tick(7, 'genuine', 0.91, ['prosody_normal', 'script_risk_absent'], ['prosody', 'stt_llm']),
      tick(10, 'genuine', 0.87, ['fingerprint_genuine'], ['machine_fingerprint']),
    ],
    finalScore: 8,
    finalVerdict: 'genuine',
    raiseAlert: false,
  },
  'cloned-voice': {
    ticks: [
      tick(20, 'unknown', 0.55, ['insufficient_audio'], []),
      tick(38, 'unknown', 0.6, ['fingerprint_synthetic'], ['machine_fingerprint']),
      tick(55, 'synthetic', 0.68, ['fingerprint_synthetic', 'prosody_anomaly'], ['machine_fingerprint', 'prosody']),
      tick(72, 'synthetic', 0.76, ['fingerprint_synthetic', 'prosody_anomaly', 'context_high_risk'], [
        'machine_fingerprint',
        'prosody',
      ]),
      tick(88, 'synthetic', 0.85, ['fingerprint_synthetic', 'voiceprint_match_synthetic', 'context_high_risk'], [
        'machine_fingerprint',
        'speaker_identity',
        'prosody',
      ]),
      tick(96, 'synthetic', 0.93, ['fingerprint_synthetic', 'voiceprint_match_synthetic', 'script_risk_high'], [
        'machine_fingerprint',
        'speaker_identity',
        'stt_llm',
      ]),
    ],
    finalScore: 96,
    finalVerdict: 'synthetic',
    raiseAlert: true,
  },
  'degraded-clone': {
    ticks: [
      tick(60, 'unknown', 0.4, ['degraded_check', 'fingerprint_synthetic'], ['machine_fingerprint'], ['prosody']),
      tick(45, 'unknown', 0.35, ['degraded_check'], [], ['prosody', 'stt_llm']),
      tick(70, 'synthetic', 0.5, ['fingerprint_synthetic', 'degraded_check'], ['machine_fingerprint'], ['speaker_identity']),
      tick(50, 'unknown', 0.38, ['degraded_check', 'insufficient_audio'], [], ['machine_fingerprint', 'prosody']),
      tick(80, 'synthetic', 0.55, ['fingerprint_synthetic', 'voiceprint_match_synthetic'], ['machine_fingerprint', 'speaker_identity'], [
        'stt_llm',
      ]),
      tick(55, 'unknown', 0.42, ['degraded_check'], [], ['prosody']),
    ],
    finalScore: 62,
    finalVerdict: 'unknown',
    raiseAlert: false,
  },
  'all-levels-sweep': {
    ticks: [
      tick(10, 'genuine', 0.9, ['fingerprint_genuine'], ['machine_fingerprint']),
      tick(15, 'genuine', 0.88, ['prosody_normal'], ['prosody']),
      tick(30, 'genuine', 0.85, ['context_low_risk'], []),
      tick(45, 'unknown', 0.6, ['fingerprint_synthetic'], ['machine_fingerprint']),
      tick(55, 'unknown', 0.58, ['prosody_anomaly'], ['prosody']),
      tick(65, 'unknown', 0.62, ['context_high_risk'], []),
      tick(75, 'synthetic', 0.7, ['fingerprint_synthetic', 'prosody_anomaly'], ['machine_fingerprint', 'prosody']),
      tick(82, 'synthetic', 0.74, ['voiceprint_match_synthetic'], ['speaker_identity']),
      tick(88, 'synthetic', 0.78, ['script_risk_high'], ['stt_llm']),
      tick(92, 'synthetic', 0.9, ['fingerprint_synthetic', 'voiceprint_match_synthetic'], ['machine_fingerprint', 'speaker_identity']),
      tick(97, 'synthetic', 0.95, ['fingerprint_synthetic', 'script_risk_high'], ['machine_fingerprint', 'stt_llm']),
    ],
    finalScore: 97,
    finalVerdict: 'synthetic',
    raiseAlert: true,
  },
}

export const DEFAULT_SCENARIO = 'all-levels-sweep'
