import type { ForecastPoint, HourlyPoint } from './types'

export interface ChartRow {
  key: string
  timestamp: string
  generated: number | null
  pred: number | null
  lower: number | null
  upper: number | null
  band: number | null
}

/** Buckets by hour (not exact timestamp): independent backend calls for
 * different zones each stamp "now" a few seconds apart, and every series
 * involved here (today's synthetic baseline, the day/hour-ahead forecast
 * models) runs on an hourly cadence anyway, so hour buckets absorb that
 * jitter without losing any real precision. */
export function hourKey(iso: string): string {
  return iso.slice(0, 13) // "2026-07-14T12:00:00Z" -> "2026-07-14T12"
}

/** Outer-joins "generated" (today's actual/baseline power, from
 * /performance's hourly series) with "forecast" (from /forecast) on their
 * hour bucket. The two series can have different, only partially
 * overlapping time ranges (a day-ahead forecast rolls forward from "now",
 * today's baseline is calendar-aligned) - this keeps every hour either side
 * reported, with the other side's fields left null rather than forcing a
 * false alignment. */
export function mergeGeneratedAndForecast(hourly: HourlyPoint[], forecastPoints: ForecastPoint[]): ChartRow[] {
  const rows = new Map<string, ChartRow>()

  for (const point of hourly) {
    const key = hourKey(point.timestamp)
    rows.set(key, { key, timestamp: point.timestamp, generated: point.ac_kw, pred: null, lower: null, upper: null, band: null })
  }

  for (const point of forecastPoints) {
    const key = hourKey(point.timestamp)
    const band = point.lower != null && point.upper != null ? point.upper - point.lower : null
    const existing = rows.get(key)
    if (existing) {
      existing.pred = point.pred
      existing.lower = point.lower
      existing.upper = point.upper
      existing.band = band
    } else {
      rows.set(key, { key, timestamp: point.timestamp, generated: null, pred: point.pred, lower: point.lower, upper: point.upper, band })
    }
  }

  return [...rows.values()].sort((a, b) => a.key.localeCompare(b.key))
}

/** Site-wide aggregate for the "All" (รวม) zone selection: power (ac_kw) is
 * extensive and sums across zones; irradiance/temperature are intensive
 * (site-wide averages, not sums). Only produces a hour where every zone
 * reported a value, so a zone with no data yet doesn't silently deflate the
 * total instead of just being absent. */
export function sumHourlyAcrossZones(perZone: HourlyPoint[][]): HourlyPoint[] {
  const acc = new Map<string, { timestamp: string; ac_kw: number; ssrd_w_m2: number; temp_c: number; n: number }>()
  for (const series of perZone) {
    for (const point of series) {
      const key = hourKey(point.timestamp)
      const entry = acc.get(key) ?? { timestamp: point.timestamp, ac_kw: 0, ssrd_w_m2: 0, temp_c: 0, n: 0 }
      entry.ac_kw += point.ac_kw
      entry.ssrd_w_m2 += point.ssrd_w_m2
      entry.temp_c += point.temp_c
      entry.n += 1
      acc.set(key, entry)
    }
  }
  return [...acc.values()]
    .filter((entry) => entry.n === perZone.length)
    .map((entry) => ({ timestamp: entry.timestamp, ac_kw: entry.ac_kw, ssrd_w_m2: entry.ssrd_w_m2 / entry.n, temp_c: entry.temp_c / entry.n }))
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
}

export function sumForecastAcrossZones(perZone: ForecastPoint[][]): ForecastPoint[] {
  const acc = new Map<string, { timestamp: string; pred: number; lower: number; upper: number; n: number }>()
  for (const series of perZone) {
    for (const point of series) {
      const key = hourKey(point.timestamp)
      const entry = acc.get(key) ?? { timestamp: point.timestamp, pred: 0, lower: 0, upper: 0, n: 0 }
      entry.pred += point.pred
      entry.lower += point.lower ?? point.pred
      entry.upper += point.upper ?? point.pred
      entry.n += 1
      acc.set(key, entry)
    }
  }
  return [...acc.values()]
    .filter((entry) => entry.n === perZone.length)
    .map((entry) => ({ timestamp: entry.timestamp, pred: entry.pred, lower: entry.lower, upper: entry.upper }))
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
}

/** The hourly point whose timestamp is closest to right now - same "pick
 * the nearest row" idea as the backend's /ws/live snapshot (there is no
 * single "current" row otherwise, since `hourly` is a full synthetic day). */
export function nearestToNow(hourly: HourlyPoint[]): HourlyPoint | undefined {
  if (hourly.length === 0) return undefined
  const now = Date.now()
  return hourly.reduce((closest, point) =>
    Math.abs(new Date(point.timestamp).getTime() - now) < Math.abs(new Date(closest.timestamp).getTime() - now) ? point : closest,
  )
}

export type WeatherIcon = 'sun' | 'partly-cloudy' | 'cloudy' | 'night'

export function weatherIconFor(ssrdWm2: number): WeatherIcon {
  if (ssrdWm2 <= 0) return 'night'
  if (ssrdWm2 > 700) return 'sun'
  if (ssrdWm2 > 300) return 'partly-cloudy'
  return 'cloudy'
}

export const WEATHER_ICON_GLYPH: Record<WeatherIcon, string> = {
  sun: '☀️',
  'partly-cloudy': '⛅',
  cloudy: '☁️',
  night: '🌙',
}

/** Picks the hourly points nearest each of the given target hours-of-day
 * (e.g. [6, 9, 12, 15]) for the weather strip - `hourly` is a full
 * synthetic today, always at hourly resolution, so an exact match exists
 * for every whole-number target hour. */
export function pickHoursOfDay(hourly: HourlyPoint[], targetHours: number[]): HourlyPoint[] {
  return targetHours
    .map((target) => hourly.find((point) => new Date(point.timestamp).getUTCHours() === target))
    .filter((point): point is HourlyPoint => point !== undefined)
}
