import { checkLabels } from '../../content/labels'
import type { CheckName } from '../../types/risk'

const ALL_CHECKS: CheckName[] = ['machine_fingerprint', 'speaker_identity', 'prosody', 'stt_llm']

const CHECK_DESCRIPTIONS: Record<CheckName, string> = {
  machine_fingerprint: 'Acoustic & phase inconsistency in synthetic speech waveforms',
  speaker_identity: 'Embedding vector distance against enrolled voiceprints',
  prosody: 'Pitch contours, syllable timing, and micro-pause variations',
  stt_llm: 'Scam script & social engineering intent pattern detection',
}

interface ChecksListProps {
  contributing: CheckName[]
  degraded: CheckName[]
}

export function ChecksList({ contributing, degraded }: ChecksListProps) {
  return (
    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
      {ALL_CHECKS.map((check) => {
        const isDegraded = degraded.includes(check)
        const isContributing = contributing.includes(check)
        const status = isDegraded ? 'Degraded' : isContributing ? 'Active / Contributing' : 'Standby / Evaluating'
        const dotColor = isDegraded ? 'var(--risk-medium)' : isContributing ? 'var(--risk-low)' : 'var(--text-muted)'
        const borderClass = isDegraded
          ? 'border-[rgba(251,191,36,0.3)]'
          : isContributing
          ? 'border-[rgba(74,222,128,0.2)]'
          : 'border-[var(--border-subtle)]'

        return (
          <div
            key={check}
            className={`flex flex-col justify-between rounded-[var(--radius)] border bg-[var(--surface)] p-3 transition-colors ${borderClass}`}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-[var(--text-xs)] font-semibold text-[var(--text-primary)]">
                {checkLabels[check]}
              </span>
              <span className="flex items-center gap-1.5 whitespace-nowrap text-[11px] font-medium" style={{ color: dotColor }}>
                <span className="h-2 w-2 rounded-full" style={{ background: dotColor }} aria-hidden="true" />
                {status}
              </span>
            </div>
            <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--text-muted)]">
              {CHECK_DESCRIPTIONS[check]}
            </p>
          </div>
        )
      })}
    </div>
  )
}
