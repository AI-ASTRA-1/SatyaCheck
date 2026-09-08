import { proofStats } from '../../content/stats'
import { StatTile } from './StatTile'

export function ProofPointsBento() {
  return (
    <section className="px-6 py-[var(--space-6)]">
      <div className="bento-grid mx-auto max-w-[1200px]">
        {proofStats.map((stat) => (
          <StatTile key={stat.label} stat={stat} />
        ))}
      </div>
    </section>
  )
}
