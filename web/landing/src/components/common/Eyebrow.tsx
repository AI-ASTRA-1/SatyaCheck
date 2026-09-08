import type { ReactNode } from 'react'

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="text-[var(--text-xs)] font-medium uppercase tracking-[0.1em] text-[var(--accent-gold)]">
      {children}
    </span>
  )
}
