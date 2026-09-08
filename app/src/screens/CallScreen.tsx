/**
 * CallScreen.tsx
 *
 * In-app WebRTC call screen -- fallback path only.
 * Only active when the user navigates to "call" in App.tsx.
 *
 * Exotel path (OverlayScreen) is completely separate and unaffected.
 *
 * States:
 *   idle      -- enter call ID to dial, or wait for incoming call
 *   dialling  -- caller sent offer, waiting for receiver
 *   ringing   -- receiver sees incoming call prompt (or caller sees "ringing")
 *   active    -- call connected, RiskChip + risk scores from useRiskSocket
 *   ended     -- call ended, summary + back button
 *
 * Risk scores are driven by useRiskSocket (port 8765) -- UNCHANGED.
 * The WebRTC call merely triggers the backend to send those scores.
 * The overlay is driven by useOverlay -- UNCHANGED.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { CriticalPrompt } from "../components/CriticalPrompt";
import { RiskChip } from "../components/RiskChip";
import { ScanningIndicator } from "../components/ScanningIndicator";
import { useOverlay } from "../overlay/useOverlay";
import { SocketStatus } from "../ws/useRiskSocket";
import { useWebRTCCall } from "../webrtc/useWebRTCCall";

interface Props {
  /** Passed from App.tsx -- same hook instance driving the overlay. */
  riskState: SocketStatus;
  onBack: () => void;
}

export function CallScreen({ riskState, onBack }: Props) {
  const {
    callState,
    role,
    sigState,
    dial,
    accept,
    hangup,
    connectSignalling,
    isSpeakerOn,
    toggleSpeaker,
  } = useWebRTCCall();

  // Drive the native overlay in sync with the risk socket -- same as OverlayScreen.
  useOverlay(riskState);

  const [callIdInput, setCallIdInput] = useState("");
  // Incoming call data is surfaced via callState when status === "ringing".
  const incomingCallId =
    callState.status === "ringing" && role === "receiver"
      ? callState.callId
      : null;

  // Generate a unique call ID for the caller to share.
  const generateCallId = useCallback(() => {
    const id = "call_" + Date.now().toString(36);
    setCallIdInput(id);
  }, []);

  // Connect to signalling server as soon as the screen mounts.
  useEffect(() => {
    connectSignalling();
  }, [connectSignalling]);

  const handleDial = useCallback(() => {
    const id = callIdInput.trim();
    if (!id) return;
    dial(id);
  }, [callIdInput, dial]);

  const handleAccept = useCallback(() => {
    if (callState.status === "ringing" && incomingCallId) {
      accept(incomingCallId);
    }
  }, [accept, callState.status, incomingCallId]);

  const handleHangup = useCallback(() => {
    if (
      callState.status === "active" ||
      callState.status === "dialling" ||
      callState.status === "ringing"
    ) {
      hangup(callState.callId);
    }
  }, [callState, hangup]);

  // ---- Render helpers ----------------------------------------------------

  function renderIdle() {
    return (
      <KeyboardAvoidingView
        behavior={Platform.OS === "android" ? "height" : "padding"}
        style={styles.section}
      >
        <Text style={styles.sectionTitle}>Start a call</Text>
        <Text style={styles.hint}>
          Enter a call ID or generate one. Share it with the other person so they
          can join.
        </Text>

        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={callIdInput}
            onChangeText={setCallIdInput}
            placeholder="call_..."
            placeholderTextColor="#94a3b8"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <TouchableOpacity style={styles.genBtn} onPress={generateCallId}>
            <Text style={styles.genBtnText}>Generate</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity
          style={[styles.primaryBtn, !callIdInput.trim() && styles.btnDisabled]}
          onPress={handleDial}
          disabled={!callIdInput.trim()}
        >
          <Text style={styles.primaryBtnText}>Call</Text>
        </TouchableOpacity>

        {sigState === "connected" && (
          <Text style={styles.connectedHint}>
            Connected. Waiting for incoming calls...
          </Text>
        )}
        {sigState === "connecting" && (
          <Text style={styles.hint}>Connecting to server...</Text>
        )}
        {(sigState === "disconnected" || sigState === "error") && (
          <Text style={styles.errorHint}>
            Signalling server unreachable. Check config.ts SIGNALLING_URL.
          </Text>
        )}
      </KeyboardAvoidingView>
    );
  }

  function renderDialling() {
    if (callState.status !== "dialling") return null;
    return (
      <View style={styles.section}>
        <ScanningIndicator />
        <Text style={styles.sectionTitle}>Calling...</Text>
        <Text style={styles.callIdText}>{callState.callId}</Text>
        <TouchableOpacity style={styles.endBtn} onPress={handleHangup}>
          <Text style={styles.endBtnText}>Cancel</Text>
        </TouchableOpacity>
      </View>
    );
  }

  function renderIncoming() {
    if (!incomingCallId) return null;
    return (
      <View style={styles.section}>
        <Text style={styles.incomingTitle}>Incoming call</Text>
        <Text style={styles.callIdText}>{incomingCallId}</Text>
        <View style={styles.incomingBtns}>
          <TouchableOpacity style={styles.endBtn} onPress={handleHangup}>
            <Text style={styles.endBtnText}>Decline</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.acceptBtn} onPress={handleAccept}>
            <Text style={styles.acceptBtnText}>Accept</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  function renderActive() {
    if (callState.status !== "active") return null;
    return (
      <ScrollView contentContainerStyle={styles.section}>
        <Text style={styles.callIdText}>Call: {callState.callId}</Text>

        {riskState.status === "session" && <ScanningIndicator />}

        {riskState.status === "live" && (
          <>
            <RiskChip level={riskState.latest.risk_level} score={riskState.latest.score} />
            <View style={styles.detailRows}>
              <DetailRow label="Verdict" value={riskState.latest.verdict} />
              <DetailRow
                label="Confidence"
                value={`${Math.round(riskState.latest.confidence * 100)}%`}
              />
              <DetailRow label="Tick" value={String(riskState.latest.sequence)} />
            </View>
            {(riskState.latest.risk_level === "high" ||
              riskState.latest.risk_level === "critical") && (
              <CriticalPrompt />
            )}
          </>
        )}

        {riskState.status === "disconnected" && (
          <Text style={styles.hint}>Waiting for risk analysis...</Text>
        )}

        <View style={styles.actionRow}>
          <TouchableOpacity
            style={[styles.speakerBtn, isSpeakerOn && styles.speakerBtnActive]}
            onPress={toggleSpeaker}
          >
            <Text
              style={[
                styles.speakerBtnText,
                isSpeakerOn && styles.speakerBtnTextActive,
              ]}
            >
              {isSpeakerOn ? "Speaker: ON" : "Audio: Earpiece"}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.endBtn} onPress={handleHangup}>
            <Text style={styles.endBtnText}>End Call</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    );
  }

  function renderEnded() {
    if (callState.status !== "ended") return null;
    const summary = riskState.status === "ended" ? riskState.summary : null;
    return (
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Call ended</Text>
        <Text style={styles.hint}>{callState.reason}</Text>
        {summary && (
          <View style={styles.summaryCard}>
            <RiskChip level={summary.final_level} compact />
            <DetailRow label="Score" value={String(summary.final_score)} />
            <DetailRow label="Verdict" value={summary.final_verdict} />
            <DetailRow
              label="Duration"
              value={`${Math.round(summary.duration_seconds)}s`}
            />
          </View>
        )}
        <TouchableOpacity style={styles.primaryBtn} onPress={onBack}>
          <Text style={styles.primaryBtnText}>Back</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ---- Main render -------------------------------------------------------

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.title}>SATYACHECK</Text>
        {callState.status === "idle" && (
          <TouchableOpacity onPress={onBack}>
            <Text style={styles.backText}>Back</Text>
          </TouchableOpacity>
        )}
      </View>

      {callState.status === "idle" && renderIdle()}
      {callState.status === "dialling" && renderDialling()}
      {callState.status === "ringing" && role === "receiver" && renderIncoming()}
      {callState.status === "ringing" && role === "caller" && renderDialling()}
      {callState.status === "active" && renderActive()}
      {callState.status === "ended" && renderEnded()}
    </SafeAreaView>
  );
}

// ---- Small helper -------------------------------------------------------

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

// ---- Styles -------------------------------------------------------------

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#f8fafc" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingVertical: 14,
    backgroundColor: "#ffffff",
    borderBottomWidth: 1,
    borderBottomColor: "#e2e8f0",
  },
  title: {
    color: "#0f172a",
    fontSize: 17,
    fontWeight: "800",
    letterSpacing: 1,
  },
  backText: { color: "#475569", fontSize: 14, fontWeight: "600" },

  section: {
    flex: 1,
    padding: 20,
    gap: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  sectionTitle: {
    color: "#0f172a",
    fontSize: 20,
    fontWeight: "700",
    textAlign: "center",
  },
  incomingTitle: {
    color: "#b91c1c",
    fontSize: 22,
    fontWeight: "800",
    textAlign: "center",
  },
  callIdText: { color: "#475569", fontSize: 13, fontFamily: "monospace" },
  hint: { color: "#64748b", fontSize: 13, textAlign: "center" },
  connectedHint: { color: "#15803d", fontSize: 12, textAlign: "center", fontWeight: "600" },
  errorHint: { color: "#b91c1c", fontSize: 12, textAlign: "center" },

  inputRow: { flexDirection: "row", gap: 8, width: "100%" },
  input: {
    flex: 1,
    backgroundColor: "#ffffff",
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 11,
    color: "#0f172a",
    fontSize: 14,
    fontFamily: "monospace",
    borderWidth: 1.5,
    borderColor: "#cbd5e1",
  },
  genBtn: {
    backgroundColor: "#f1f5f9",
    borderRadius: 10,
    paddingHorizontal: 14,
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#e2e8f0",
  },
  genBtnText: { color: "#334155", fontSize: 13, fontWeight: "600" },

  primaryBtn: {
    backgroundColor: "#2563eb",
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 40,
    alignItems: "center",
  },
  primaryBtnText: { color: "#ffffff", fontSize: 15, fontWeight: "700" },
  btnDisabled: { opacity: 0.4 },

  actionRow: {
    flexDirection: "row",
    gap: 12,
    marginTop: 8,
  },
  speakerBtn: {
    flex: 1,
    backgroundColor: "#f1f5f9",
    borderWidth: 1,
    borderColor: "#cbd5e1",
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  speakerBtnActive: {
    backgroundColor: "#e0f2fe",
    borderColor: "#0284c7",
  },
  speakerBtnText: {
    color: "#334155",
    fontSize: 14,
    fontWeight: "700",
  },
  speakerBtnTextActive: {
    color: "#0369a1",
  },
  endBtn: {
    flex: 1,
    backgroundColor: "#dc2626",
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  endBtnText: { color: "#ffffff", fontSize: 15, fontWeight: "700" },

  acceptBtn: {
    backgroundColor: "#16a34a",
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 32,
    alignItems: "center",
  },
  acceptBtnText: { color: "#ffffff", fontSize: 15, fontWeight: "700" },

  incomingBtns: { flexDirection: "row", gap: 16 },

  detailRows: {
    width: "100%",
    gap: 10,
    backgroundColor: "#ffffff",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#e2e8f0",
    padding: 16,
    shadowColor: "#0f172a",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  },
  row: { flexDirection: "row", justifyContent: "space-between" },
  rowLabel: { color: "#64748b", fontSize: 13, fontWeight: "500" },
  rowValue: { color: "#0f172a", fontSize: 13, fontWeight: "700" },

  summaryCard: {
    backgroundColor: "#ffffff",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#e2e8f0",
    padding: 18,
    width: "100%",
    gap: 10,
    shadowColor: "#0f172a",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  },
});

