import { riskLevelMeta } from '../../lib/riskLevelMeta'
import type { CallEnded } from '../../types/risk'
import { VerdictBadge } from '../live/VerdictBadge'

export function CallEndedSummary({ message }: { message: CallEnded }) {
  const meta = riskLevelMeta(message.final_level)
  return (
    <div className={`flex flex-col gap-4 rounded-[var(--radius)] border border-[var(--border-subtle)] bg-[var(--surface)] p-6 ${meta.glowClass}`}>
      <p className="text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--text-muted)]">Call ended</p>
      <div className="flex flex-wrap items-center gap-4">
        <span className="font-[var(--font-display)] text-[var(--text-2xl)]" style={{ color: meta.colorVar }}>
          {message.final_score}
        </span>
        <VerdictBadge verdict={message.final_verdict} />
        <span className="text-[var(--text-sm)] text-[var(--text-secondary)]">{meta.label} risk</span>
      </div>
      <p className="text-[var(--text-sm)] text-[var(--text-secondary)]">
        Duration {Math.round(message.duration_seconds)}s.{' '}
        {message.alert_fingerprint ? 'Alert raised, fingerprint sealed.' : 'No alert raised.'}
      </p>
      {message.alert_fingerprint && (
        <dl className="grid grid-cols-1 gap-2 text-[var(--text-xs)] text-[var(--text-muted)] md:grid-cols-2">
          <div>
            <dt className="uppercase tracking-[0.1em]">Fingerprint</dt>
            <dd className="truncate">{message.alert_fingerprint}</dd>
          </div>
          {message.merkle_root && (
            <div>
              <dt className="uppercase tracking-[0.1em]">Merkle root</dt>
              <dd className="truncate">{message.merkle_root}</dd>
            </div>
          )}
          {message.sealed_record_id && (
            <div>
              <dt className="uppercase tracking-[0.1em]">Sealed record</dt>
              <dd className="truncate">{message.sealed_record_id}</dd>
            </div>
          )}
          {message.root_published_at && (
            <div>
              <dt className="uppercase tracking-[0.1em]">Root published</dt>
              <dd>{new Date(message.root_published_at).toLocaleString()}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  )
}
