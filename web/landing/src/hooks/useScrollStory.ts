import { useEffect, type RefObject } from 'react'
import { gsap, ScrollTrigger } from '../lib/gsap'
import { useReducedMotion } from './useReducedMotion'

interface UseScrollStoryOptions {
  wrapperRef: RefObject<HTMLElement>
  stepCount: number
  onStepChange?: (index: number) => void
  onProgressChange?: (progress: number) => void
}

/**
 * Tracks scroll progress through a tall wrapper, exposing continuous
 * normalized progress (0 to 1) and step index changes.
 */
export function useScrollStory({
  wrapperRef,
  stepCount,
  onStepChange,
  onProgressChange,
}: UseScrollStoryOptions): boolean {
  const reducedMotion = useReducedMotion()

  useEffect(() => {
    if (reducedMotion || stepCount < 2) return
    const wrapper = wrapperRef.current
    if (!wrapper) return

    const ctx = gsap.context(() => {
      ScrollTrigger.create({
        trigger: wrapper,
        start: 'top top',
        end: 'bottom bottom',
        onUpdate: (self) => {
          onProgressChange?.(self.progress)
          if (onStepChange) {
            const index = Math.min(stepCount - 1, Math.floor(self.progress * stepCount))
            onStepChange(index)
          }
        },
      })
    }, wrapper)

    return () => ctx.revert()
  }, [wrapperRef, stepCount, onStepChange, onProgressChange, reducedMotion])

  return reducedMotion
}

