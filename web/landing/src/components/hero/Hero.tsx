import { copy } from '../../content/copy'
import { heroStats } from '../../content/stats'
import { Eyebrow } from '../common/Eyebrow'
import { FloatingStatCard } from './FloatingStatCard'
import { GradientMesh } from './GradientMesh'

export function Hero() {
  return (
    <section id="top" className="relative flex min-h-screen items-center overflow-hidden px-6 pt-24">
      <GradientMesh />
      <div className="relative mx-auto grid max-w-[1200px] gap-12 md:grid-cols-[1.2fr_0.8fr] md:items-center">
        <div>
          <Eyebrow>{copy.hero.eyebrow}</Eyebrow>
          <h1 className="mt-6 text-[clamp(2.5rem,1.8rem+3vw,4.209rem)] tracking-[-0.03em]">{copy.hero.headline}</h1>
          <p className="mt-6 max-w-[55ch] text-[var(--text-lg)] leading-[1.7] text-[var(--text-secondary)]">
            {copy.hero.sub}
          </p>
          <div className="mt-10 flex flex-wrap gap-4">
            <a
              href="#how-it-works"
              className="rounded-[var(--radius-pill)] bg-[var(--accent-gold)] px-6 py-3 text-[var(--text-sm)] font-medium text-[var(--bg)] transition-transform hover:scale-105"
            >
              {copy.hero.ctaPrimary}
            </a>
            <a
              href={import.meta.env.VITE_DASHBOARD_URL ?? '#'}
              className="glass rounded-[var(--radius-pill)] px-6 py-3 text-[var(--text-sm)] text-[var(--text-primary)] transition-transform hover:scale-105"
            >
              {copy.hero.ctaSecondary}
            </a>
          </div>
        </div>
        <div className="flex flex-col gap-4">
          {heroStats.map((stat) => (
            <FloatingStatCard key={stat.label} stat={stat} />
          ))}
        </div>
      </div>
    </section>
  )
}
