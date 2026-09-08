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
  low: "#16a34a",       // emerald-600
  medium: "#d97706",    // amber-600
  high: "#dc2626",      // red-600
  critical: "#b91c1c",  // deep red-700
};

export const RISK_BACKGROUND: Record<RiskLevel, string> = {
  low: "#f0fdf4",       // emerald-50
  medium: "#fffbeb",    // amber-50
  high: "#fef2f2",      // red-50
  critical: "#fff1f2",  // rose-50
};

export const RISK_BORDER: Record<RiskLevel, string> = {
  low: "#bbf7d0",       // emerald-200
  medium: "#fde68a",    // amber-200
  high: "#fecaca",      // red-200
  critical: "#fca5a5",  // rose-300
};

export const RISK_TEXT: Record<RiskLevel, string> = {
  low: "#15803d",       // emerald-700
  medium: "#b45309",    // amber-700
  high: "#b91c1c",      // red-700
  critical: "#991b1b",  // rose-800
};

export const RISK_LABEL: Record<RiskLevel, string> = {
  low: "LOW RISK",
  medium: "MEDIUM RISK",
  high: "HIGH RISK",
  critical: "CRITICAL",
};

/** Pristine Light Theme Tokens */
export const LIGHT_THEME = {
  background: "#f8fafc",      // slate-50 canvas
  surface: "#ffffff",         // pure white cards
  surfaceMuted: "#f1f5f9",    // slate-100
  border: "#e2e8f0",          // slate-200
  borderSubtle: "#f1f5f9",    // slate-100
  textPrimary: "#0f172a",     // slate-900
  textSecondary: "#475569",   // slate-600
  textMuted: "#94a3b8",       // slate-400
  primary: "#2563eb",         // blue-600
  primaryLight: "#eff6ff",    // blue-50
  primaryHover: "#1d4ed8",    // blue-700
  danger: "#dc2626",          // red-600
  dangerLight: "#fef2f2",     // red-50
  success: "#16a34a",         // green-600
  successLight: "#f0fdf4",    // green-50
  warning: "#d97706",         // amber-600
};

/** Text shown only on critical. The human decides; this is a warning. */
export const CRITICAL_PROMPT =
  "Warning: unusual voice patterns detected. Proceed with caution. You decide.";

