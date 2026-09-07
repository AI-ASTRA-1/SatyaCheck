/**
 * TypeScript interface for the SatyacheckOverlay native module.
 *
 * The native side (OverlayModule.kt + OverlayService.kt) draws a
 * TYPE_APPLICATION_OVERLAY window using Android WindowManager.
 * SYSTEM_ALERT_WINDOW permission must be granted before showOverlay() works.
 */

import { requireNativeModule } from "expo-modules-core";

const OverlayModule = requireNativeModule("SatyacheckOverlay");

/** Returns true if the SYSTEM_ALERT_WINDOW permission is already granted. */
export function isPermissionGranted(): boolean {
  return OverlayModule.isPermissionGranted();
}

/**
 * Opens the Android "Draw over other apps" settings screen so the user can
 * grant SYSTEM_ALERT_WINDOW. No-op if already granted.
 */
export function requestPermission(): void {
  OverlayModule.requestPermission();
}

/**
 * Starts (or updates) the overlay window with the current risk state.
 * Starts the foreground OverlayService if not already running.
 *
 * @param score      0-100 integer (for display only -- RiskLevel governs colour)
 * @param riskLevel  "low" | "medium" | "high" | "critical"
 * @param verdict    "genuine" | "synthetic" | "unknown"
 */
export function showOverlay(
  score: number,
  riskLevel: string,
  verdict: string
): void {
  OverlayModule.showOverlay(score, riskLevel, verdict);
}

/**
 * Hides the overlay and stops the foreground service.
 * Call on WebSocket disconnect so no stale score is shown.
 */
export function hideOverlay(): void {
  OverlayModule.hideOverlay();
}
