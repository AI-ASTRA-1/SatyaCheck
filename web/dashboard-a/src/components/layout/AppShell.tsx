import type { ReactNode } from 'react'

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto min-h-screen max-w-[1200px] px-6 pb-24 pt-10">
      <header className="mb-8">
        <p className="text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--accent-gold)]">SatyaCheck</p>
        <h1 className="mt-2 text-[clamp(1.8rem,1.5rem+1.5vw,2.369rem)] tracking-[-0.02em]">Live risk view</h1>
      </header>
      {children}
    </div>
  )
}
