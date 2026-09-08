import type { Stat } from '../../content/stats'
import { SourceNote } from '../common/SourceNote'

export function StatTile({ stat }: { stat: Stat }) {
  return (
    <div className="glow-gold shadow-[var(--shadow-sm)] rounded-[var(--radius)] border border-[var(--border-subtle)] bg-[var(--surface)] p-6">
      <p className="font-[var(--font-display)] text-[var(--text-xl)] text-[var(--accent-gold)]">{stat.value}</p>
      <p className="mt-2 text-[var(--text-sm)] text-[var(--text-secondary)]">{stat.label}</p>
      <SourceNote source={stat.source} verified={stat.verified} caveat={stat.caveat} />
    </div>
  )
}
