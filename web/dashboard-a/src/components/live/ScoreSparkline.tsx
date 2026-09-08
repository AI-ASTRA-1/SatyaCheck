import { riskLevelMeta } from '../../lib/riskLevelMeta'
import type { RiskLevel } from '../../types/risk'

export interface SparklinePoint {
  score: number
  riskLevel: RiskLevel
}

const WIDTH = 280
const HEIGHT = 64
const PADDING = 6
const MAX_POINTS = 30

// One axis (score only). The line is neutral; only the tick dots carry the
// risk_level status color, per the reserved-status-palette rule.
export function ScoreSparkline({ points }: { points: SparklinePoint[] }) {
  if (points.length < 2) {
    return <p className="text-[var(--text-sm)] text-[var(--text-muted)]">Not enough ticks yet.</p>
  }

  const usable = points.slice(-MAX_POINTS)
  const stepX = (WIDTH - PADDING * 2) / (usable.length - 1)
  const toY = (score: number) => HEIGHT - PADDING - (score / 100) * (HEIGHT - PADDING * 2)
  const linePoints = usable.map((p, i) => `${PADDING + i * stepX},${toY(p.score)}`).join(' ')

  return (
    <svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Score over recent updates">
      <polyline points={linePoints} fill="none" stroke="var(--text-muted)" strokeWidth={2} />
      {usable.map((p, i) => (
        <circle
          key={i}
          cx={PADDING + i * stepX}
          cy={toY(p.score)}
          r={i === usable.length - 1 ? 4 : 2.5}
          fill={riskLevelMeta(p.riskLevel).colorVar}
        />
      ))}
    </svg>
  )
}
