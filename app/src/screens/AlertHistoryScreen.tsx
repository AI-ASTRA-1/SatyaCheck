import React from "react";
import {
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { RiskChip } from "../components/RiskChip";
import { AlertHistoryEntry } from "../ws/useRiskSocket";

interface Props {
  history: AlertHistoryEntry[];
  onBack: () => void;
}

/**
 * AlertHistoryScreen: Round 1 alert history -- a list of CallEnded summaries.
 *
 * Shows final_level, final_score, final_verdict, duration for each past call.
 * Sealed record IDs shown when present (stage 07 evidence, opaque ids only).
 * No audio, no transcript, no PII -- only the non-sensitive fields from CallEnded.
 */
export function AlertHistoryScreen({ history, onBack }: Props) {
  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity onPress={onBack} style={styles.backBtn}>
          <Text style={styles.backText}>Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Alert History</Text>
        <View style={styles.spacer} />
      </View>

      {history.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyText}>No calls analysed yet.</Text>
        </View>
      ) : (
        <FlatList
          data={history}
          keyExtractor={(item) => item.session.call_id}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => <HistoryCard entry={item} />}
        />
      )}
    </SafeAreaView>
  );
}

function HistoryCard({ entry }: { entry: AlertHistoryEntry }) {
  const { summary } = entry;
  const date = new Date(summary.ended_at).toLocaleTimeString();

  return (
    <View style={styles.card}>
      <View style={styles.cardTop}>
        <RiskChip level={summary.final_level} compact />
        <Text style={styles.time}>{date}</Text>
      </View>

      <Row label="Score" value={String(summary.final_score)} />
      <Row label="Verdict" value={summary.final_verdict} />
      <Row
        label="Duration"
        value={`${Math.round(summary.duration_seconds)}s`}
      />

      {summary.sealed_record_id && (
        <Text style={styles.sealedId} numberOfLines={1}>
          Sealed: {summary.sealed_record_id}
        </Text>
      )}
    </View>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

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
  backBtn: { width: 60 },
  backText: { color: "#475569", fontSize: 14, fontWeight: "600" },
  title: {
    color: "#0f172a",
    fontSize: 17,
    fontWeight: "800",
    letterSpacing: 0.5,
  },
  spacer: { width: 60 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyText: { color: "#64748b", fontSize: 15, fontWeight: "500" },
  list: { padding: 18, gap: 12 },
  card: {
    backgroundColor: "#ffffff",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#e2e8f0",
    padding: 16,
    gap: 10,
    shadowColor: "#0f172a",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  },
  cardTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  time: { color: "#64748b", fontSize: 12, fontWeight: "500" },
  row: { flexDirection: "row", justifyContent: "space-between" },
  label: { color: "#64748b", fontSize: 13, fontWeight: "500" },
  value: { color: "#0f172a", fontSize: 13, fontWeight: "700" },
  sealedId: {
    color: "#94a3b8",
    fontSize: 11,
    fontFamily: "monospace",
    marginTop: 4,
  },
});

