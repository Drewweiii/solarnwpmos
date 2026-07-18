import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useMascotReaction } from '../useMascotReaction'

describe('useMascotReaction', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts idle with no speech', () => {
    const { result } = renderHook(() => useMascotReaction())
    expect(result.current.mood).toBe('idle')
    expect(result.current.speech).toBeNull()
  })

  it('sets mood + speech immediately, then reverts to idle after the given duration', () => {
    const { result } = renderHook(() => useMascotReaction())
    act(() => result.current.trigger('blush', 'ขอบคุณค้าบบ~', 5000))
    expect(result.current.mood).toBe('blush')
    expect(result.current.speech).toBe('ขอบคุณค้าบบ~')

    act(() => vi.advanceTimersByTime(4999))
    expect(result.current.mood).toBe('blush')

    act(() => vi.advanceTimersByTime(1))
    expect(result.current.mood).toBe('idle')
    expect(result.current.speech).toBeNull()
  })

  it('never stacks - 10 rapid identical triggers still clear exactly 5s after the last one, not 50s', () => {
    const { result } = renderHook(() => useMascotReaction())

    // 10 clicks, 500ms apart - the 10th (last) one lands at elapsed t=4500ms
    // and resets the deadline to t=9500ms. If durations stacked instead of
    // resetting, this would instead still be showing at t=9500 (10*5000ms
    // queued) - the whole point of this test is proving they don't.
    for (let i = 0; i < 10; i++) {
      act(() => {
        result.current.trigger('blush', 'ขอบคุณค้าบบ~', 5000)
        vi.advanceTimersByTime(500)
      })
    }
    // Elapsed is now t=5000ms; the last trigger's deadline (t=9500ms) is
    // still 4500ms away.
    expect(result.current.mood).toBe('blush')

    act(() => vi.advanceTimersByTime(4499))
    expect(result.current.mood).toBe('blush')
    act(() => vi.advanceTimersByTime(1))
    expect(result.current.mood).toBe('idle')
  })

  it('a new trigger while one is already pending replaces it instead of queuing', () => {
    const { result } = renderHook(() => useMascotReaction())
    act(() => result.current.trigger('hurt', 'อย่าจิ้มเค้าาา!', 5000))
    act(() => vi.advanceTimersByTime(2000))
    act(() => result.current.trigger('love', 'กอดอุ่นๆ แบบนี้ชอบเลย', 5000))
    expect(result.current.mood).toBe('love')
    expect(result.current.speech).toBe('กอดอุ่นๆ แบบนี้ชอบเลย')

    // The first trigger's original 5s deadline (3s from now) must NOT fire.
    act(() => vi.advanceTimersByTime(3000))
    expect(result.current.mood).toBe('love')

    // The second trigger's own 5s deadline (2s further) does fire.
    act(() => vi.advanceTimersByTime(2000))
    expect(result.current.mood).toBe('idle')
  })

  it('supports a mood change with no speech bubble (AI-answer-driven mood)', () => {
    const { result } = renderHook(() => useMascotReaction())
    act(() => result.current.trigger('happy'))
    expect(result.current.mood).toBe('happy')
    expect(result.current.speech).toBeNull()
  })
})
