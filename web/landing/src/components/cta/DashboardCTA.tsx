import { copy } from '../../content/copy'

export function DashboardCTA() {
  return (
    <section className="px-6 py-[var(--space-6)]">
      <div className="glass shadow-[var(--shadow-lg)] mx-auto flex max-w-[900px] flex-col items-center gap-6 rounded-[var(--radius)] p-12 text-center">
        <h2 className="text-[clamp(1.8rem,1.4rem+2vw,2.369rem)] tracking-[-0.02em]">{copy.cta.heading}</h2>
        <p className="max-w-[60ch] text-[var(--text-secondary)]">{copy.cta.body}</p>
        <a
          href={import.meta.env.VITE_DASHBOARD_URL ?? '#'}
          className="glow-gold rounded-[var(--radius-pill)] bg-[var(--accent-gold)] px-8 py-4 text-[var(--text-sm)] font-medium text-[var(--bg)] transition-transform hover:scale-105"
        >
          {copy.cta.button}
        </a>
      </div>
    </section>
  )
}
