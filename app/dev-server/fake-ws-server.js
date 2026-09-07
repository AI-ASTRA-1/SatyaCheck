/**
 * Fake WebSocket server for SATYACHECK app development.
 *
 * Emits exactly the AppMessage schema from contracts/risk.py:
 *   - one SessionStart on connect
 *   - RiskUpdate roughly once per second with a realistic score arc
 *   - one CallEnded after CALL_DURATION_S seconds
 *
 * Run:  node app/dev-server/fake-ws-server.js
 * Test: npx wscat -c ws://localhost:8765
 *
 * Fields are the exact Pydantic field names from contracts/risk.py and
 * contracts/checks.py. Do not add, rename, or drop fields relative to
 * those models.
 */

"use strict";

const { WebSocketServer } = require("ws");

const PORT = 8765;
const CALL_DURATION_S = 35;
const TICK_MS = 1000;

// CheckName values from contracts/checks.py CheckName enum
const CHECK_NAMES = [
  "machine_fingerprint",
  "speaker_identity",
  "prosody",
  "stt_llm",
];

// ReasonCode values from contracts/checks.py ReasonCode enum
const REASON_CODES = {
  low: ["fingerprint_genuine", "prosody_normal", "voiceprint_no_enrolment"],
  medium: ["insufficient_audio", "voiceprint_no_enrolment"],
  high: ["fingerprint_synthetic", "prosody_anomaly", "context_high_risk"],
  critical: [
    "fingerprint_synthetic",
    "voiceprint_match_synthetic",
    "prosody_anomaly",
    "script_risk_high",
  ],
};

// Score arc: maps elapsed second -> {score, verdict, risk_level, confidence}
// Simulates genuine call that suddenly turns suspicious at ~15s.
function tickState(seq) {
  if (seq < 8) {
    return { score: 10 + seq, verdict: "genuine", risk_level: "low", confidence: 0.72 };
  }
  if (seq < 14) {
    return { score: 40 + (seq - 8) * 3, verdict: "unknown", risk_level: "medium", confidence: 0.55 };
  }
  if (seq < 20) {
    return { score: 70 + (seq - 14), verdict: "synthetic", risk_level: "high", confidence: 0.80 };
  }
  if (seq < 26) {
    return { score: 90 + Math.min(seq - 20, 8), verdict: "synthetic", risk_level: "critical", confidence: 0.93 };
  }
  // Score starts dropping as call winds down
  const drop = (seq - 26) * 5;
  const score = Math.max(88 - drop, 30);
  if (score >= 90) return { score, verdict: "synthetic", risk_level: "critical", confidence: 0.91 };
  if (score >= 70) return { score, verdict: "synthetic", risk_level: "high", confidence: 0.85 };
  if (score >= 40) return { score, verdict: "unknown", risk_level: "medium", confidence: 0.60 };
  return { score, verdict: "genuine", risk_level: "low", confidence: 0.68 };
}

function isoNow() {
  return new Date().toISOString();
}

function randomId(prefix) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

const wss = new WebSocketServer({ port: PORT });
console.log(`[fake-ws] listening on ws://localhost:${PORT}`);

wss.on("connection", (ws) => {
  const streamId = randomId("stream");
  const callId = randomId("call");
  const startedAt = isoNow();
  let seq = 0;
  let timer = null;

  console.log(`[fake-ws] client connected  stream_id=${streamId}`);

  // 1. SessionStart
  const sessionStart = {
    kind: "session_start",
    stream_id: streamId,
    call_id: callId,
    started_at: startedAt,
    protected_number: null,
    schema_version: "1.0",
  };
  ws.send(JSON.stringify(sessionStart));
  console.log("[fake-ws] sent session_start");

  // 2. RiskUpdate loop
  timer = setInterval(() => {
    if (ws.readyState !== ws.OPEN) {
      clearInterval(timer);
      return;
    }

    const state = tickState(seq);
    const reasons = REASON_CODES[state.risk_level] || [];
    const contributing = state.score >= 40
      ? ["machine_fingerprint", "prosody"]
      : ["machine_fingerprint"];
    const degraded = seq < 5 ? ["speaker_identity"] : [];

    const update = {
      kind: "risk_update",
      stream_id: streamId,
      call_id: callId,
      sequence: seq,
      timestamp: isoNow(),
      score: state.score,
      verdict: state.verdict,
      risk_level: state.risk_level,
      confidence: state.confidence,
      reasons,
      contributing_checks: contributing,
      degraded_checks: degraded,
      evidence_refs: seq >= 10 ? [`evref-${seq}`] : [],
      schema_version: "1.0",
    };
    ws.send(JSON.stringify(update));
    console.log(
      `[fake-ws] tick ${seq}  score=${state.score}  level=${state.risk_level}  verdict=${state.verdict}`
    );

    seq += 1;
    if (seq >= CALL_DURATION_S) {
      clearInterval(timer);
      sendCallEnded(ws, streamId, callId, startedAt, state);
    }
  }, TICK_MS);

  ws.on("close", () => {
    console.log(`[fake-ws] client disconnected  stream_id=${streamId}`);
    if (timer) clearInterval(timer);
  });

  ws.on("error", (err) => {
    console.error(`[fake-ws] error: ${err.message}`);
    if (timer) clearInterval(timer);
  });
});

function sendCallEnded(ws, streamId, callId, startedAt, lastState) {
  if (ws.readyState !== ws.OPEN) return;

  const callEnded = {
    kind: "call_ended",
    stream_id: streamId,
    call_id: callId,
    ended_at: isoNow(),
    duration_seconds: CALL_DURATION_S,
    final_score: lastState.score,
    final_verdict: lastState.verdict,
    final_level: lastState.risk_level,
    reasons: REASON_CODES[lastState.risk_level] || [],
    alert_fingerprint: lastState.score >= 70 ? randomId("fp") : null,
    merkle_root: lastState.score >= 70 ? randomId("root") : null,
    sealed_record_id: lastState.score >= 70 ? randomId("sr") : null,
    root_published_at: lastState.score >= 70 ? isoNow() : null,
    schema_version: "1.0",
  };
  ws.send(JSON.stringify(callEnded));
  console.log(
    `[fake-ws] sent call_ended  final_score=${lastState.score}  final_level=${lastState.risk_level}`
  );
  ws.close();
}
