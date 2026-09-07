/**
 * Colour and style tokens keyed on RiskLevel.
 *
 * Source: app/README.md colour mapping (authoritative for R4).
 *   low      - green subtle chip
 *   medium   - amber chip
 *   high     - red overlay strip
 *   critical - red overlay + action prompt
 *
 * The app renders risk_level as sent; it never derives a band from score.
 */

import { RiskLevel } from "./ws/types";

export const RISK_COLOURS: Record<RiskLevel, string> = {
  low: "#22c55e",       // green-500
  medium: "#f59e0b",    // amber-500
  high: "#ef4444",      // red-500
  critical: "#b91c1c",  // red-700
};

export const RISK_BACKGROUND: Record<RiskLevel, string> = {
  low: "rgba(34, 197, 94, 0.15)",
  medium: "rgba(245, 158, 11, 0.18)",
  high: "rgba(239, 68, 68, 0.22)",
  critical: "rgba(185, 28, 28, 0.30)",
};

export const RISK_LABEL: Record<RiskLevel, string> = {
  low: "LOW",
  medium: "MEDIUM",
  high: "HIGH",
  critical: "CRITICAL",
};

/** Text shown only on critical. The human decides; this is a warning. */
export const CRITICAL_PROMPT =
  "Warning: unusual voice patterns detected. Proceed with caution.";
