import type { AppMessage } from '../../types/risk'
import { HistoryEntry } from './HistoryEntry'

// history is newest-first (see useAppSocket), matching a top-loaded feed.
export function AlertHistory({ history }: { history: AppMessage[] }) {
  if (history.length === 0) {
    return <p className="text-[var(--text-sm)] text-[var(--text-muted)]">No messages yet.</p>
  }
  return (
    <ul className="flex max-h-[360px] flex-col overflow-y-auto rounded-[var(--radius)] border border-[var(--border-subtle)] bg-[var(--surface)] px-4">
      {history.map((message, i) => (
        <HistoryEntry key={i} message={message} />
      ))}
    </ul>
  )
}
