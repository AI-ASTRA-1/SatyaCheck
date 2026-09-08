export function ConfidenceMeter({ confidence }: { confidence: number }) {
  const pct = Math.round(Math.min(1, Math.max(0, confidence)) * 100)
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--text-muted)]">
        <span>Confidence</span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-[var(--radius-pill)] bg-[var(--surface-raised)]">
        <div className="h-full rounded-[var(--radius-pill)] bg-[var(--accent-gold)]" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-[var(--text-xs)] text-[var(--text-muted)]">Aggregate signal confidence, not a threshold.</p>
    </div>
  )
}
