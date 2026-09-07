import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { RISK_COLOURS, RISK_LABEL } from "../theme";
import { RiskLevel } from "../ws/types";

interface Props {
  level: RiskLevel;
  score?: number;
  compact?: boolean;
}

/**
 * RiskChip: coloured pill showing risk level and optionally the numeric score.
 *
 * Colour source: app/src/theme.ts (single source of truth).
 * The chip renders risk_level as sent; it never computes a band from score.
 */
export function RiskChip({ level, score, compact = false }: Props) {
  const bg = RISK_COLOURS[level];

  return (
    <View style={[styles.chip, { backgroundColor: bg }, compact && styles.compact]}>
      <Text style={[styles.label, compact && styles.labelSmall]}>
        {RISK_LABEL[level]}
      </Text>
      {score !== undefined && !compact && (
        <Text style={styles.score}>{score}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 8,
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  compact: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 6,
  },
  label: {
    color: "#ffffff",
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 1,
  },
  labelSmall: {
    fontSize: 11,
  },
  score: {
    color: "rgba(255,255,255,0.85)",
    fontSize: 20,
    fontWeight: "700",
  },
});
