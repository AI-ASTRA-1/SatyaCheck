import { useCallback, useRef, useState } from 'react'
import type { ScrollStoryStepData } from '../../content/copy'
import { useScrollStory } from '../../hooks/useScrollStory'
import { StoryStep } from './StoryStep'
import { ExplodedPhoneCanvas } from './ExplodedPhoneCanvas'
import { StoryVisual } from './StoryVisual'

export function ScrollStorySection({ steps }: { steps: ScrollStoryStepData[] }) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [progress, setProgress] = useState(0)

  const onStepChange = useCallback((index: number) => setActiveIndex(index), [])
  const onProgressChange = useCallback((p: number) => setProgress(p), [])

  const reducedMotion = useScrollStory({
    wrapperRef,
    stepCount: steps.length,
    onStepChange,
    onProgressChange,
  })

  // Stage labels for HUD indicator
  const stageNames = [
    'Stage 01 to 03: Telephony Ingress & Out-of-Band Copy',
    'Stage 04: Four Parallel AI Checks in 180 ms',
    'Stage 05: Risk Fusion (0 to 100 continuous score)',
    'Stage 06 & 07: In-Call Warning HUD & Merkle Evidence',
  ]
  const currentStageName = stageNames[Math.min(stageNames.length - 1, Math.floor(progress * stageNames.length))]

  return (
    <div ref={wrapperRef} className="relative">
      <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-8 px-6 md:grid-cols-2 md:gap-16">
        {/* Left Column: Fluid Scroll Narrative */}
        <div className="flex flex-col">
          {steps.map((step, i) => {
            const stepCenter = (i + 0.5) / steps.length
            const dist = Math.abs(progress - stepCenter)
            // Gaussian-like smooth opacity calculation
            const smoothOpacity = reducedMotion
              ? 1
              : Math.max(0.35, 1 - Math.pow(dist / (1.2 / steps.length), 2))

            return (
              <div
                key={step.heading}
                className="flex min-h-[85vh] flex-col justify-center py-12 transition-all duration-300"
                style={{ opacity: smoothOpacity }}
              >
                <StoryStep step={step} active={reducedMotion ? true : activeIndex === i} />
              </div>
            )
          })}
        </div>

        {/* Right Column: Pinned 3D Exploded Phone Scene */}
        <div className="hidden md:block">
          <div className="sticky top-[8vh] flex h-[84vh] flex-col overflow-hidden rounded-[var(--radius)] border border-[var(--border-subtle)] bg-[var(--surface)] shadow-[var(--shadow-lg)]">
            {/* Top Telemetry Header */}
            <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-3">
              <span className="flex items-center gap-2 text-[var(--text-xs)] uppercase tracking-[0.1em] text-[var(--accent-gold)]">
                <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--accent-gold)]" />
                Live 3D Architecture
              </span>
              <span className="text-[var(--text-xs)] text-[var(--text-muted)]">
                {Math.round(progress * 100)}% analyzed
              </span>
            </div>

            {/* Canvas Viewport */}
            <div className="relative flex-1">
              {reducedMotion ? (
                <div className="relative h-full w-full">
                  {steps.map((step, i) => (
                    <StoryVisual
                      key={step.heading}
                      variant={step.visual}
                      label={step.eyebrow}
                      active={activeIndex === i}
                    />
                  ))}
                </div>
              ) : (
                <ExplodedPhoneCanvas progress={progress} />
              )}
            </div>

            {/* Bottom Architecture Progress Pill */}
            <div className="border-t border-[var(--border-subtle)] bg-[rgba(10,10,13,0.7)] px-5 py-3 backdrop-blur-md">
              <p className="text-[var(--text-xs)] font-medium text-[var(--text-secondary)]">
                {currentStageName}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
