import { copy } from '../../content/copy'
import { SectionHeading } from '../common/SectionHeading'

export function ProblemSection() {
  return (
    <section className="px-6 py-[var(--space-6)]">
      <SectionHeading eyebrow={copy.problem.eyebrow} heading={copy.problem.heading} intro={copy.problem.body} />
    </section>
  )
}
