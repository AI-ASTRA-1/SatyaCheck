package com.aiastra.satyacheckoverlay

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.os.Build
import android.os.IBinder
import android.view.Gravity
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView

/**
 * OverlayService: draws a TYPE_APPLICATION_OVERLAY window over whatever app
 * is in the foreground (including the dialler / call UI).
 *
 * Lifecycle:
 *   startForegroundService() -> onCreate -> createOverlayView
 *   subsequent startService() calls -> onStartCommand -> updateOverlay
 *   stopService()             -> onDestroy -> removeOverlayView
 *
 * The overlay is display-only. It never intercepts touches on the call
 * controls: FLAG_NOT_FOCUSABLE + FLAG_NOT_TOUCH_MODAL ensure all touch
 * events pass through to the app underneath.
 *
 * Colour mapping (matches app/src/theme.ts):
 *   low      -> #22c55e  green
 *   medium   -> #f59e0b  amber
 *   high     -> #ef4444  red
 *   critical -> #b91c1c  dark red + warning prompt
 */
class OverlayService : Service() {

    private var windowManager: WindowManager? = null
    private var overlayRoot: LinearLayout? = null
    private var levelLabel: TextView? = null
    private var scoreText: TextView? = null
    private var verdictText: TextView? = null
    private var promptText: TextView? = null

    companion object {
        private const val NOTIF_CHANNEL_ID = "satyacheck_overlay_ch"
        private const val NOTIF_ID = 1001
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        startForegroundWithNotification()
        createOverlayView()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        intent?.let {
            val score = it.getIntExtra("score", -1)
            val riskLevel = it.getStringExtra("riskLevel") ?: "low"
            val verdict = it.getStringExtra("verdict") ?: "unknown"
            if (score >= 0) updateOverlay(score, riskLevel, verdict)
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        removeOverlayView()
        super.onDestroy()
    }

    // ---- Foreground notification ----------------------------------------

    private fun startForegroundWithNotification() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                NOTIF_CHANNEL_ID,
                "SATYACHECK active",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Call analysis is running"
                setShowBadge(false)
            }
            (getSystemService(NOTIFICATION_SERVICE) as NotificationManager)
                .createNotificationChannel(channel)
        }

        val notif = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, NOTIF_CHANNEL_ID)
                .setContentTitle("SATYACHECK")
                .setContentText("Call analysis active")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
                .setContentTitle("SATYACHECK")
                .setContentText("Call analysis active")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .build()
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    // ---- Overlay view creation -----------------------------------------

    private fun createOverlayView() {
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dpToPx(12), dpToPx(8), dpToPx(12), dpToPx(8))
            setBackgroundColor(Color.parseColor("#22c55e"))   // default: low/green
            background = roundedBackground(Color.parseColor("#22c55e"))
        }

        levelLabel = TextView(this).apply {
            textSize = 10f
            setTextColor(Color.WHITE)
            letterSpacing = 0.12f
            typeface = Typeface.DEFAULT_BOLD
            text = "LOW"
        }

        scoreText = TextView(this).apply {
            textSize = 20f
            setTextColor(Color.WHITE)
            typeface = Typeface.DEFAULT_BOLD
            text = "--"
        }

        verdictText = TextView(this).apply {
            textSize = 11f
            setTextColor(Color.argb(200, 255, 255, 255))
            text = ""
        }

        promptText = TextView(this).apply {
            textSize = 11f
            setTextColor(Color.WHITE)
            visibility = android.view.View.GONE
            setPadding(0, dpToPx(4), 0, 0)
            text = "Warning: unusual voice patterns detected. Proceed with caution."
        }

        root.addView(levelLabel)
        root.addView(scoreText)
        root.addView(verdictText)
        root.addView(promptText)
        overlayRoot = root

        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            type,
            // FLAG_NOT_FOCUSABLE + FLAG_NOT_TOUCH_MODAL: touches pass through
            // to whatever app is underneath. The overlay never intercepts call
            // controls.
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.END
            x = dpToPx(12)
            y = dpToPx(48)    // below the status bar
        }

        windowManager?.addView(overlayRoot, params)
    }

    // ---- Overlay update ------------------------------------------------

    private fun updateOverlay(score: Int, riskLevel: String, verdict: String) {
        val color = when (riskLevel) {
            "low"      -> Color.parseColor("#22c55e")
            "medium"   -> Color.parseColor("#f59e0b")
            "high"     -> Color.parseColor("#ef4444")
            "critical" -> Color.parseColor("#b91c1c")
            else       -> Color.parseColor("#22c55e")
        }

        overlayRoot?.background = roundedBackground(color)
        levelLabel?.text = riskLevel.uppercase()
        scoreText?.text = score.toString()
        verdictText?.text = verdict

        if (riskLevel == "critical") {
            promptText?.visibility = android.view.View.VISIBLE
        } else {
            promptText?.visibility = android.view.View.GONE
        }
    }

    // ---- Cleanup -------------------------------------------------------

    private fun removeOverlayView() {
        overlayRoot?.let { windowManager?.removeView(it) }
        overlayRoot = null
        @Suppress("DEPRECATION")
        stopForeground(true)
    }

    // ---- Helpers -------------------------------------------------------

    private fun dpToPx(dp: Int): Int =
        (dp * resources.displayMetrics.density).toInt()

    private fun roundedBackground(color: Int): android.graphics.drawable.GradientDrawable =
        android.graphics.drawable.GradientDrawable().apply {
            setColor(color)
            cornerRadius = dpToPx(8).toFloat()
        }
}
