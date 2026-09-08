import { reasonLabels } from '../../content/labels'
import type { ReasonCode } from '../../types/risk'

export function ReasonsList({ reasons }: { reasons: ReasonCode[] }) {
  if (reasons.length === 0) {
    return <p className="text-[var(--text-sm)] text-[var(--text-muted)]">No reasons reported yet.</p>
  }
  return (
    <ul className="flex flex-col gap-2">
      {reasons.map((reason, i) => (
        <li key={`${reason}-${i}`} className="text-[var(--text-sm)] text-[var(--text-secondary)]">
          {reasonLabels[reason]}
        </li>
      ))}
    </ul>
  )
}
