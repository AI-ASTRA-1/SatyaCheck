/**
 * Renders the simulated mobile phone UI and live in-call overlay
 * onto an offscreen canvas for use as a Three.js CanvasTexture.
 */

export interface PhoneScreenState {
  progress: number
  callDuration: number
  callerName: string
  callerNumber: string
}

export function drawPhoneScreen(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  state: PhoneScreenState
) {
  const { progress } = state

  // Clear background (phone dark theme)
  ctx.fillStyle = '#0a0a0d'
  ctx.fillRect(0, 0, width, height)

  // Subtle radial gradient background
  const bgGrad = ctx.createRadialGradient(
    width / 2,
    height * 0.35,
    20,
    width / 2,
    height * 0.4,
    width * 0.8
  )
  bgGrad.addColorStop(0, '#16161d')
  bgGrad.addColorStop(1, '#0a0a0d')
  ctx.fillStyle = bgGrad
  ctx.fillRect(0, 0, width, height)

  // 1. Status Bar
  ctx.fillStyle = '#f5f0e8'
  ctx.font = '500 24px system-ui, -apple-system, sans-serif'
  ctx.textAlign = 'left'
  ctx.fillText('10:42', 36, 50)

  // Battery & Signal icons (simplified vector shapes)
  ctx.textAlign = 'right'
  ctx.fillText('5G  100%', width - 36, 50)

  // 2. Telephony App Header / Caller Identity
  ctx.textAlign = 'center'
  ctx.fillStyle = '#7a756a'
  ctx.font = '600 20px system-ui, -apple-system, sans-serif'
  ctx.fillText('INCOMING CARRIER CALL (EXOTEL)', width / 2, 120)

  // Caller Avatar Circle
  ctx.beginPath()
  ctx.arc(width / 2, 210, 60, 0, Math.PI * 2)
  ctx.fillStyle = '#1f1f26'
  ctx.fill()
  ctx.lineWidth = 2
  ctx.strokeStyle = progress > 0.7 ? 'rgba(248, 113, 113, 0.6)' : 'rgba(201, 169, 110, 0.4)'
  ctx.stroke()

  ctx.fillStyle = '#f5f0e8'
  ctx.font = '600 36px system-ui, -apple-system, sans-serif'
  ctx.fillText(state.callerName, width / 2, 320)

  ctx.fillStyle = '#b8b2a6'
  ctx.font = '400 24px system-ui, -apple-system, sans-serif'
  ctx.fillText(state.callerNumber, width / 2, 360)

  // Call duration counter
  const seconds = Math.floor(state.callDuration) % 60
  const minutes = Math.floor(state.callDuration / 60)
  const timeStr = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  ctx.fillStyle = '#7a756a'
  ctx.font = '500 22px system-ui, -apple-system, sans-serif'
  ctx.fillText(`Live Call · ${timeStr}`, width / 2, 400)

  // 3. Audio Stream Visualizer Bar
  const barCount = 28
  const barWidth = 6
  const barGap = 6
  const totalW = barCount * (barWidth + barGap)
  const startX = (width - totalW) / 2
  const centerY = 460

  for (let i = 0; i < barCount; i++) {
    const wave = Math.sin(i * 0.4 + state.callDuration * 5) * 0.5 + 0.5
    const barHeight = 10 + wave * 36
    const x = startX + i * (barWidth + barGap)
    ctx.fillStyle =
      progress > 0.75
        ? 'rgba(248, 113, 113, 0.8)'
        : progress > 0.3
        ? 'rgba(201, 169, 110, 0.7)'
        : 'rgba(74, 222, 128, 0.7)'
    ctx.fillRect(x, centerY - barHeight / 2, barWidth, barHeight)
  }

  // 4. Live SatyaCheck In-Call Overlay HUD
  if (progress > 0.15) {
    const overlayAlpha = Math.min(1, (progress - 0.15) * 3)
    const overlayY = 530
    const overlayW = width - 64
    const overlayH = 260
    const overlayX = 32

    ctx.save()
    ctx.globalAlpha = overlayAlpha

    // Overlay Card Background
    const isCritical = progress > 0.7
    ctx.fillStyle = isCritical ? 'rgba(32, 12, 14, 0.95)' : 'rgba(26, 26, 31, 0.92)'
    roundRect(ctx, overlayX, overlayY, overlayW, overlayH, 20)
    ctx.fill()

    ctx.lineWidth = 2
    ctx.strokeStyle = isCritical ? '#f87171' : 'rgba(201, 169, 110, 0.6)'
    ctx.stroke()

    // Overlay Header & Brand
    ctx.textAlign = 'left'
    ctx.fillStyle = '#c9a96e'
    ctx.font = '700 18px system-ui, -apple-system, sans-serif'
    ctx.fillText('SATYACHECK · LIVE CALL SHIELD', overlayX + 24, overlayY + 42)

    // Score computation
    const targetScore = isCritical ? Math.min(91, Math.round(14 + (progress - 0.7) * 260)) : 14
    const scoreColor = isCritical ? '#f87171' : '#4ade80'

    ctx.textAlign = 'right'
    ctx.fillStyle = scoreColor
    ctx.font = '700 28px system-ui, -apple-system, sans-serif'
    ctx.fillText(`RISK: ${targetScore}/100`, overlayX + overlayW - 24, overlayY + 44)

    // Primary Warning Label
    ctx.textAlign = 'left'
    ctx.fillStyle = '#f5f0e8'
    ctx.font = '700 22px system-ui, -apple-system, sans-serif'
    if (isCritical) {
      ctx.fillText('CRITICAL IMPERSONATION WARNING', overlayX + 24, overlayY + 95)

      ctx.fillStyle = '#fca5a5'
      ctx.font = '400 18px system-ui, -apple-system, sans-serif'
      ctx.fillText('Phase discontinuity & neural TTS artifact detected.', overlayX + 24, overlayY + 130)
      ctx.fillText('Analysis latency: 212 ms (p90 budget < 400 ms)', overlayX + 24, overlayY + 160)

      // Action pill
      ctx.fillStyle = '#ef4444'
      roundRect(ctx, overlayX + 24, overlayY + 185, overlayW - 48, 48, 12)
      ctx.fill()

      ctx.fillStyle = '#ffffff'
      ctx.font = '600 18px system-ui, -apple-system, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('ACTION: MANDATE OUT-OF-BAND CHALLENGE', overlayX + overlayW / 2, overlayY + 215)
    } else {
      ctx.fillText('CONTINUOUS VOICE ANALYSIS ACTIVE', overlayX + 24, overlayY + 95)

      ctx.fillStyle = '#b8b2a6'
      ctx.font = '400 18px system-ui, -apple-system, sans-serif'
      ctx.fillText('Out-of-band audio stream copy. Call unaltered.', overlayX + 24, overlayY + 130)
      ctx.fillText('4 AI checks evaluating waveform & identity.', overlayX + 24, overlayY + 160)

      // Active status pill
      ctx.fillStyle = 'rgba(74, 222, 128, 0.15)'
      roundRect(ctx, overlayX + 24, overlayY + 185, overlayW - 48, 48, 12)
      ctx.fill()
      ctx.strokeStyle = '#4ade80'
      ctx.stroke()

      ctx.fillStyle = '#4ade80'
      ctx.font = '600 18px system-ui, -apple-system, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('NO SYNTHETIC ANOMALIES DETECTED', overlayX + overlayW / 2, overlayY + 215)
    }

    ctx.restore()
  }

  // 5. Standard Dialer Controls at bottom
  const btnY = height - 120
  const btnRadius = 38
  const btnSpacing = (width - 64) / 4

  const buttons = ['Mute', 'Keypad', 'Speaker', 'End']
  const buttonColors = ['#1f1f26', '#1f1f26', '#1f1f26', '#dc2626']

  buttons.forEach((label, i) => {
    const cx = 48 + i * btnSpacing + btnSpacing / 2 - 16
    ctx.beginPath()
    ctx.arc(cx, btnY, btnRadius, 0, Math.PI * 2)
    ctx.fillStyle = buttonColors[i]
    ctx.fill()

    ctx.fillStyle = '#f5f0e8'
    ctx.font = '500 16px system-ui, -apple-system, sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(label, cx, btnY + 60)
  })
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number
) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + w - r, y)
  ctx.quadraticCurveTo(x + w, y, x + w, y + r)
  ctx.lineTo(x + w, y + h - r)
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
  ctx.lineTo(x + r, y + h)
  ctx.quadraticCurveTo(x, y + h, x, y + h - r)
  ctx.lineTo(x, y + r)
  ctx.quadraticCurveTo(x, y, x + r, y)
  ctx.closePath()
}
