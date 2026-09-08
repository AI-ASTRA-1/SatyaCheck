import type { ReactNode } from 'react'

export function Chip({ children, colorVar }: { children: ReactNode; colorVar?: string }) {
  return (
    <span
      className="inline-flex items-center rounded-[var(--radius-pill)] border px-3 py-1 text-[var(--text-xs)] uppercase tracking-[0.1em]"
      style={{ borderColor: colorVar ?? 'var(--border-subtle)', color: colorVar ?? 'var(--text-secondary)' }}
    >
      {children}
    </span>
  )
}
