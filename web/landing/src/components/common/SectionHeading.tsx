import { Eyebrow } from './Eyebrow'

interface SectionHeadingProps {
  eyebrow: string
  heading: string
  intro?: string
}

export function SectionHeading({ eyebrow, heading, intro }: SectionHeadingProps) {
  return (
    <div className="mx-auto max-w-[720px] text-center">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="mt-4 text-[clamp(2rem,1.5rem+2vw,3.157rem)] tracking-[-0.02em]">{heading}</h2>
      {intro && <p className="mx-auto mt-4 max-w-[65ch] text-[var(--text-secondary)]">{intro}</p>}
    </div>
  )
}
