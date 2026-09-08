import { copy } from '../../content/copy'

export function Footer() {
  return (
    <footer className="border-t border-[var(--border-subtle)] px-6 py-[var(--space-4)]">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-3 text-[var(--text-sm)] text-[var(--text-secondary)] md:flex-row md:items-center md:justify-between">
        <p>{copy.footer.status}</p>
        <p className="text-[var(--text-muted)]">{copy.footer.credit}</p>
      </div>
    </footer>
  )
}
