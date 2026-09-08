import type { ConnectionState } from '../../lib/useAppSocket'

interface ConnectionStatusProps {
  state: ConnectionState
  lastMessageAt: number | null
  now: number
}

export function ConnectionStatus({ state, lastMessageAt, now }: ConnectionStatusProps) {
  if (state === 'open') {
    return (
      <div className="flex items-center gap-2 text-[var(--text-xs)] text-[var(--text-muted)]">
        <span className="h-2 w-2 rounded-full bg-[var(--risk-low)]" aria-hidden="true" />
        Connected to the fake local risk stream
      </div>
    )
  }

  const staleness = lastMessageAt ? Math.round((now - lastMessageAt) / 1000) : null

  if (state === 'connecting') {
    return (
      <div className="glow-gold flex items-center gap-3 rounded-[var(--radius)] border border-[var(--border-subtle)] bg-[var(--surface)] px-5 py-3 text-[var(--text-sm)] text-[var(--text-secondary)]">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--accent-gold)]" aria-hidden="true" />
        Connecting to the live risk stream.
      </div>
    )
  }

  return (
    <div className="glow-critical flex items-center gap-3 rounded-[var(--radius)] border border-[var(--risk-critical)] bg-[var(--surface)] px-5 py-3 text-[var(--text-sm)] text-[var(--risk-critical)]">
      <span className="h-2 w-2 rounded-full bg-[var(--risk-critical)]" aria-hidden="true" />
      Disconnected. No live signal{staleness !== null ? ` (last update ${staleness}s ago)` : ''}.
    </div>
  )
}
