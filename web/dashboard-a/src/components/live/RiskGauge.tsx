import { riskLevelMeta } from '../../lib/riskLevelMeta'
import type { RiskLevel } from '../../types/risk'

interface RiskGaugeProps {
  score: number
  riskLevel: RiskLevel
}

const START_ANGLE = -120
const END_ANGLE = 120
const RADIUS = 80
const STROKE = 14

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180
  return { x: cx + r * Math.cos(angleRad), y: cy + r * Math.sin(angleRad) }
}

function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
  const start = polarToCartesian(cx, cy, r, endAngle)
  const end = polarToCartesian(cx, cy, r, startAngle)
  const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1'
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`
}

/**
 * The sweep angle is a continuous, purely cosmetic function of `score`.
 * The stroke color comes from `riskLevelMeta(riskLevel)` only: this is the
 * one place a coding change could accidentally re-derive a band from score
 * by reaching for an interpolated hue instead.
 */
export function RiskGauge({ score, riskLevel }: RiskGaugeProps) {
  const meta = riskLevelMeta(riskLevel)
  const clampedScore = Math.min(100, Math.max(0, score))
  const sweepAngle = START_ANGLE + (clampedScore / 100) * (END_ANGLE - START_ANGLE)
  const size = (RADIUS + STROKE) * 2

  return (
    <div className={`relative flex flex-col items-center justify-center rounded-[var(--radius)] bg-[var(--surface)] p-6 ${meta.glowClass}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <path
          d={describeArc(size / 2, size / 2, RADIUS, START_ANGLE, END_ANGLE)}
          fill="none"
          stroke="var(--border-subtle)"
          strokeWidth={STROKE}
          strokeLinecap="round"
        />
        <path
          d={describeArc(size / 2, size / 2, RADIUS, START_ANGLE, sweepAngle)}
          fill="none"
          stroke={meta.colorVar}
          strokeWidth={STROKE}
          strokeLinecap="round"
          style={{ transition: 'stroke 0.4s ease' }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-[var(--text-3xl)] font-semibold" style={{ color: meta.colorVar }}>
          {Math.round(clampedScore)}
        </span>
        <span className="text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--text-muted)]">{meta.label} risk</span>
      </div>
    </div>
  )
}
