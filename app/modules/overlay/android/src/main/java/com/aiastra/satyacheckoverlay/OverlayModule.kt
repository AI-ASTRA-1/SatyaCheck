package com.aiastra.satyacheckoverlay

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/**
 * SatyacheckOverlay native module.
 *
 * Exposes four synchronous functions to JavaScript:
 *   isPermissionGranted() -> Boolean
 *   requestPermission()   -> Unit  (opens system settings screen)
 *   showOverlay(score, riskLevel, verdict) -> Unit
 *   hideOverlay()         -> Unit
 *
 * showOverlay starts (or updates) OverlayService, which draws the
 * TYPE_APPLICATION_OVERLAY window using WindowManager.
 * hideOverlay stops the service and removes the window.
 *
 * The overlay is display-only. It never blocks, mutes, or ends a call.
 */
class OverlayModule : Module() {

    override fun definition() = ModuleDefinition {

        Name("SatyacheckOverlay")

        // Returns true if Settings.canDrawOverlays() is satisfied.
        // On API < 23 always returns true (permission granted at install time).
        Function("isPermissionGranted") {
            val ctx = appContext.reactContext ?: return@Function false
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                Settings.canDrawOverlays(ctx)
            } else {
                true
            }
        }

        // Opens the "Draw over other apps" system settings screen.
        // No-op if already granted.
        Function("requestPermission") {
            val activity = appContext.currentActivity
            if (activity != null &&
                Build.VERSION.SDK_INT >= Build.VERSION_CODES.M &&
                !Settings.canDrawOverlays(activity)
            ) {
                val intent = Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:${activity.packageName}")
                )
                activity.startActivity(intent)
            }
        }

        // Starts or updates the overlay with the current risk state.
        // score: 0-100 (display only; riskLevel governs colour)
        // riskLevel: "low" | "medium" | "high" | "critical"
        // verdict: "genuine" | "synthetic" | "unknown"
        Function("showOverlay") { score: Int, riskLevel: String, verdict: String ->
            val ctx = appContext.reactContext
            if (ctx != null) {
                val intent = Intent(ctx, OverlayService::class.java).apply {
                    putExtra("score", score)
                    putExtra("riskLevel", riskLevel)
                    putExtra("verdict", verdict)
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    ctx.startForegroundService(intent)
                } else {
                    ctx.startService(intent)
                }
            }
        }

        // Hides the overlay and stops the foreground service.
        // Called on WebSocket disconnect so no stale score is shown.
        Function("hideOverlay") {
            val ctx = appContext.reactContext
            if (ctx != null) {
                ctx.stopService(Intent(ctx, OverlayService::class.java))
            }
        }
    }
}
