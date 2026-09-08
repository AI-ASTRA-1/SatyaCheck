import React from "react";
import { StyleSheet, Text, View } from "react-native";

/**
 * CriticalPrompt: shown only when risk_level is "critical".
 *
 * Wording follows AGENTS.md claims discipline:
 *   - "warning" not "detection"
 *   - "proceed with caution" not "hang up" (we never instruct the user to end a call)
 *   - the human decides
 */
export function CriticalPrompt() {
  return (
    <View style={styles.container}>
      <Text style={styles.icon}>!</Text>
      <Text style={styles.text}>
        Warning: unusual voice patterns detected.{"\n"}
        Proceed with caution. You decide.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "flex-start",
    backgroundColor: "#fef2f2",
    borderWidth: 1,
    borderColor: "#fca5a5",
    borderRadius: 10,
    padding: 14,
    gap: 10,
    marginTop: 12,
  },
  icon: {
    color: "#b91c1c",
    fontWeight: "800",
    fontSize: 18,
    lineHeight: 20,
  },
  text: {
    color: "#7f1d1d",
    fontSize: 13,
    lineHeight: 19,
    fontWeight: "500",
    flex: 1,
  },
});

