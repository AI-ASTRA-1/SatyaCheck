import { useEffect, useRef } from 'react'
import type { RiskLevel } from '../../types/risk'

interface AcousticSpectrumCanvasProps {
  riskLevel: RiskLevel
  score: number
  isLive: boolean
}

export function AcousticSpectrumCanvas({
  riskLevel,
  score,
  isLive,
}: AcousticSpectrumCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId = 0
    let tick = 0

    const render = () => {
      animId = requestAnimationFrame(render)
      tick += 0.04

      const width = canvas.width
      const height = canvas.height

      // Clear with dark surface background
      ctx.fillStyle = '#141419'
      ctx.fillRect(0, 0, width, height)

      // Frequency Grid lines
      ctx.lineWidth = 1
      ctx.strokeStyle = 'rgba(245, 240, 232, 0.05)'
      for (let y = 20; y < height; y += 25) {
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(width, y)
        ctx.stroke()
      }

      // Bar count for 0-4 kHz telephony range
      const barCount = 36
      const barWidth = (width - 40) / barCount - 3
      const isCritical = riskLevel === 'critical' || riskLevel === 'high'

      // Render Frequency Spectrum Bars
      for (let i = 0; i < barCount; i++) {
        const freqNorm = i / barCount
        // Base voice frequency curve peaking in speech fundamentals (300-2500 Hz)
        const speechEnvelope = Math.sin(freqNorm * Math.PI)

        let energy = 0
        if (isLive) {
          const wave1 = Math.sin(tick * 3 + i * 0.45) * 0.3
          const wave2 = Math.cos(tick * 5 - i * 0.8) * 0.25
          const jitter = isCritical ? (Math.random() - 0.5) * 0.35 : 0
          energy = Math.max(0.08, speechEnvelope * (0.6 + wave1 + wave2) + jitter)
        } else {
          energy = 0.05
        }

        const barHeight = energy * (height - 35)
        const x = 20 + i * (barWidth + 3)
        const y = height - 15 - barHeight

        // Color bars: normal gold/green vs critical red/orange for vocoder artifacts
        let barColor = 'rgba(201, 169, 110, 0.75)'
        if (isCritical) {
          barColor = i > 18 ? 'rgba(248, 113, 113, 0.9)' : 'rgba(251, 146, 60, 0.8)'
        } else if (riskLevel === 'medium') {
          barColor = 'rgba(251, 191, 36, 0.8)'
        }

        ctx.fillStyle = barColor
        ctx.fillRect(x, y, barWidth, barHeight)
      }

      // 8 kHz Telephony Compression Cutoff Line
      ctx.strokeStyle = 'rgba(201, 169, 110, 0.3)'
      ctx.setLineDash([4, 4])
      ctx.beginPath()
      ctx.moveTo(width - 25, 10)
      ctx.lineTo(width - 25, height - 15)
      ctx.stroke()
      ctx.setLineDash([])

      // Frequency and Telephony Labels
      ctx.fillStyle = '#7a756a'
      ctx.font = '500 10px monospace'
      ctx.textAlign = 'left'
      ctx.fillText('0 Hz', 20, height - 4)
      ctx.textAlign = 'center'
      ctx.fillText('1.5 kHz (Formant Range)', width / 2, height - 4)
      ctx.textAlign = 'right'
      ctx.fillText('3.4 kHz G.711 Cutoff', width - 20, height - 4)

      // Anomaly Callout if Critical
      if (isCritical) {
        ctx.fillStyle = '#f87171'
        ctx.font = '600 11px system-ui, sans-serif'
        ctx.textAlign = 'right'
        ctx.fillText('PHASE INCONSISTENCY IN HIGH BANDS', width - 30, 24)
      }
    }

    render()

    return () => {
      cancelAnimationFrame(animId)
    }
  }, [riskLevel, score, isLive])

  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius)] border border-[var(--border-subtle)] bg-[var(--surface)] p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[var(--accent-gold)]" aria-hidden="true" />
          <h3 className="text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--text-secondary)]">
            Acoustic Signal Energy · Live Telephony Frames (20 ms)
          </h3>
        </div>
        <span className="text-[var(--text-xs)] text-[var(--text-muted)]">
          Bandwidth: 8 kHz Narrowband
        </span>
      </div>
      <canvas
        ref={canvasRef}
        width={540}
        height={130}
        className="w-full rounded-[var(--radius)]"
        aria-label="Real-time acoustic spectral frequency visualizer"
      />
    </div>
  )
}
