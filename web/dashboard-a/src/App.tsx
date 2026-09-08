import { useMemo } from 'react'
import { AlertHistory } from './components/history/AlertHistory'
import { CallEndedSummary } from './components/history/CallEndedSummary'
import { ConnectionStatus } from './components/connection/ConnectionStatus'
import { AppShell } from './components/layout/AppShell'
import { FallbackBadge } from './components/layout/FallbackBadge'
import { LiveRiskView } from './components/live/LiveRiskView'
import { useNowTick } from './hooks/useNowTick'
import { useAppSocket } from './lib/useAppSocket'
import type { RiskUpdate } from './types/risk'

const MOCK_WS_URL = import.meta.env.VITE_MOCK_WS_URL ?? 'ws://localhost:8787'

export default function App() {
  const { connectionState, latest, history, lastMessageAt } = useAppSocket(MOCK_WS_URL)
  const now = useNowTick()
  const isStale = connectionState !== 'open'

  const body = useMemo(() => {
    if (!latest) {
      return <p className="text-[var(--text-sm)] text-[var(--text-muted)]">Waiting for a session to start.</p>
    }
    if (latest.kind === 'session_start') {
      return <p className="text-[var(--text-sm)] text-[var(--text-muted)]">Session started, waiting for the first risk update.</p>
    }
    if (latest.kind === 'risk_update') {
      return (
        <div className={isStale ? 'opacity-60 grayscale' : ''}>
          <LiveRiskView current={latest as RiskUpdate} history={history} />
        </div>
      )
    }
    return <CallEndedSummary message={latest} />
  }, [latest, history, isStale])

  return (
    <AppShell>
      <div className="flex flex-col gap-6">
        <ConnectionStatus state={connectionState} lastMessageAt={lastMessageAt} now={now} />
        {body}
        <section>
          <h2 className="mb-3 text-[var(--text-lg)] tracking-[-0.01em]">Alert history</h2>
          <AlertHistory history={history} />
        </section>
      </div>
      <FallbackBadge />
    </AppShell>
  )
}
