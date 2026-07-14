import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  hourKey,
  mergeGeneratedAndForecast,
  nearestToNow,
  pickHoursOfDay,
  sumForecastAcrossZones,
  sumHourlyAcrossZones,
  weatherIconFor,
} from '../chartData'
import type { ForecastPoint, HourlyPoint } from '../types'

function hourly(hourUtc: number, ac_kw: number, ssrd_w_m2 = 500, temp_c = 30): HourlyPoint {
  return { timestamp: `2026-07-14T${String(hourUtc).padStart(2, '0')}:00:00Z`, ac_kw, ssrd_w_m2, temp_c }
}

function forecastPoint(hourUtc: number, pred: number, lower: number | null = null, upper: number | null = null): ForecastPoint {
  return { timestamp: `2026-07-14T${String(hourUtc).padStart(2, '0')}:00:00Z`, pred, lower, upper }
}

describe('hourKey', () => {
  it('buckets timestamps a few seconds apart into the same key', () => {
    expect(hourKey('2026-07-14T12:00:03Z')).toBe(hourKey('2026-07-14T12:00:57Z'))
  })

  it('keeps different hours distinct', () => {
    expect(hourKey('2026-07-14T12:00:00Z')).not.toBe(hourKey('2026-07-14T13:00:00Z'))
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

describe('pickHoursOfDay', () => {
  it('returns points matching each requested UTC hour, skipping missing ones', () => {
    const points = [hourly(6, 1), hourly(9, 2), hourly(15, 4)]
    const picked = pickHoursOfDay(points, [6, 9, 12, 15])
    expect(picked.map((p) => new Date(p.timestamp).getUTCHours())).toEqual([6, 9, 15])
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
