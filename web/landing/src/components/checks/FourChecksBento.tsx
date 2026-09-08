import { copy } from '../../content/copy'
import { SectionHeading } from '../common/SectionHeading'
import { BentoCard } from './BentoCard'

export function FourChecksBento() {
  return (
    <section className="px-6 py-[var(--space-6)]">
      <SectionHeading eyebrow={copy.fourChecks.eyebrow} heading={copy.fourChecks.heading} intro={copy.fourChecks.intro} />
      <div className="bento-grid mx-auto mt-[var(--space-5)] max-w-[1200px]">
        {copy.fourChecks.checks.map((check) => (
          <BentoCard key={check.name} title={check.name} subtitle={check.model} body={check.question} />
        ))}
      </div>
    </section>
  )
}
