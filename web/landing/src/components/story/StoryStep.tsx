import type { ScrollStoryStepData } from '../../content/copy'
import { Eyebrow } from '../common/Eyebrow'
import { StoryVisual } from './StoryVisual'

interface StoryStepProps {
  step: ScrollStoryStepData
  active: boolean
}

export function StoryStep({ step, active }: StoryStepProps) {
  return (
    <div
      className={`flex flex-col gap-4 transition-opacity duration-500 ${
        active ? 'opacity-100' : 'opacity-50 md:opacity-40'
      }`}
    >
      <div className="relative h-40 overflow-hidden rounded-[var(--radius)] border border-[var(--border-subtle)] md:hidden">
        <StoryVisual variant={step.visual} label={step.eyebrow} active />
      </div>
      <Eyebrow>{step.eyebrow}</Eyebrow>
      <h3 className="text-[var(--text-xl)] tracking-[-0.02em]">{step.heading}</h3>
      <p className="max-w-[60ch] leading-[1.7] text-[var(--text-secondary)]">{step.body}</p>
    </div>
  )
}
