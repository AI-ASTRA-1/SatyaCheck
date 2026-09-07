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
    backgroundColor: "rgba(185, 28, 28, 0.15)",
    borderWidth: 1,
    borderColor: "#b91c1c",
    borderRadius: 8,
    padding: 12,
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
    color: "#fca5a5",
    fontSize: 14,
    lineHeight: 20,
    flex: 1,
  },
});
