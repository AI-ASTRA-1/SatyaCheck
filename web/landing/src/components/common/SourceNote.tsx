interface SourceNoteProps {
  source?: string
  verified: boolean
  caveat?: string
}

export function SourceNote({ source, verified, caveat }: SourceNoteProps) {
  if (!source && !caveat) return null

  return (
    <p className="mt-2 text-[var(--text-xs)] text-[var(--text-muted)]">
      {source && <span>{source}</span>}
      {!verified && (
        <span className="ml-2 rounded-[var(--radius-pill)] border border-[var(--risk-medium)] px-2 py-0.5 text-[var(--risk-medium)]">
          ID not verified
        </span>
      )}
      {caveat && <span className="mt-1 block">{caveat}</span>}
    </p>
  )
}
