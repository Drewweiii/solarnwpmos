import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useForecastHistory } from '../forecastHistory'
import type { ForecastPoint } from '../types'

function point(timestamp: string, pred: number): ForecastPoint {
  return { timestamp, pred, lower: pred - 2, upper: pred + 2, algorithm: null, error: null }
}

describe('useForecastHistory', () => {
  it('keeps points from an earlier poll even once a later poll no longer includes them', () => {
    const { result, rerender } = renderHook(({ latest }) => useForecastHistory(latest, 'GIS:hour'), {
      initialProps: { latest: [point('2026-07-18T09:00:00Z', 10)] },
    })
    expect(result.current.map((p) => p.timestamp)).toEqual(['2026-07-18T09:00:00Z'])

    // Next poll's forward-looking window has moved on - 09:00 is no longer
    // in it, but it should still be remembered.
    rerender({ latest: [point('2026-07-18T10:00:00Z', 12)] })
    expect(result.current.map((p) => p.timestamp)).toEqual(['2026-07-18T09:00:00Z', '2026-07-18T10:00:00Z'])
  })

  it('overwrites an older point for the same timestamp with a newer issuance', () => {
    const { result, rerender } = renderHook(({ latest }) => useForecastHistory(latest, 'GIS:hour'), {
      initialProps: { latest: [point('2026-07-18T09:00:00Z', 10)] },
    })
    rerender({ latest: [point('2026-07-18T09:00:00Z', 15)] })
    expect(result.current).toEqual([point('2026-07-18T09:00:00Z', 15)])
  })

  it('resets accumulated history when resetKey changes (switching zone or horizon)', () => {
    const { result, rerender } = renderHook(({ latest, resetKey }) => useForecastHistory(latest, resetKey), {
      initialProps: { latest: [point('2026-07-18T09:00:00Z', 10)], resetKey: 'GIS:hour' },
    })
    expect(result.current).toHaveLength(1)

    rerender({ latest: [], resetKey: 'ISB:hour' })
    expect(result.current).toHaveLength(0)

    rerender({ latest: [point('2026-07-18T11:00:00Z', 20)], resetKey: 'ISB:hour' })
    expect(result.current.map((p) => p.timestamp)).toEqual(['2026-07-18T11:00:00Z'])
  })

  it('returns points sorted by timestamp regardless of arrival order', () => {
    const { result, rerender } = renderHook(({ latest }) => useForecastHistory(latest, 'GIS:hour'), {
      initialProps: { latest: [point('2026-07-18T12:00:00Z', 30)] },
    })
    rerender({ latest: [point('2026-07-18T09:00:00Z', 10)] })
    expect(result.current.map((p) => p.timestamp)).toEqual(['2026-07-18T09:00:00Z', '2026-07-18T12:00:00Z'])
  })

  it('regression: a brand-new array/object with the same field values does not keep re-triggering state updates', () => {
    // sumForecastAcrossZones and query-derived arrays rebuild a fresh array
    // (and fresh point objects) on every render even when nothing about the
    // underlying data changed - comparing by object identity here caused an
    // infinite render loop in practice ("Maximum update depth exceeded",
    // found live testing this fix). This locks in the value-based fix: the
    // same logical point, as a new object, must not keep replacing itself.
    const { result, rerender } = renderHook(({ latest }) => useForecastHistory(latest, 'GIS:hour'), {
      initialProps: { latest: [point('2026-07-18T09:00:00Z', 10)] },
    })
    const firstResult = result.current

    // Same timestamp/values, but a brand-new array and a brand-new object -
    // exactly what an unstable upstream memo produces every render.
    rerender({ latest: [point('2026-07-18T09:00:00Z', 10)] })

    expect(result.current).toBe(firstResult) // bailed out - no new Map, no re-render caused by this hook
  })
})
