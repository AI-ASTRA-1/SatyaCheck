import { copy } from '../../content/copy'
import { SectionHeading } from '../common/SectionHeading'

export function ScopeSection() {
  return (
    <section id="scope" className="px-6 py-[var(--space-6)]">
      <SectionHeading eyebrow={copy.scope.eyebrow} heading={copy.scope.heading} />
      <div className="mx-auto mt-[var(--space-5)] max-w-[900px] overflow-x-auto">
        <table className="w-full border-collapse text-left text-[var(--text-sm)]">
          <thead>
            <tr className="border-b border-[var(--border-subtle)] text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--accent-gold)]">
              <th className="py-3 pr-6 font-medium">Round 1: built and demoed</th>
              <th className="py-3 font-medium">Round 2: described, not built</th>
            </tr>
          </thead>
          <tbody>
            {copy.scope.rows.map((row) => (
              <tr key={row.round1} className="border-b border-[var(--border-subtle)] align-top">
                <td className="py-3 pr-6 text-[var(--text-primary)]">{row.round1}</td>
                <td className="py-3 text-[var(--text-secondary)]">{row.round2 || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
