import React from "react";
import { StyleSheet, Text, View } from "react-native";
import {
  RISK_BACKGROUND,
  RISK_BORDER,
  RISK_COLOURS,
  RISK_LABEL,
  RISK_TEXT,
} from "../theme";
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
  const bg = RISK_BACKGROUND[level];
  const border = RISK_BORDER[level];
  const textCol = RISK_TEXT[level];
  const dotCol = RISK_COLOURS[level];

  return (
    <View
      style={[
        styles.chip,
        { backgroundColor: bg, borderColor: border },
        compact && styles.compact,
      ]}
    >
      <View style={[styles.dot, { backgroundColor: dotCol }]} />
      <Text style={[styles.label, { color: textCol }, compact && styles.labelSmall]}>
        {RISK_LABEL[level]}
      </Text>
      {score !== undefined && !compact && (
        <View style={styles.scoreContainer}>
          <Text style={[styles.score, { color: textCol }]}>{score}</Text>
          <Text style={[styles.scoreMax, { color: textCol }]}>/100</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    borderRadius: 10,
    borderWidth: 1.5,
    paddingHorizontal: 14,
    paddingVertical: 8,
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
    alignSelf: "flex-start",
  },
  compact: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    borderWidth: 1,
    gap: 6,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  label: {
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  labelSmall: {
    fontSize: 11,
    letterSpacing: 0.3,
  },
  scoreContainer: {
    flexDirection: "row",
    alignItems: "baseline",
    marginLeft: 4,
  },
  score: {
    fontSize: 16,
    fontWeight: "800",
  },
  scoreMax: {
    fontSize: 11,
    fontWeight: "600",
    opacity: 0.7,
    marginLeft: 1,
  },
});

