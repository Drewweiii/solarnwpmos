import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  buildCompetitionRows,
  exactTimeKey,
  hourKey,
  mergeGeneratedAndForecast,
  nearestToNow,
  nearestToTimestamp,
  sumForecastAcrossZones,
  sumHourlyAcrossZones,
  truncateGeneratedToNow,
  weatherIconFor,
} from '../chartData'
import type { ForecastPoint, HourlyPoint } from '../types'

function hourly(hourUtc: number, ac_kw: number, ssrd_w_m2 = 500, temp_c = 30): HourlyPoint {
  return { timestamp: `2026-07-14T${String(hourUtc).padStart(2, '0')}:00:00Z`, ac_kw, ssrd_w_m2, temp_c }
}

function forecastPoint(
  hourUtc: number,
  pred: number,
  lower: number | null = null,
  upper: number | null = null,
  algorithm: string | null = null,
  error: number | null = null,
  candidateErrors: Record<string, number> | null = null,
): ForecastPoint {
  return {
    timestamp: `2026-07-14T${String(hourUtc).padStart(2, '0')}:00:00Z`,
    pred,
    lower,
    upper,
    algorithm,
    error,
    candidate_errors: candidateErrors,
  }
}

describe('hourKey', () => {
  it('buckets timestamps a few seconds apart into the same key', () => {
    expect(hourKey('2026-07-14T12:00:03Z')).toBe(hourKey('2026-07-14T12:00:57Z'))
  })

  it('keeps different hours distinct', () => {
    expect(hourKey('2026-07-14T12:00:00Z')).not.toBe(hourKey('2026-07-14T13:00:00Z'))
  })
})

describe('exactTimeKey', () => {
  it('keeps different minutes within the same hour distinct, unlike hourKey', () => {
    expect(exactTimeKey('2026-07-14T12:00:00Z')).not.toBe(exactTimeKey('2026-07-14T12:10:00Z'))
  })

  it('is the identity function', () => {
    expect(exactTimeKey('2026-07-14T12:00:00Z')).toBe('2026-07-14T12:00:00Z')
  })
})

describe('mergeGeneratedAndForecast', () => {
  it('outer-joins on hour, filling the missing side with null', () => {
    const rows = mergeGeneratedAndForecast([hourly(10, 20), hourly(11, 30)], [forecastPoint(11, 28, 20, 36), forecastPoint(12, 32, 24, 40)])

    expect(rows.map((r) => r.key)).toEqual(['2026-07-14T10', '2026-07-14T11', '2026-07-14T12'])
    expect(rows[0]).toMatchObject({ generated: 20, pred: null })
    expect(rows[1]).toMatchObject({ generated: 30, pred: 28, lower: 20, upper: 36, band: 16 })
    expect(rows[2]).toMatchObject({ generated: null, pred: 32, band: 16 })
  })

  it('sorts chronologically regardless of input order', () => {
    const rows = mergeGeneratedAndForecast([hourly(15, 5), hourly(9, 1)], [])
    expect(rows.map((r) => r.key)).toEqual(['2026-07-14T09', '2026-07-14T15'])
  })

  it('leaves band null when a forecast point has no PI', () => {
    const rows = mergeGeneratedAndForecast([], [forecastPoint(9, 10)])
    expect(rows[0]).toMatchObject({ pred: 10, lower: null, upper: null, band: null })
  })

  it('carries algorithm and error through from the forecast point', () => {
    const rows = mergeGeneratedAndForecast([], [forecastPoint(9, 10, 8, 12, 'lightgbm', 3.5)])
    expect(rows[0]).toMatchObject({ algorithm: 'lightgbm', error: 3.5 })
  })
})

describe('truncateGeneratedToNow', () => {
  const now = '2026-07-14T12:00:00Z'

  it('nulls generated for rows after now, leaving forecast fields untouched', () => {
    const rows = mergeGeneratedAndForecast(
      [hourly(11, 20), hourly(13, 30)], // 13:00 is "in the future" relative to `now`
      [forecastPoint(13, 28, 20, 36)],
    )
    const truncated = truncateGeneratedToNow(rows, now)
    expect(truncated.find((r) => r.key === '2026-07-14T11')).toMatchObject({ generated: 20 })
    expect(truncated.find((r) => r.key === '2026-07-14T13')).toMatchObject({ generated: null, pred: 28, band: 16 })
  })

  it('leaves a row exactly at now untouched (not yet "in the future")', () => {
    const rows = mergeGeneratedAndForecast([hourly(12, 25)], [])
    const truncated = truncateGeneratedToNow(rows, now)
    expect(truncated[0].generated).toBe(25)
  })

  it('defaults to the real current time when no cutoff is passed', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(now))
    const rows = mergeGeneratedAndForecast([hourly(11, 20), hourly(13, 30)], [])
    expect(truncateGeneratedToNow(rows).map((r) => r.generated)).toEqual([20, null])
    vi.useRealTimers()
  })
})

describe('sumHourlyAcrossZones', () => {
  it('sums power but averages irradiance/temperature across zones', () => {
    const gis = [hourly(12, 40, 900, 32)]
    const isb = [hourly(12, 90, 800, 30)]
    const [row] = sumHourlyAcrossZones([gis, isb])
    expect(row.ac_kw).toBe(130)
    expect(row.ssrd_w_m2).toBe(850)
    expect(row.temp_c).toBe(31)
  })

  it('drops hours not reported by every zone', () => {
    const gis = [hourly(12, 40), hourly(13, 45)]
    const isb = [hourly(12, 90)]
    const rows = sumHourlyAcrossZones([gis, isb])
    expect(rows.map((r) => r.timestamp)).toEqual([hourly(12, 0).timestamp])
  })
})

describe('sumForecastAcrossZones', () => {
  it('sums pred/lower/upper only where every zone has a point', () => {
    const gis = [forecastPoint(12, 10, 8, 12)]
    const isb = [forecastPoint(12, 20, 16, 24)]
    const jetty = [forecastPoint(13, 5, 4, 6)] // different hour - should be dropped
    const rows = sumForecastAcrossZones([gis, isb, jetty])
    expect(rows).toHaveLength(0) // jetty never reports hour 12, gis/isb never report hour 13
  })

  it('sums matching hours', () => {
    const gis = [forecastPoint(12, 10, 8, 12)]
    const isb = [forecastPoint(12, 20, 16, 24)]
    const [row] = sumForecastAcrossZones([gis, isb])
    expect(row).toMatchObject({ pred: 30, lower: 24, upper: 36 })
  })

  it('sums error but drops algorithm (each zone can pick a different winner)', () => {
    const gis = [forecastPoint(12, 10, 8, 12, 'lightgbm', 2)]
    const isb = [forecastPoint(12, 20, 16, 24, 'random_forest', 3)]
    const [row] = sumForecastAcrossZones([gis, isb])
    expect(row.error).toBe(5)
    expect(row.algorithm).toBeNull()
  })

  it('with the default hourKey, drops minute-resolution points that share an hour (the bug found live 2026-07-17)', () => {
    // 6 points at 10-minute steps starting :50 past the hour - straddles an
    // hour boundary exactly like forecast/serving.py's real minute-ahead
    // anchor does. Every zone reports the identical 6 timestamps.
    const minuteTimestamps = [
      '2026-07-14T21:50:00Z', '2026-07-14T22:00:00Z', '2026-07-14T22:10:00Z',
      '2026-07-14T22:20:00Z', '2026-07-14T22:30:00Z', '2026-07-14T22:40:00Z',
    ]
    const zoneSeries = (): ForecastPoint[] =>
      minuteTimestamps.map((timestamp) => ({ timestamp, pred: 10, lower: null, upper: null, algorithm: null, error: null, candidate_errors: null }))

    const rowsWithDefaultKey = sumForecastAcrossZones([zoneSeries(), zoneSeries(), zoneSeries()])
    expect(rowsWithDefaultKey.length).toBeLessThan(6) // demonstrates the bug, not the desired behavior
  })

  it('with exactTimeKey, keeps every minute-resolution point instead of collapsing by hour', () => {
    const minuteTimestamps = [
      '2026-07-14T21:50:00Z', '2026-07-14T22:00:00Z', '2026-07-14T22:10:00Z',
      '2026-07-14T22:20:00Z', '2026-07-14T22:30:00Z', '2026-07-14T22:40:00Z',
    ]
    const zoneSeries = (predBase: number): ForecastPoint[] =>
      minuteTimestamps.map((timestamp) => ({
        timestamp,
        pred: predBase,
        lower: null,
        upper: null,
        algorithm: null,
        error: null,
        candidate_errors: null,
      }))

    const rows = sumForecastAcrossZones([zoneSeries(10), zoneSeries(20), zoneSeries(30)], exactTimeKey)
    expect(rows.map((r) => r.timestamp)).toEqual(minuteTimestamps)
    expect(rows.every((r) => r.pred === 60)).toBe(true) // 10 + 20 + 30 per zone, at every one of the 6 timestamps
  })
})

describe('nearestToNow', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-14T12:05:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('picks the closest timestamp to Date.now()', () => {
    const points = [hourly(10, 1), hourly(12, 2), hourly(13, 3)]
    expect(nearestToNow(points)?.timestamp).toBe(hourly(12, 0).timestamp)
  })

  it('returns undefined for an empty series', () => {
    expect(nearestToNow([])).toBeUndefined()
  })
})

describe('nearestToTimestamp', () => {
  it('picks the closest point to an arbitrary target timestamp, not just now', () => {
    const points = [hourly(6, 1), hourly(12, 2), hourly(18, 3)]
    expect(nearestToTimestamp(points, '2026-07-14T17:00:00Z')?.timestamp).toBe(hourly(18, 0).timestamp)
  })

  it('works for any series with a timestamp field, e.g. ForecastPoint', () => {
    const points = [forecastPoint(6, 10), forecastPoint(12, 20), forecastPoint(18, 30)]
    expect(nearestToTimestamp(points, '2026-07-14T13:00:00Z')?.pred).toBe(20)
  })

  it('returns undefined for an empty series', () => {
    expect(nearestToTimestamp([], '2026-07-14T12:00:00Z')).toBeUndefined()
  })
})

describe('buildCompetitionRows', () => {
  const nowIso = '2026-07-14T12:00:00Z'

  it('builds one row per lead hour, labeled +1h..+6h in order, with each candidate RMSE and the winner', () => {
    const points = [
      forecastPoint(13, 40, null, null, 'lightgbm', 1.2, { lightgbm: 1.2, random_forest: 1.5, sum_k_lstm: 1.4 }),
      forecastPoint(14, 41, null, null, 'random_forest', 0.9, { lightgbm: 1.1, random_forest: 0.9 }),
    ]
    const rows = buildCompetitionRows(points, nowIso)

    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({ leadLabel: '+1h', winner: 'lightgbm', lightgbm: 1.2, randomForest: 1.5, sumKLstm: 1.4 })
    expect(rows[1]).toMatchObject({ leadLabel: '+2h', winner: 'random_forest', lightgbm: 1.1, randomForest: 0.9, sumKLstm: null })
  })

  it('drops points more than an hour in the past (only the live k-step race, not accumulated history)', () => {
    const stale = forecastPoint(9, 10, null, null, 'lightgbm', 1, { lightgbm: 1 })
    const live = forecastPoint(13, 40, null, null, 'lightgbm', 1.2, { lightgbm: 1.2 })
    const rows = buildCompetitionRows([stale, live], nowIso)
    expect(rows).toHaveLength(1)
    expect(rows[0].leadLabel).toBe('+1h')
  })

  it('caps at 6 rows even if more future points are present', () => {
    const points = Array.from({ length: 8 }, (_, i) =>
      forecastPoint(13 + i, 40, null, null, 'lightgbm', 1, { lightgbm: 1 }),
    )
    expect(buildCompetitionRows(points, nowIso)).toHaveLength(6)
  })

  it('computes spread as max - min across whichever candidates competed', () => {
    const point = forecastPoint(13, 40, null, null, 'lightgbm', 1.2, { lightgbm: 1.2, random_forest: 1.5, sum_k_lstm: 1.4 })
    const [row] = buildCompetitionRows([point], nowIso)
    expect(row.spread).toBeCloseTo(0.3) // 1.5 - 1.2
  })

  it('leaves spread null when fewer than 2 candidates have a recorded RMSE', () => {
    const point = forecastPoint(13, 40, null, null, 'lightgbm', 1.2, { lightgbm: 1.2 })
    const [row] = buildCompetitionRows([point], nowIso)
    expect(row.spread).toBeNull()
  })
})

describe('weatherIconFor', () => {
  it('classifies by irradiance ratio', () => {
    expect(weatherIconFor(0)).toBe('night')
    expect(weatherIconFor(200)).toBe('cloudy')
    expect(weatherIconFor(500)).toBe('partly-cloudy')
    expect(weatherIconFor(900)).toBe('sun')
  })
})
