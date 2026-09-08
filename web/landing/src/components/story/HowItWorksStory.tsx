import { copy } from '../../content/copy'
import { SectionHeading } from '../common/SectionHeading'
import { ScrollStorySection } from './ScrollStorySection'

export function HowItWorksStory() {
  return (
    <section id="how-it-works" className="py-[var(--space-6)]">
      <div className="px-6">
        <SectionHeading eyebrow={copy.howItWorks.eyebrow} heading={copy.howItWorks.heading} intro={copy.howItWorks.intro} />
      </div>
      <div className="mt-[var(--space-5)]">
        <ScrollStorySection steps={copy.howItWorks.steps} />
      </div>
    </section>
  )
}
