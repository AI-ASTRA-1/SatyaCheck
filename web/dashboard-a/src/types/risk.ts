/**
 * Hand-written TypeScript mirror of contracts/risk.py and contracts/checks.py,
 * for reference only. Never imported by contracts/, and not the source of
 * truth: contracts/*.py is. Keep in sync by hand if the Pydantic models change.
 */

export type RiskVerdict = 'genuine' | 'synthetic' | 'unknown'
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export type CheckName = 'machine_fingerprint' | 'speaker_identity' | 'prosody' | 'stt_llm'

export type ReasonCode =
  | 'fingerprint_synthetic'
  | 'fingerprint_genuine'
  | 'voiceprint_no_enrolment'
  | 'voiceprint_no_match'
  | 'voiceprint_match'
  | 'voiceprint_match_synthetic'
  | 'prosody_anomaly'
  | 'prosody_normal'
  | 'script_risk_high'
  | 'script_risk_absent'
  | 'context_high_risk'
  | 'context_low_risk'
  | 'insufficient_audio'
  | 'degraded_check'

export interface SessionStart {
  kind: 'session_start'
  stream_id: string
  call_id: string
  started_at: string
  protected_number: string | null
  schema_version: string
}

export interface RiskUpdate {
  kind: 'risk_update'
  stream_id: string
  call_id: string
  sequence: number
  timestamp: string
  score: number
  verdict: RiskVerdict
  risk_level: RiskLevel
  confidence: number
  reasons: ReasonCode[]
  contributing_checks: CheckName[]
  degraded_checks: CheckName[]
  evidence_refs: string[]
  schema_version: string
}

export interface CallEnded {
  kind: 'call_ended'
  stream_id: string
  call_id: string
  ended_at: string
  duration_seconds: number
  final_score: number
  final_verdict: RiskVerdict
  final_level: RiskLevel
  reasons: ReasonCode[]
  alert_fingerprint: string | null
  merkle_root: string | null
  sealed_record_id: string | null
  root_published_at: string | null
  schema_version: string
}

export type AppMessage = SessionStart | RiskUpdate | CallEnded
