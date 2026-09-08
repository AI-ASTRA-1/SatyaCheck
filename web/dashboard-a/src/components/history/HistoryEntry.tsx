import { riskLevelMeta } from '../../lib/riskLevelMeta'
import type { AppMessage } from '../../types/risk'
import { Chip } from '../common/Chip'

export function HistoryEntry({ message }: { message: AppMessage }) {
  const time = new Date(
    message.kind === 'session_start'
      ? message.started_at
      : message.kind === 'call_ended'
      ? message.ended_at
      : message.timestamp,
  ).toLocaleTimeString()

  if (message.kind === 'session_start') {
    return (
      <li className="flex items-center justify-between border-b border-[var(--border-subtle)] py-2.5 text-[var(--text-sm)] text-[var(--text-muted)]">
        <span className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent-gold)]" />
          Telephony Session Ingestion Started
        </span>
        <span className="font-mono text-[var(--text-xs)]">{time}</span>
      </li>
    )
  }

  const level = message.kind === 'risk_update' ? message.risk_level : message.final_level
  const score = message.kind === 'risk_update' ? message.score : message.final_score
  const meta = riskLevelMeta(level)

  if (message.kind === 'call_ended') {
    return (
      <li className="flex flex-col gap-1.5 border-b border-[var(--border-subtle)] py-3 text-[var(--text-sm)]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Chip colorVar={meta.colorVar}>{meta.label}</Chip>
            <span className="font-medium text-[var(--text-primary)]">
              Call Concluded · Final Score {score}
            </span>
          </div>
          <span className="font-mono text-[var(--text-xs)] text-[var(--text-muted)]">{time}</span>
        </div>

        {/* Cryptographic Merkle Proof Anchor */}
        {message.alert_fingerprint && (
          <div className="mt-1 flex flex-wrap items-center gap-2 rounded bg-[var(--surface-raised)] px-2.5 py-1 text-[11px] text-[var(--text-muted)]">
            <span className="text-[var(--accent-gold)] font-medium">Merkle Anchor:</span>
            <span className="font-mono text-[var(--text-secondary)]">
              {message.alert_fingerprint.slice(0, 16)}...
            </span>
            <span className="rounded bg-[rgba(201,169,110,0.15)] px-1.5 py-0.5 text-[10px] text-[var(--accent-gold)]">
              NCRP 1930 Sealed
            </span>
          </div>
        )}
      </li>
    )
  }

  return (
    <li className="flex items-center justify-between border-b border-[var(--border-subtle)] py-2.5 text-[var(--text-sm)]">
      <div className="flex items-center gap-3">
        <Chip colorVar={meta.colorVar}>{meta.label}</Chip>
        <span className="text-[var(--text-secondary)]">
          Live tick #{message.sequence}, score {score}
        </span>
      </div>
      <span className="font-mono text-[var(--text-xs)] text-[var(--text-muted)]">{time}</span>
    </li>
  )
}
