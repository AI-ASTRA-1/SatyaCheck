import type { AppMessage, RiskUpdate } from '../../types/risk'
import { IngressTelemetry } from './IngressTelemetry'
import { AcousticSpectrumCanvas } from './AcousticSpectrumCanvas'
import { ActionProtocolTray } from './ActionProtocolTray'
import { ChecksList } from './ChecksList'
import { ConfidenceMeter } from './ConfidenceMeter'
import { ReasonsList } from './ReasonsList'
import { RiskGauge } from './RiskGauge'
import { ScoreSparkline, type SparklinePoint } from './ScoreSparkline'
import { VerdictBadge } from './VerdictBadge'

interface LiveRiskViewProps {
  current: RiskUpdate
  history: AppMessage[]
}

export function LiveRiskView({ current, history }: LiveRiskViewProps) {
  const sparklinePoints: SparklinePoint[] = history
    .filter((m): m is RiskUpdate => m.kind === 'risk_update')
    .slice(0, 30)
    .reverse()
    .map((m) => ({ score: m.score, riskLevel: m.risk_level }))

  return (
    <div className="flex flex-col gap-5">
      {/* 1. Top Ingress & Ingestion Telemetry */}
      <IngressTelemetry
        streamId={current.stream_id}
        callId={current.call_id}
        sequence={current.sequence}
        isDegraded={current.degraded_checks.length > 0}
      />

      {/* 2. Mission-Control Dual Column Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
        {/* Left Column: Real-Time Decision Stage & Action Playbook */}
        <div className="flex flex-col gap-4">
          <div className="flex flex-col items-center gap-4 rounded-[var(--radius)] border border-[var(--border-subtle)] bg-[var(--surface)] p-6">
            <div className="flex w-full items-center justify-between">
              <VerdictBadge verdict={current.verdict} />
              <span className="text-[var(--text-xs)] text-[var(--text-muted)]">
                {new Date(current.timestamp).toLocaleTimeString()}
              </span>
            </div>

            <RiskGauge score={current.score} riskLevel={current.risk_level} />

            <div className="w-full">
              <ConfidenceMeter confidence={current.confidence} />
            </div>
          </div>

          {/* Actionable Incident Playbook */}
          <ActionProtocolTray riskLevel={current.risk_level} score={current.score} />
        </div>

        {/* Right Column: Acoustic Diagnostics & AI Checks Signal Matrix */}
        <div className="flex flex-col gap-4">
          {/* Live In-Flight Audio Spectrogram */}
          <AcousticSpectrumCanvas
            riskLevel={current.risk_level}
            score={current.score}
            isLive={true}
          />

          {/* Four AI Checks Matrix */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <p className="text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--text-muted)]">
                Four Parallel AI Checks (Stage 04 · Budget &lt; 180 ms)
              </p>
              <span className="text-[var(--text-xs)] text-[var(--text-secondary)]">
                Local CPU Inference (AASIST-L)
              </span>
            </div>
            <ChecksList
              contributing={current.contributing_checks}
              degraded={current.degraded_checks}
            />
          </div>

          {/* Active Diagnostic Reasons */}
          {current.reasons.length > 0 && (
            <div className="flex flex-col gap-2">
              <p className="text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--text-muted)]">
                Active Diagnostic Signals
              </p>
              <ReasonsList reasons={current.reasons} />
            </div>
          )}

          {/* Continuous Score Evolution Sparkline */}
          <div className="flex flex-col gap-2 rounded-[var(--radius)] border border-[var(--border-subtle)] bg-[var(--surface)] p-4">
            <div className="flex items-center justify-between">
              <p className="text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--text-muted)]">
                Continuous Score History (Updated ~1s)
              </p>
              <span className="text-[11px] text-[var(--text-muted)]">Last 30 updates</span>
            </div>
            <ScoreSparkline points={sparklinePoints} />
          </div>
        </div>
      </div>
    </div>
  )
}
