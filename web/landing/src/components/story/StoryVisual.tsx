import type { ReactNode } from 'react'
import type { ScrollStoryStepData } from '../../content/copy'

type Variant = ScrollStoryStepData['visual']

const ICONS: Record<Variant, ReactNode> = {
  acquisition: <path d="M3 12h3l2-7 4 14 3-9 2 5h4" />,
  copy: (
    <>
      <rect x="4" y="4" width="11" height="13" rx="1.5" />
      <rect x="9" y="8" width="11" height="13" rx="1.5" fill="none" />
    </>
  ),
  checks: (
    <>
      <circle cx="8" cy="8" r="3" />
      <circle cx="17" cy="8" r="3" />
      <circle cx="8" cy="17" r="3" />
      <circle cx="17" cy="17" r="3" />
    </>
  ),
  fusion: <circle cx="12" cy="12" r="7" />,
  evidence: <path d="M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z" />,
}

interface StoryVisualProps {
  variant: Variant
  label: string
  active: boolean
}

/**
 * Abstract, on-brand panel standing in for a product screenshot. Used both
 * as the sticky desktop image (absolutely positioned, cross-faded by
 * `active`) and inline on mobile. Avoids depending on screenshot assets that
 * don't exist yet (the dashboard hasn't been built in this pass).
 */
export function StoryVisual({ variant, label, active }: StoryVisualProps) {
  return (
    <div
      className="absolute inset-0 flex flex-col items-center justify-center gap-6 bg-[var(--surface)] transition-opacity duration-700 ease-in-out"
      style={{ opacity: active ? 1 : 0 }}
      aria-hidden={!active}
    >
      <div
        className="absolute inset-0"
        style={{ background: 'radial-gradient(circle at 30% 30%, var(--accent-gold-soft), transparent 65%)' }}
      />
      <svg
        width="88"
        height="88"
        viewBox="0 0 24 24"
        fill="none"
        stroke="var(--accent-gold)"
        strokeWidth="1.1"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="relative"
      >
        {ICONS[variant]}
      </svg>
      <span className="relative text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--text-muted)]">
        {label}
      </span>
    </div>
  )
}
