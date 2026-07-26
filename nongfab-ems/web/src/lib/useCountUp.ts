import { useEffect, useRef, useState } from 'react'

/** Animate a KPI number from its previous value to its new one (project R,
 * 2026-07-26).
 *
 * Two rules this hook exists to enforce, both of them about not lying:
 *
 * **It never animates on mount.** Counting up from zero the first time a tile
 * appears would show the viewer a sequence of numbers the plant never produced,
 * and end on a value that looks like the result of a process rather than a
 * reading. The first value is rendered as-is; only a *change* is animated,
 * because a change is the thing that actually happened.
 *
 * **It always lands exactly.** The final frame assigns the target value rather
 * than whatever the easing computed, so a polled figure can never settle one
 * unit off and sit there being wrong.
 *
 * Honours `prefers-reduced-motion`, in which case it is the identity function.
 */

const DEFAULT_DURATION_MS = 550

/** Ease-out cubic: fast first, settling gently. A linear count reads like a
 * loading spinner rather than a value arriving. */
function easeOut(t: number): number {
  return 1 - (1 - t) ** 3
}

export function prefersReducedMotion(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function useCountUp(target: number | null, durationMs = DEFAULT_DURATION_MS): number | null {
  const [shown, setShown] = useState<number | null>(target)
  const previous = useRef<number | null>(target)

  useEffect(() => {
    const from = previous.current
    previous.current = target

    // Nothing to interpolate between: first render, a cleared value, or a
    // value arriving where there was none.
    if (target === null || from === null || from === target || prefersReducedMotion()) {
      setShown(target)
      return
    }

    let frame = 0
    const started = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - started) / durationMs)
      // Exact landing, not `from + (target - from) * easeOut(1)`, which can
      // drift by a float epsilon and print a number nobody computed.
      setShown(t >= 1 ? target : from + (target - from) * easeOut(t))
      if (t < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs])

  return shown
}
