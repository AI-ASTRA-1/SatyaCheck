import { useState } from 'react'
import type { RiskLevel } from '../../types/risk'

interface ActionProtocolTrayProps {
  riskLevel: RiskLevel
  score: number
}

export function ActionProtocolTray({ riskLevel, score }: ActionProtocolTrayProps) {
  const [activeAction, setActiveAction] = useState<string | null>(null)

  const isCritical = riskLevel === 'critical'
  const isHigh = riskLevel === 'high'
  const isElevated = isCritical || isHigh

  return (
    <div
      className={`flex flex-col gap-3 rounded-[var(--radius)] border p-4 transition-all duration-300 ${
        isCritical
          ? 'border-[var(--risk-critical)] bg-[rgba(248,113,113,0.06)]'
          : isHigh
          ? 'border-[var(--risk-high)] bg-[rgba(251,146,60,0.06)]'
          : 'border-[var(--border-subtle)] bg-[var(--surface)]'
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--text-muted)]">
          Operator Intervention Playbook
        </span>
        <span
          className={`text-[var(--text-xs)] font-medium ${
            isElevated ? 'text-[var(--risk-critical)]' : 'text-[var(--risk-low)]'
          }`}
        >
          {isElevated ? 'Urgent Action Recommended' : 'Routine Verification'}
        </span>
      </div>

      {isElevated ? (
        <div className="flex flex-col gap-2.5">
          <p className="text-[var(--text-sm)] font-medium text-[var(--text-primary)]">
            High probability of AI-cloned or synthetic speech (Score: {score}/100).
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setActiveAction('challenge')}
              className={`rounded-[var(--radius-pill)] px-3.5 py-1.5 text-[var(--text-xs)] font-medium transition-colors ${
                activeAction === 'challenge'
                  ? 'bg-[var(--risk-critical)] text-white'
                  : 'bg-[rgba(248,113,113,0.2)] text-[var(--risk-critical)] hover:bg-[rgba(248,113,113,0.3)]'
              }`}
            >
              Mandate Out-of-Band Challenge
            </button>
            <button
              type="button"
              onClick={() => setActiveAction('freeze')}
              className={`rounded-[var(--radius-pill)] px-3.5 py-1.5 text-[var(--text-xs)] font-medium transition-colors ${
                activeAction === 'freeze'
                  ? 'bg-[var(--risk-critical)] text-white'
                  : 'bg-[rgba(248,113,113,0.2)] text-[var(--risk-critical)] hover:bg-[rgba(248,113,113,0.3)]'
              }`}
            >
              Halt Telephonic Funds Authorization
            </button>
            <button
              type="button"
              onClick={() => setActiveAction('ncrp')}
              className={`rounded-[var(--radius-pill)] px-3.5 py-1.5 text-[var(--text-xs)] font-medium transition-colors ${
                activeAction === 'ncrp'
                  ? 'bg-[var(--accent-gold)] text-[var(--bg)]'
                  : 'glass text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
            >
              Prepare NCRP / 1930 Sealed Report
            </button>
          </div>

          {activeAction && (
            <div className="mt-1 rounded-[var(--radius)] bg-[var(--surface-raised)] p-3 text-[var(--text-xs)] text-[var(--text-secondary)]">
              {activeAction === 'challenge' && (
                <p>
                  Protocol active: Ask the caller an unscripted, out-of-band question (e.g. personal shared fact) that neural TTS systems cannot predict.
                </p>
              )}
              {activeAction === 'freeze' && (
                <p>
                  Protocol active: Flagged to core banking API. Approvals or fund release requests over telephonic channels are locked pending dual-factor verification.
                </p>
              )}
              {activeAction === 'ncrp' && (
                <p>
                  Protocol active: Alert fingerprint and Merkle tree root generated for cybercrime dispatch under National Cyber Crime Reporting Portal (1930 / I4C).
                </p>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="flex items-center justify-between text-[var(--text-sm)] text-[var(--text-secondary)]">
          <span>Acoustic and prosodic parameters within normal human speech variation.</span>
          <span className="flex items-center gap-1.5 text-[var(--risk-low)]">
            <span className="h-2 w-2 rounded-full bg-[var(--risk-low)]" />
            Clear
          </span>
        </div>
      )}

      {/* Safety invariant disclosure */}
      <p className="border-t border-[var(--border-subtle)] pt-2 text-[11px] text-[var(--text-muted)]">
        SatyaCheck operates out-of-band on an audio copy. Telephony audio is never altered or automatically terminated.
      </p>
    </div>
  )
}
