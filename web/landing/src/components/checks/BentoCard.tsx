interface BentoCardProps {
  title: string
  subtitle?: string
  body: string
}

export function BentoCard({ title, subtitle, body }: BentoCardProps) {
  return (
    <div className="glass shadow-[var(--shadow-sm)] flex flex-col gap-3 rounded-[var(--radius)] p-6">
      <h3 className="font-[var(--font-display)] text-[var(--text-lg)] tracking-[-0.01em]">{title}</h3>
      {subtitle && (
        <p className="text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--accent-gold)]">{subtitle}</p>
      )}
      <p className="text-[var(--text-sm)] leading-[1.7] text-[var(--text-secondary)]">{body}</p>
    </div>
  )
}
