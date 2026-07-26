import { describe, expect, it } from 'vitest'
import {
  EMPTY_KPI,
  computeForecastKpi,
  inferStepHours,
  pointsAhead,
  pointsForTomorrow,
} from '../forecastKpi'
import type { ForecastPoint } from '../types'

function point(timestamp: string, pred: number, lower: number | null = null, upper: number | null = null): ForecastPoint {
  return { timestamp, pred, lower, upper, algorithm: 'lightgbm', error: null, candidate_errors: null }
}

describe('inferStepHours', () => {
  it('reads the step off the data instead of assuming hourly', () => {
    const quarterHourly = [
      point('2026-07-25T00:00:00Z', 1),
      point('2026-07-25T00:15:00Z', 1),
      point('2026-07-25T00:30:00Z', 1),
    ]
    expect(inferStepHours(quarterHourly)).toBe(0.25)
  })

  it('takes the median so one gap cannot inflate the energy total', () => {
    // Five hourly points with a six-hour hole in the middle. A mean step would
    // be ~2.2h and would more than double every kWh figure downstream.
    const gappy = [
      point('2026-07-25T00:00:00Z', 1),
      point('2026-07-25T01:00:00Z', 1),
      point('2026-07-25T07:00:00Z', 1),
      point('2026-07-25T08:00:00Z', 1),
      point('2026-07-25T09:00:00Z', 1),
    ]
    expect(inferStepHours(gappy)).toBe(1)
  })

  it('falls back to one hour for a single point rather than dividing by zero', () => {
    expect(inferStepHours([point('2026-07-25T00:00:00Z', 1)])).toBe(1)
  })
})

describe('pointsForTomorrow', () => {
  it('uses the Thai calendar day, not the UTC one', () => {
    // 2026-07-26T00:30Z is 07:30 on the 26th in Bangkok, so it belongs to
    // "tomorrow" for a viewer standing at 2026-07-25 ICT. 2026-07-26T18:00Z is
    // already 01:00 on the 27th ICT and must NOT be counted.
    const points = [
      point('2026-07-26T00:30:00Z', 10),
      point('2026-07-26T18:00:00Z', 20),
    ]
    const kept = pointsForTomorrow(points, '2026-07-25T05:00:00Z')
    expect(kept.map((p) => p.pred)).toEqual([10])
  })

  it('drops a point that is only tomorrow in UTC terms', () => {
    // 17:30Z on the 25th is already 00:30 on the 26th in Bangkok - tomorrow to
    // a Thai reader even though UTC still calls it today.
    const points = [point('2026-07-25T17:30:00Z', 5)]
    expect(pointsForTomorrow(points, '2026-07-25T05:00:00Z')).toHaveLength(1)
  })
})

describe('pointsAhead', () => {
  it('keeps only what has not happened yet', () => {
    const points = [
      point('2026-07-25T04:00:00Z', 1),
      point('2026-07-25T05:00:00Z', 2),
      point('2026-07-25T06:00:00Z', 3),
    ]
    expect(pointsAhead(points, '2026-07-25T05:00:00Z').map((p) => p.pred)).toEqual([3])
  })
})

describe('computeForecastKpi', () => {
  const day = [
    point('2026-07-25T00:00:00Z', 0),
    point('2026-07-25T01:00:00Z', 20, 15, 25),
    point('2026-07-25T02:00:00Z', 60, 45, 75),
    point('2026-07-25T03:00:00Z', 40, 30, 50),
    point('2026-07-25T04:00:00Z', 0),
  ]

  it('turns hourly kW into kWh using the inferred step', () => {
    expect(computeForecastKpi(day).energyKwh).toBe(120)
  })

  it('scales energy by a sub-hourly step rather than counting samples', () => {
    const halfHourly = [
      point('2026-07-25T00:00:00Z', 100),
      point('2026-07-25T00:30:00Z', 100),
    ]
    // Two half-hour samples at 100 kW is 100 kWh, not 200.
    expect(computeForecastKpi(halfHourly).energyKwh).toBe(100)
  })

  it('reports the peak and the hour it lands on', () => {
    const kpi = computeForecastKpi(day)
    expect(kpi.peakKw).toBe(60)
    expect(kpi.peakAtIso).toBe('2026-07-25T02:00:00Z')
  })

  it('reports the interval at the peak as a half-width', () => {
    const kpi = computeForecastKpi(day)
    expect(kpi.bandKw).toBe(15)
    expect(kpi.bandPct).toBe(25)
  })

  it('leaves the band null when the model published no interval', () => {
    // The physics-baseline fallback has no interval at all. Reporting +/-0
    // would read as perfect confidence, which is the opposite of the truth.
    const noBand = [point('2026-07-25T02:00:00Z', 60)]
    const kpi = computeForecastKpi(noBand)
    expect(kpi.bandKw).toBeNull()
    expect(kpi.bandPct).toBeNull()
  })

  it('counts productive hours relative to the peak, not an absolute floor', () => {
    // 3 of the 5 hours are above 5% of the 60 kW peak.
    expect(computeForecastKpi(day).productiveHours).toBe(3)
  })

  it('returns the empty shape for an empty window instead of a confident zero', () => {
    expect(computeForecastKpi([])).toEqual(EMPTY_KPI)
    expect(computeForecastKpi([]).energyKwh).toBeNull()
  })

  it('ignores non-finite predictions rather than poisoning the sum', () => {
    const withNaN = [point('2026-07-25T01:00:00Z', Number.NaN), point('2026-07-25T02:00:00Z', 10)]
    const kpi = computeForecastKpi(withNaN)
    expect(kpi.energyKwh).toBe(10)
    expect(kpi.pointCount).toBe(1)
  })

  it('does not let a negative prediction subtract from the energy total', () => {
    const withNegative = [point('2026-07-25T01:00:00Z', -5), point('2026-07-25T02:00:00Z', 10)]
    expect(computeForecastKpi(withNegative).energyKwh).toBe(10)
  })
})
