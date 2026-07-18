import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  buildCompetitionRows,
  exactTimeKey,
  filterToRecentPast,
  hourKey,
  mergeGeneratedAndForecast,
  mergeMinuteAheadRows,
  nearestToNow,
  nearestToTimestamp,
  sumForecastAcrossZones,
  sumGeneratedPowerHistoryAcrossZones,
  sumHourlyAcrossZones,
  truncateGeneratedToNow,
  weatherIconFor,
} from '../chartData'
import type { ChartRow } from '../chartData'
import type { ForecastPoint, GeneratedPowerPoint, HourlyPoint } from '../types'

function hourly(hourUtc: number, ac_kw: number, ssrd_w_m2 = 500, temp_c = 30): HourlyPoint {
  return { timestamp: `2026-07-14T${String(hourUtc).padStart(2, '0')}:00:00Z`, ac_kw, ssrd_w_m2, temp_c }
}

function historyPoint(iso: string, ac_kw: number, estimated = false): GeneratedPowerPoint {
  return { timestamp: iso, ac_kw, estimated }
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

describe('filterToRecentPast', () => {
  const now = '2026-07-14T12:00:00Z'

  it('drops points older than the cutoff', () => {
    const points = [{ timestamp: '2026-07-14T11:00:00Z' }, { timestamp: '2026-07-14T11:31:00Z' }]
    expect(filterToRecentPast(points, now, 30).map((p) => p.timestamp)).toEqual(['2026-07-14T11:31:00Z'])
  })

  it('keeps a point exactly at the cutoff', () => {
    const points = [{ timestamp: '2026-07-14T11:30:00Z' }]
    expect(filterToRecentPast(points, now, 30)).toHaveLength(1)
  })

  it('keeps every future point regardless of how far out it reaches', () => {
    const points = [{ timestamp: '2026-07-14T12:00:00Z' }, { timestamp: '2026-07-15T00:00:00Z' }]
    expect(filterToRecentPast(points, now, 30)).toHaveLength(2)
  })
})

describe('mergeGeneratedAndForecast', () => {
  const now = '2026-07-14T13:00:00Z'

  it('outer-joins on hour, filling the missing side with null', () => {
    const rows = mergeGeneratedAndForecast(
      [hourly(10, 20), hourly(11, 30)],
      [forecastPoint(11, 28, 20, 36), forecastPoint(12, 32, 24, 40)],
      [],
      now,
    )

    expect(rows.map((r) => r.key)).toEqual(['2026-07-14T10', '2026-07-14T11', '2026-07-14T12'])
    // hour 11 is the most recent already-happened actual point (<= now) -> "now" tier
    expect(rows[1]).toMatchObject({ actualNow: 30, actualToday: null, actualPast: null, pred: 28, lower: 20, upper: 36, band: 16 })
    // hour 10 is same ICT day but not the most recent -> "today" tier
    expect(rows[0]).toMatchObject({ actualToday: 20, actualNow: null, pred: null })
    // hour 12 has no actual data at all
    expect(rows[2]).toMatchObject({ actualPast: null, actualToday: null, actualNow: null, pred: 32, band: 16 })
  })

  it('sorts chronologically regardless of input order', () => {
    const rows = mergeGeneratedAndForecast([hourly(15, 5), hourly(9, 1)], [], [], now)
    expect(rows.map((r) => r.key)).toEqual(['2026-07-14T09', '2026-07-14T15'])
  })

  it('leaves band null when a forecast point has no PI', () => {
    const rows = mergeGeneratedAndForecast([], [forecastPoint(9, 10)], [], now)
    expect(rows[0]).toMatchObject({ pred: 10, lower: null, upper: null, band: null })
  })

  it('carries algorithm and error through from the forecast point', () => {
    const rows = mergeGeneratedAndForecast([], [forecastPoint(9, 10, 8, 12, 'lightgbm', 3.5)], [], now)
    expect(rows[0]).toMatchObject({ algorithm: 'lightgbm', error: 3.5 })
  })

  it('buckets `history` points from an earlier ICT calendar date as the "past" tier', () => {
    const rows = mergeGeneratedAndForecast([hourly(10, 20)], [], [historyPoint('2026-07-12T10:00:00Z', 15)], now)
    const pastRow = rows.find((r) => r.key === '2026-07-12T10')
    expect(pastRow).toMatchObject({ actualPast: 15, actualToday: null, actualNow: null })
  })

  it('carries the estimated flag through from a `history` point onto the row (2026-07-18 fix: a backfilled "actual" reading must be distinguishable from a live one)', () => {
    const rows = mergeGeneratedAndForecast(
      [],
      [],
      [historyPoint('2026-07-12T10:00:00Z', 15, true), historyPoint('2026-07-12T11:00:00Z', 20, false)],
      now,
    )
    expect(rows.find((r) => r.key === '2026-07-12T10')?.actualEstimated).toBe(true)
    expect(rows.find((r) => r.key === '2026-07-12T11')?.actualEstimated).toBe(false)
  })

  it('picks the single most-recent already-happened point across multiple `history` entries as the "now" tier', () => {
    // No `hourly` data at all here (e.g. before today's first poll) - so
    // the most recent of two *past-day* history points still correctly
    // becomes the "now" tier, proving the comparison is purely
    // chronological, not "today's data always wins".
    const rows = mergeGeneratedAndForecast(
      [],
      [],
      [historyPoint('2026-07-12T10:00:00Z', 15), historyPoint('2026-07-13T10:00:00Z', 25)],
      now,
    )
    expect(rows.find((r) => r.key === '2026-07-13T10')).toMatchObject({ actualNow: 25, actualToday: null, actualPast: null })
    expect(rows.find((r) => r.key === '2026-07-12T10')).toMatchObject({ actualPast: 15, actualNow: null })
  })

  it('uses the ICT (not UTC) calendar date to decide "today" vs "past", per the Thailand-first display convention', () => {
    // 2026-07-14T01:00:00Z is 08:00 ICT on 2026-07-14 - same ICT date as
    // `now` (13:00Z = 20:00 ICT, still 2026-07-14) - a UTC-date comparison
    // would already agree here, so this alone doesn't distinguish the two;
    // paired with the next test below for the boundary case that does.
    // A later `hourly` point (hour 12) claims the "now" tier so this point
    // is free to land on "today" instead of being auto-claimed as "now"
    // for simply being the only actual point in the series.
    const rows = mergeGeneratedAndForecast([hourly(12, 99)], [], [historyPoint('2026-07-14T01:00:00Z', 7)], now)
    expect(rows.find((r) => r.key === '2026-07-14T01')).toMatchObject({ actualToday: 7, actualNow: null, actualPast: null })
  })

  it('treats late-UTC-evening-of-the-previous-day as "today" in ICT (the UTC/ICT boundary case)', () => {
    // 2026-07-13T18:00:00Z is 01:00 ICT on 2026-07-14 - a *different* UTC
    // calendar date (07-13) from `now`'s 07-14, but the *same* ICT date. A
    // naive UTC-date comparison would wrongly bucket this as "past".
    const rows = mergeGeneratedAndForecast([hourly(12, 99)], [], [historyPoint('2026-07-13T18:00:00Z', 9)], now)
    expect(rows.find((r) => r.key === '2026-07-13T18')).toMatchObject({ actualToday: 9, actualPast: null, actualNow: null })
  })
})

describe('truncateGeneratedToNow', () => {
  const now = '2026-07-14T12:00:00Z'

  it('nulls all 3 actual-power tiers for rows after now, leaving forecast fields untouched', () => {
    const rows = mergeGeneratedAndForecast(
      [hourly(11, 20), hourly(13, 30)], // 13:00 is "in the future" relative to `now`
      [forecastPoint(13, 28, 20, 36)],
      [],
      now,
    )
    const truncated = truncateGeneratedToNow(rows, now)
    expect(truncated.find((r) => r.key === '2026-07-14T11')).toMatchObject({ actualNow: 20 })
    expect(truncated.find((r) => r.key === '2026-07-14T13')).toMatchObject({
      actualPast: null,
      actualToday: null,
      actualNow: null,
      pred: 28,
      band: 16,
    })
  })

  it('leaves a row exactly at now untouched (not yet "in the future")', () => {
    const rows = mergeGeneratedAndForecast([hourly(12, 25)], [], [], now)
    const truncated = truncateGeneratedToNow(rows, now)
    expect(truncated[0].actualNow).toBe(25)
  })

  it('defaults to the real current time when no cutoff is passed', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(now))
    const rows = mergeGeneratedAndForecast([hourly(11, 20), hourly(13, 30)], [])
    const truncated = truncateGeneratedToNow(rows)
    expect(truncated.find((r) => r.key === '2026-07-14T11')?.actualNow).toBe(20)
    expect(truncated.find((r) => r.key === '2026-07-14T13')).toMatchObject({ actualPast: null, actualToday: null, actualNow: null })
    vi.useRealTimers()
  })
})

function minutePoint(iso: string, pred: number): ForecastPoint {
  return { timestamp: iso, pred, lower: null, upper: null, algorithm: null, error: null, candidate_errors: null }
}

function actualChartRow(
  iso: string,
  tier: { actualPast?: number; actualToday?: number; actualNow?: number },
): ChartRow {
  return {
    key: iso,
    timestamp: iso,
    actualPast: tier.actualPast ?? null,
    actualToday: tier.actualToday ?? null,
    actualNow: tier.actualNow ?? null,
    actualEstimated: false,
    pred: null,
    lower: null,
    upper: null,
    band: null,
    algorithm: null,
    error: null,
    errorLightgbm: null,
    errorRandomForest: null,
    errorSumKLstm: null,
  }
}

describe('mergeMinuteAheadRows', () => {
  it('merges forecast points and actual-power rows into one array by timestamp', () => {
    const minutePoints = [minutePoint('2026-07-18T12:50:00Z', 10), minutePoint('2026-07-18T13:00:00Z', 12)]
    const actualRows = [actualChartRow('2026-07-18T13:00:00Z', { actualNow: 11 })]
    const rows = mergeMinuteAheadRows(minutePoints, actualRows)

    expect(rows.map((r) => r.timestamp)).toEqual(['2026-07-18T12:50:00Z', '2026-07-18T13:00:00Z'])
    expect(rows[0]).toMatchObject({ pred: 10, actualPast: null, actualToday: null, actualNow: null })
    expect(rows[1]).toMatchObject({ pred: 12, actualNow: 11 })
  })

  it('keeps a timestamp sorted in order even when it only appears in the actual-power rows, not the forecast points (the reported out-of-order x-axis bug)', () => {
    // actualRows reaches an hour (11:00) the forecast's own narrower window
    // doesn't cover at all - this must not land at the end of the sorted
    // output just because it was only "discovered" via the second array.
    const minutePoints = [minutePoint('2026-07-18T12:00:00Z', 5)]
    const actualRows = [actualChartRow('2026-07-18T11:00:00Z', { actualPast: 40 }), actualChartRow('2026-07-18T12:00:00Z', { actualNow: 45 })]
    const rows = mergeMinuteAheadRows(minutePoints, actualRows)

    expect(rows.map((r) => r.timestamp)).toEqual(['2026-07-18T11:00:00Z', '2026-07-18T12:00:00Z'])
  })

  it('returns an empty array when both inputs are empty', () => {
    expect(mergeMinuteAheadRows([], [])).toEqual([])
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

  it('keeps hours reported by only some zones, summing whatever is there (2026-07-18: an earlier version dropped these)', () => {
    const gis = [hourly(12, 40), hourly(13, 45)]
    const isb = [hourly(12, 90)]
    const rows = sumHourlyAcrossZones([gis, isb])
    expect(rows.map((r) => r.timestamp)).toEqual([hourly(12, 0).timestamp, hourly(13, 0).timestamp])
    expect(rows.find((r) => r.timestamp === hourly(13, 0).timestamp)?.ac_kw).toBe(45) // only GIS reported this hour
  })
})

describe('sumGeneratedPowerHistoryAcrossZones', () => {
  it('sums ac_kw across zones for a timestamp every zone reported', () => {
    const gis = [historyPoint('2026-07-12T10:00:00Z', 15)]
    const isb = [historyPoint('2026-07-12T10:00:00Z', 25)]
    const [row] = sumGeneratedPowerHistoryAcrossZones([gis, isb])
    expect(row).toMatchObject({ ac_kw: 40 })
  })

  it('keeps timestamps reported by only some zones, summing whatever is there (2026-07-18: an earlier version dropped these)', () => {
    const gis = [historyPoint('2026-07-12T10:00:00Z', 15), historyPoint('2026-07-12T11:00:00Z', 20)]
    const isb = [historyPoint('2026-07-12T10:00:00Z', 25)]
    const rows = sumGeneratedPowerHistoryAcrossZones([gis, isb])
    expect(rows.map((r) => r.timestamp)).toEqual(['2026-07-12T10:00:00Z', '2026-07-12T11:00:00Z'])
    expect(rows.find((r) => r.timestamp === '2026-07-12T11:00:00Z')?.ac_kw).toBe(20) // only GIS reported this hour
  })

  it('marks the summed row estimated if any contributing zone was estimated', () => {
    const gis = [historyPoint('2026-07-12T10:00:00Z', 15, true)]
    const isb = [historyPoint('2026-07-12T10:00:00Z', 25, false)]
    const [row] = sumGeneratedPowerHistoryAcrossZones([gis, isb])
    expect(row.estimated).toBe(true)
  })

  it('leaves the summed row not estimated when every contributing zone is live', () => {
    const gis = [historyPoint('2026-07-12T10:00:00Z', 15, false)]
    const isb = [historyPoint('2026-07-12T10:00:00Z', 25, false)]
    const [row] = sumGeneratedPowerHistoryAcrossZones([gis, isb])
    expect(row.estimated).toBe(false)
  })
})

describe('sumForecastAcrossZones', () => {
  it('keeps hours reported by only some zones, summing whatever is there (2026-07-18: an earlier version dropped these - the reported "Model Competition chart empty" bug)', () => {
    const gis = [forecastPoint(12, 10, 8, 12)]
    const isb = [forecastPoint(12, 20, 16, 24)]
    const jetty = [forecastPoint(13, 5, 4, 6)] // different hour - kept on its own, not merged with hour 12
    const rows = sumForecastAcrossZones([gis, isb, jetty])
    expect(rows).toHaveLength(2)
    expect(rows.find((r) => r.timestamp === forecastPoint(12, 0, 0, 0).timestamp)?.pred).toBe(30) // gis + isb only
    expect(rows.find((r) => r.timestamp === forecastPoint(13, 0, 0, 0).timestamp)?.pred).toBe(5) // jetty only
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

  it('drops any already-passed point (only the live k-step race, not accumulated history)', () => {
    const stale = forecastPoint(9, 10, null, null, 'lightgbm', 1, { lightgbm: 1 })
    const live = forecastPoint(13, 40, null, null, 'lightgbm', 1.2, { lightgbm: 1.2 })
    const rows = buildCompetitionRows([stale, live], nowIso)
    expect(rows).toHaveLength(1)
    expect(rows[0].leadLabel).toBe('+1h')
  })

  it('drops an already-passed point even within the last hour, instead of admitting it and bumping a real +6h point out of the 6-row cap', () => {
    // Found live 2026-07-18: an earlier version filtered `>= nowMs - 1h`, so
    // an hour that had *just* passed (here, 11:00 - one hour before
    // nowIso=12:00) - already aged out of live k-step coverage, so
    // algorithm/candidate_errors are back to their "nothing here" defaults,
    // same as any other already-passed hour - sorted ahead of the real
    // +1h..+6h race, got mislabeled "+1h" with every bar null, and pushed
    // the genuine +6h point out of `.slice(0, 6)`. That's exactly what the
    // reported "empty Model Competition chart" screenshot showed.
    const staleWithinLastHour = forecastPoint(11, 30, null, null, null, null, {})
    const live = Array.from({ length: 6 }, (_, i) => forecastPoint(13 + i, 40, null, null, 'lightgbm', 1, { lightgbm: 1 }))
    const rows = buildCompetitionRows([staleWithinLastHour, ...live], nowIso)
    expect(rows).toHaveLength(6)
    expect(rows.every((r) => r.lightgbm === 1)).toBe(true)
    expect(rows[0].leadLabel).toBe('+1h')
    expect(rows[5].leadLabel).toBe('+6h')
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
