import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useCountUp } from '../useCountUp'

/** The two properties worth protecting are both about not showing a number
 * that never happened: no animation on mount, and an exact landing. */

function Probe({ value }: { value: number | null }) {
  const shown = useCountUp(value, 100)
  return <span data-testid="v">{shown === null ? 'null' : String(shown)}</span>
}

function setReducedMotion(reduce: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: reduce && query.includes('reduced-motion'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
}

describe('useCountUp', () => {
  beforeEach(() => {
    setReducedMotion(false)
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('shows the first value immediately instead of counting up from zero', () => {
    // Counting up on mount would walk the viewer through a sequence of outputs
    // the plant never produced, and make a reading look like a computation.
    render(<Probe value={850} />)
    expect(screen.getByTestId('v')).toHaveTextContent('850')
  })

  it('lands exactly on the target, not near it', async () => {
    const { rerender } = render(<Probe value={100} />)
    rerender(<Probe value={200} />)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    // A polled figure that settles a fraction off and stays there is simply
    // displaying a wrong number.
    expect(screen.getByTestId('v')).toHaveTextContent('200')
  })

  it('is the identity function when the viewer asked for reduced motion', async () => {
    setReducedMotion(true)
    const { rerender } = render(<Probe value={10} />)
    rerender(<Probe value={99} />)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByTestId('v')).toHaveTextContent('99')
  })

  it('passes null straight through rather than animating toward zero', async () => {
    const { rerender } = render(<Probe value={500} />)
    rerender(<Probe value={null} />)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    // null means "no forecast", which must render as an em dash upstream -
    // easing it down to 0 would turn missing data into a confident zero.
    expect(screen.getByTestId('v')).toHaveTextContent('null')
  })
})
