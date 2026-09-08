interface IngressTelemetryProps {
  streamId: string
  callId: string
  sequence: number
  isDegraded?: boolean
}

export function IngressTelemetry({
  streamId,
  callId,
  sequence,
  isDegraded = false,
}: IngressTelemetryProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-[var(--radius)] border border-[var(--border-subtle)] bg-[var(--surface)] p-4 text-[var(--text-xs)]">
      {/* Telephony Transport */}
      <div className="flex items-center gap-3">
        <span className="flex h-2.5 w-2.5 rounded-full bg-[var(--accent-gold)]" aria-hidden="true" />
        <div>
          <p className="font-semibold text-[var(--text-primary)]">
            Primary Ingress: Exotel Telephony Stream
          </p>
          <p className="text-[var(--text-muted)]">Codec: 8 kHz G.711 / AMR · 20 ms frames</p>
        </div>
      </div>

      {/* Latency & Processing Budget */}
      <div className="flex items-center gap-6">
        <div>
          <p className="text-[var(--text-muted)]">Latency Budget (p90)</p>
          <p className="font-semibold text-[var(--risk-low)]">~210 ms / 400 ms</p>
        </div>

        {/* Ingestion Sequence & Stream Identity */}
        <div>
          <p className="text-[var(--text-muted)]">Call / Stream</p>
          <p className="font-mono text-[var(--text-secondary)]">
            {callId.slice(0, 6)}... ({streamId.slice(0, 6)}...) · #{sequence}
          </p>
        </div>

        {/* Transport Status Badge */}
        <div>
          <span
            className={`rounded-full px-2.5 py-1 font-medium ${
              isDegraded
                ? 'bg-[rgba(251,191,36,0.15)] text-[var(--risk-medium)]'
                : 'bg-[rgba(74,222,128,0.15)] text-[var(--risk-low)]'
            }`}
          >
            {isDegraded ? 'Degraded Ingress' : 'Live In-Flight'}
          </span>
        </div>
      </div>
    </div>
  )
}
