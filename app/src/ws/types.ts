/**
 * TypeScript mirror of contracts/risk.py AppMessage union.
 *
 * Source of truth: contracts/risk.py (Pydantic models).
 * Do not add, rename, or drop fields relative to those models.
 * Do not import from Python; this file reproduces the shape for the TypeScript side.
 *
 * schema_version: "1.0"
 */

// ---- Enums (contracts/risk.py) ----------------------------------------

/** contracts/risk.py RiskVerdict */
export type RiskVerdict = "genuine" | "synthetic" | "unknown";

/** contracts/risk.py RiskLevel */
export type RiskLevel = "low" | "medium" | "high" | "critical";

// ---- Enum strings (contracts/checks.py) --------------------------------

/** contracts/checks.py CheckName */
export type CheckName =
  | "machine_fingerprint"
  | "speaker_identity"
  | "prosody"
  | "stt_llm";

/** contracts/checks.py ReasonCode */
export type ReasonCode =
  | "fingerprint_synthetic"
  | "fingerprint_genuine"
  | "voiceprint_no_enrolment"
  | "voiceprint_no_match"
  | "voiceprint_match"
  | "voiceprint_match_synthetic"
  | "prosody_anomaly"
  | "prosody_normal"
  | "script_risk_high"
  | "script_risk_absent"
  | "context_high_risk"
  | "context_low_risk"
  | "insufficient_audio"
  | "degraded_check";

// ---- Message shapes (contracts/risk.py) --------------------------------

/**
 * contracts/risk.py SessionStart
 * Call started. App shows a subtle scanning indicator.
 */
export interface SessionStart {
  kind: "session_start";
  stream_id: string;
  call_id: string;
  /** ISO-8601 datetime string */
  started_at: string;
  /** The enrolled user's own number. null when no enrolment (Round 1). */
  protected_number: string | null;
  schema_version: string;
}

/**
 * contracts/risk.py RiskUpdate
 * One scoring tick, roughly once per second while the call is live.
 */
export interface RiskUpdate {
  kind: "risk_update";
  stream_id: string;
  call_id: string;
  /** Monotonic scoring tick index from 0. */
  sequence: number;
  /** ISO-8601 datetime string */
  timestamp: string;
  /** 0-100 integer. App renders risk_level, never derives a band from this. */
  score: number;
  verdict: RiskVerdict;
  risk_level: RiskLevel;
  /** 0.0-1.0 aggregate signal confidence. Not a threshold. */
  confidence: number;
  reasons: ReasonCode[];
  contributing_checks: CheckName[];
  degraded_checks: CheckName[];
  /** Opaque identifiers only. No audio, no transcript, no numbers. */
  evidence_refs: string[];
  schema_version: string;
}

/**
 * contracts/risk.py CallEnded
 * Terminal message. Carries the stage 07 evidence summary, nothing sensitive.
 */
export interface CallEnded {
  kind: "call_ended";
  stream_id: string;
  call_id: string;
  /** ISO-8601 datetime string */
  ended_at: string;
  duration_seconds: number;
  /** 0-100 integer */
  final_score: number;
  final_verdict: RiskVerdict;
  final_level: RiskLevel;
  reasons: ReasonCode[];
  /** Present only if an alert was raised. */
  alert_fingerprint: string | null;
  /** Published off-ledger anchor. */
  merkle_root: string | null;
  sealed_record_id: string | null;
  /** ISO-8601 datetime string or null */
  root_published_at: string | null;
  schema_version: string;
}

/**
 * contracts/risk.py AppMessage
 * Discriminated union on `kind`. Parse with a switch on msg.kind.
 */
export type AppMessage = SessionStart | RiskUpdate | CallEnded;
