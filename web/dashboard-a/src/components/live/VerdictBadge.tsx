import type { RiskVerdict } from '../../types/risk'

const VERDICT_LABEL: Record<RiskVerdict, string> = {
  genuine: 'Genuine',
  synthetic: 'Synthetic',
  unknown: 'Unknown',
}

// Deliberately not color-matched to the risk_level palette: two competing
// color systems on one screen would read as contradictory signals.
export function VerdictBadge({ verdict }: { verdict: RiskVerdict }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-[var(--surface)] px-4 py-2 text-[var(--text-sm)] text-[var(--text-primary)]">
      <span className="text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--text-muted)]">Verdict</span>
      {VERDICT_LABEL[verdict]}
    </span>
  )
}
