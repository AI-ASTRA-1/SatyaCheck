import type { Stat } from '../../content/stats'

export function FloatingStatCard({ stat }: { stat: Stat }) {
  return (
    <div className="glass shadow-[var(--shadow-md)] rounded-[var(--radius)] p-6">
      <p className="font-[var(--font-display)] text-[var(--text-2xl)] tracking-[-0.02em] text-[var(--accent-gold)]">
        {stat.value}
      </p>
      <p className="mt-2 text-[var(--text-sm)] text-[var(--text-secondary)]">{stat.label}</p>
    </div>
  )
}
