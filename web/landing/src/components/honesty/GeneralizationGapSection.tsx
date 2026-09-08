import { copy } from '../../content/copy'
import { gapStats } from '../../content/stats'
import { SectionHeading } from '../common/SectionHeading'
import { SourceNote } from '../common/SourceNote'

export function GeneralizationGapSection() {
  return (
    <section id="the-gap" className="px-6 py-[var(--space-6)]">
      <SectionHeading eyebrow={copy.gap.eyebrow} heading={copy.gap.heading} intro={copy.gap.body} />
      <div className="mx-auto mt-[var(--space-5)] grid max-w-[900px] grid-cols-1 gap-6 md:grid-cols-2">
        {gapStats.map((stat) => (
          <div key={stat.label} className="rounded-[var(--radius)] border border-[var(--border-subtle)] p-6">
            <p className="font-[var(--font-display)] text-[var(--text-2xl)] text-[var(--accent-gold)]">{stat.value}</p>
            <p className="mt-2 text-[var(--text-sm)] text-[var(--text-secondary)]">{stat.label}</p>
            <SourceNote source={stat.source} verified={stat.verified} caveat={stat.caveat} />
          </div>
        ))}
      </div>
    </section>
  )
}
