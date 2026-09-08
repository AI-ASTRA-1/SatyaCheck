import React from "react";
import {
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { CriticalPrompt } from "../components/CriticalPrompt";
import { RiskChip } from "../components/RiskChip";
import { ScanningIndicator } from "../components/ScanningIndicator";
import { RISK_COLOURS } from "../theme";
import { useOverlay } from "../overlay/useOverlay";
import { SocketStatus } from "../ws/useRiskSocket";

interface Props {
  state: SocketStatus;
  onReconnect: () => void;
  onHistory: () => void;
  /** Navigate to the WebRTC in-app call screen (fallback path). */
  onCall?: () => void;
}

/**
 * OverlayScreen: the main in-app view mirroring the overlay state.
 *
 * This screen is what the user sees inside the SATYACHECK app itself.
 * The native OverlayService draws on top of other apps separately.
 *
 * States:
 *   disconnected / connecting -> neutral waiting UI
 *   session                   -> ScanningIndicator
 *   live                      -> RiskChip + detail rows
 *   ended                     -> summary card
 */
export function OverlayScreen({ state, onReconnect, onHistory, onCall }: Props) {
  // Drive the native overlay window in sync with the socket state.
  useOverlay(state);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.title}>SATYACHECK</Text>
        <View style={styles.headerBtns}>
          {onCall && (
            <TouchableOpacity onPress={onCall} style={styles.callBtn}>
              <Text style={styles.callBtnText}>Call</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={onHistory} style={styles.histBtn}>
            <Text style={styles.histBtnText}>History</Text>
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView contentContainerStyle={styles.body}>
        {(state.status === "disconnected" || state.status === "connecting") && (
          <View style={styles.waitCard}>
            <Text style={styles.waitTitle}>
              {state.status === "connecting" ? "Connecting..." : "Waiting for call"}
            </Text>
            <Text style={styles.waitSub}>
              Start a call to begin analysis.
            </Text>
            {state.status === "disconnected" && (
              <TouchableOpacity style={styles.reconnectBtn} onPress={onReconnect}>
                <Text style={styles.reconnectText}>Reconnect</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {state.status === "session" && (
          <View style={styles.card}>
            <Text style={styles.callId}>Call {state.session.call_id}</Text>
            <ScanningIndicator />
            <Text style={styles.subtext}>
              Gathering audio -- warning will appear if patterns change.
            </Text>
          </View>
        )}

        {state.status === "live" && (
          <View style={styles.card}>
            <Text style={styles.callId}>Call {state.session.call_id}</Text>
            <View style={styles.chipRow}>
              <RiskChip
                level={state.latest.risk_level}
                score={state.latest.score}
              />
            </View>

            <View style={styles.detailGrid}>
              <DetailRow label="Verdict" value={state.latest.verdict} />
              <DetailRow
                label="Confidence"
                value={`${Math.round(state.latest.confidence * 100)}%`}
              />
              <DetailRow
                label="Tick"
                value={String(state.latest.sequence)}
              />
            </View>

            {state.latest.degraded_checks.length > 0 && (
              <Text style={styles.degraded}>
                Degraded: {state.latest.degraded_checks.join(", ")}
              </Text>
            )}

            {state.latest.risk_level === "critical" && <CriticalPrompt />}
          </View>
        )}

        {state.status === "ended" && (
          <View style={styles.card}>
            <Text style={styles.endedTitle}>Call ended</Text>
            <View style={styles.chipRow}>
              <RiskChip level={state.summary.final_level} />
            </View>
            <DetailRow label="Final score" value={String(state.summary.final_score)} />
            <DetailRow label="Verdict" value={state.summary.final_verdict} />
            <DetailRow
              label="Duration"
              value={`${Math.round(state.summary.duration_seconds)}s`}
            />
            {state.summary.sealed_record_id && (
              <Text style={styles.evidenceRef}>
                Record: {state.summary.sealed_record_id}
              </Text>
            )}
            <TouchableOpacity style={styles.reconnectBtn} onPress={onReconnect}>
              <Text style={styles.reconnectText}>Start monitoring</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.detailRow}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0f0f0f" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: "#1f1f1f",
  },
  title: { color: "#ffffff", fontSize: 18, fontWeight: "700", letterSpacing: 1 },
  headerBtns: { flexDirection: "row", alignItems: "center", gap: 12 },
  callBtn: { paddingVertical: 4, paddingHorizontal: 10, backgroundColor: "#1d4ed8", borderRadius: 6 },
  callBtnText: { color: "#ffffff", fontSize: 13, fontWeight: "600" },
  histBtn: { padding: 6 },
  histBtnText: { color: "#6b7280", fontSize: 14 },
  body: { padding: 20, flexGrow: 1 },
  card: {
    backgroundColor: "#1a1a1a",
    borderRadius: 12,
    padding: 20,
    gap: 12,
  },
  waitCard: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    paddingVertical: 60,
  },
  waitTitle: { color: "#ffffff", fontSize: 18, fontWeight: "600" },
  waitSub: { color: "#6b7280", fontSize: 14, textAlign: "center" },
  callId: { color: "#6b7280", fontSize: 12, fontFamily: "monospace" },
  subtext: { color: "#6b7280", fontSize: 13 },
  chipRow: { flexDirection: "row" },
  detailGrid: { gap: 8 },
  detailRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    borderBottomWidth: 1,
    borderBottomColor: "#2a2a2a",
    paddingBottom: 6,
  },
  detailLabel: { color: "#6b7280", fontSize: 13 },
  detailValue: { color: "#e5e7eb", fontSize: 13, fontWeight: "500" },
  degraded: { color: "#f59e0b", fontSize: 12 },
  endedTitle: { color: "#ffffff", fontSize: 16, fontWeight: "600" },
  evidenceRef: { color: "#374151", fontSize: 11, fontFamily: "monospace" },
  reconnectBtn: {
    backgroundColor: "#1f2937",
    borderRadius: 8,
    paddingVertical: 12,
    alignItems: "center",
    marginTop: 8,
  },
  reconnectText: { color: "#e5e7eb", fontSize: 14, fontWeight: "600" },
});
