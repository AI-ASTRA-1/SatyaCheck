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
  safe: { flex: 1, backgroundColor: "#0f0f0f" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: "#1f1f1f",
  },
  backBtn: { width: 60 },
  backText: { color: "#6b7280", fontSize: 14 },
  title: { color: "#ffffff", fontSize: 16, fontWeight: "600" },
  spacer: { width: 60 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyText: { color: "#374151", fontSize: 15 },
  list: { padding: 16, gap: 12 },
  card: {
    backgroundColor: "#1a1a1a",
    borderRadius: 10,
    padding: 14,
    gap: 8,
  },
  cardTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  time: { color: "#6b7280", fontSize: 12 },
  row: { flexDirection: "row", justifyContent: "space-between" },
  label: { color: "#6b7280", fontSize: 13 },
  value: { color: "#e5e7eb", fontSize: 13, fontWeight: "500" },
  sealedId: {
    color: "#374151",
    fontSize: 11,
    fontFamily: "monospace",
    marginTop: 4,
  },
});
