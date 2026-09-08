import { randomUUID } from 'node:crypto'

const SCHEMA_VERSION = '1.0'

export function makeSessionStart({ streamId, callId, protectedNumber = null }) {
  return {
    kind: 'session_start',
    stream_id: streamId,
    call_id: callId,
    started_at: new Date().toISOString(),
    protected_number: protectedNumber,
    schema_version: SCHEMA_VERSION,
  }
}

// Mirrors contracts/risk.py DEFAULT_BAND_MAPPING. Correct for this mock
// server to compute, since it stands in for the backend, which owns this
// derivation. The dashboard itself must never do this.
function bandFromScore(score) {
  if (score >= 90) return 'critical'
  if (score >= 70) return 'high'
  if (score >= 40) return 'medium'
  return 'low'
}

export function makeRiskUpdate({
  streamId,
  callId,
  sequence,
  score,
  verdict,
  confidence,
  reasons = [],
  contributingChecks = [],
  degradedChecks = [],
}) {
  return {
    kind: 'risk_update',
    stream_id: streamId,
    call_id: callId,
    sequence,
    timestamp: new Date().toISOString(),
    score,
    verdict,
    risk_level: bandFromScore(score),
    confidence,
    reasons,
    contributing_checks: contributingChecks,
    degraded_checks: degradedChecks,
    evidence_refs: [],
    schema_version: SCHEMA_VERSION,
  }
}

export function makeCallEnded({ streamId, callId, durationSeconds, finalScore, finalVerdict, reasons = [], raiseAlert = false }) {
  return {
    kind: 'call_ended',
    stream_id: streamId,
    call_id: callId,
    ended_at: new Date().toISOString(),
    duration_seconds: durationSeconds,
    final_score: finalScore,
    final_verdict: finalVerdict,
    final_level: bandFromScore(finalScore),
    reasons,
    alert_fingerprint: raiseAlert ? randomUUID().replace(/-/g, '') : null,
    merkle_root: raiseAlert ? randomUUID().replace(/-/g, '') : null,
    sealed_record_id: raiseAlert ? randomUUID() : null,
    root_published_at: raiseAlert ? new Date().toISOString() : null,
    schema_version: SCHEMA_VERSION,
  }
}
