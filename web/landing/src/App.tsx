import { DashboardCTA } from './components/cta/DashboardCTA'
import { FourChecksBento } from './components/checks/FourChecksBento'
import { GeneralizationGapSection } from './components/honesty/GeneralizationGapSection'
import { ScopeSection } from './components/honesty/ScopeSection'
import { Hero } from './components/hero/Hero'
import { Footer } from './components/layout/Footer'
import { NavBar } from './components/layout/NavBar'
import { ProblemSection } from './components/problem/ProblemSection'
import { ProofPointsBento } from './components/proof/ProofPointsBento'
import { HowItWorksStory } from './components/story/HowItWorksStory'
import { SectionHeading } from './components/common/SectionHeading'
import { copy } from './content/copy'

export default function App() {
  return (
    <>
      <NavBar />
      <main>
        <Hero />
        <ProblemSection />
        <HowItWorksStory />
        <FourChecksBento />
        <GeneralizationGapSection />
        <ProofPointsBento />
        <ScopeSection />
        <section className="px-6 py-[var(--space-6)]">
          <SectionHeading eyebrow="Privacy and evidence" heading={copy.evidence.heading} intro={copy.evidence.body} />
        </section>
        <DashboardCTA />
      </main>
      <Footer />
    </>
  )
}
