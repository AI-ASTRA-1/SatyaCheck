import { copy } from '../../content/copy'

export function NavBar() {
  return (
    <header className="glass fixed inset-x-0 top-0 z-50">
      <nav className="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-4">
        <a href="#top" className="font-[var(--font-display)] text-[var(--text-md)] tracking-[-0.01em] text-[var(--text-primary)]">
          {copy.nav.brand}
        </a>
        <ul className="hidden items-center gap-8 md:flex">
          {copy.nav.links.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                className="text-[var(--text-sm)] text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>
        <a
          href={import.meta.env.VITE_DASHBOARD_URL ?? '#'}
          className="glow-gold rounded-[var(--radius-pill)] border border-[var(--accent-gold)] px-4 py-2 text-[var(--text-sm)] text-[var(--accent-gold)] transition-transform hover:scale-105"
        >
          {copy.nav.cta}
        </a>
      </nav>
    </header>
  )
}
