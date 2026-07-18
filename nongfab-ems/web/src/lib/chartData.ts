import type { ForecastPoint, HourlyPoint } from './types'

export interface ChartRow {
  key: string
  timestamp: string
  generated: number | null
  pred: number | null
  lower: number | null
  upper: number | null
  band: number | null
  algorithm: string | null
  error: number | null
  // Every hour-ahead candidate's own RMSE, flattened out of
  // ForecastPoint.candidate_errors into one Recharts-friendly numeric field
  // per model (added 2026-07-18, replacing the single winner-only `error`
  // line on the main chart) - null wherever that candidate didn't compete
  // that lead hour (e.g. sum_k_lstm failed to train) or the point predates
  // this field. Flat fields rather than a nested object so each becomes its
  // own <Line dataKey=...> without relying on Recharts' dot-path lookup.
  errorLightgbm: number | null
  errorRandomForest: number | null
  errorSumKLstm: number | null
}

/** Buckets by hour (not exact timestamp): independent backend calls for
 * different zones each stamp "now" a few seconds apart, and every series
 * involved here (today's synthetic baseline, the day/hour-ahead forecast
 * models) runs on an hourly cadence anyway, so hour buckets absorb that
 * jitter without losing any real precision. */
export function hourKey(iso: string): string {
  return iso.slice(0, 13) // "2026-07-14T12:00:00Z" -> "2026-07-14T12"
}

/** Groups by the exact timestamp, not the hour it falls in - the bucket key
 * `sumForecastAcrossZones` needs for minute-ahead's "All" (รวม) zone
 * aggregation. Minute-ahead points are 10-minute resolution (up to 6 points
 * inside one 60-minute window), so several of them routinely share the same
 * *hour* - `hourKey`'s hour-only granularity was silently collapsing that
 * window's points into 1-2 buckets whose per-zone counts stopped matching
 * `perZone.length`, dropping all but (at most) one point (found live
 * 2026-07-17: the "All" zone's Minute-ahead panel rendered a single dot
 * instead of a connected 6-point line, while GIS/ISB/Jetty individually
 * rendered correctly - those don't go through this aggregator at all, see
 * ForecastPage.tsx). All 3 zones' own minute-ahead requests round their
 * timestamps to the same 10-minute anchor (forecast/serving.py's
 * `_ceil_to`), so they line up exactly under normal conditions; only a
 * request that happens to straddle the exact 10-minute boundary against the
 * others could still miss a match here - self-correcting on the next 60s
 * poll, not worth a more complex reconciliation for. */
export function exactTimeKey(iso: string): string {
  return iso
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
    rows.set(key, {
      key,
      timestamp: point.timestamp,
      generated: point.ac_kw,
      pred: null,
      lower: null,
      upper: null,
      band: null,
      algorithm: null,
      error: null,
      errorLightgbm: null,
      errorRandomForest: null,
      errorSumKLstm: null,
    })
  }

  for (const point of forecastPoints) {
    const key = hourKey(point.timestamp)
    const band = point.lower != null && point.upper != null ? point.upper - point.lower : null
    const errorLightgbm = point.candidate_errors?.lightgbm ?? null
    const errorRandomForest = point.candidate_errors?.random_forest ?? null
    const errorSumKLstm = point.candidate_errors?.sum_k_lstm ?? null
    const existing = rows.get(key)
    if (existing) {
      existing.pred = point.pred
      existing.lower = point.lower
      existing.upper = point.upper
      existing.band = band
      existing.algorithm = point.algorithm
      existing.error = point.error
      existing.errorLightgbm = errorLightgbm
      existing.errorRandomForest = errorRandomForest
      existing.errorSumKLstm = errorSumKLstm
    } else {
      rows.set(key, {
        key,
        timestamp: point.timestamp,
        generated: null,
        pred: point.pred,
        lower: point.lower,
        upper: point.upper,
        band,
        algorithm: point.algorithm,
        error: point.error,
        errorLightgbm,
        errorRandomForest,
        errorSumKLstm,
      })
    }
  }

  return [...rows.values()].sort((a, b) => a.key.localeCompare(b.key))
}

/** Nulls out `generated` (actual/baseline power) for any row whose timestamp
 * is later than `nowIso` - `hourly`'s underlying series is a full synthetic
 * *today* (see mergeGeneratedAndForecast's own docstring above), so without
 * this a chart opened at, say, 08:45 would already show bars out to 17:00
 * that haven't happened yet, making a series meant to read as "what was
 * actually produced" look like it was itself a forecast (found live
 * 2026-07-17, across all/GIS/ISB/Jetty alike). Only `generated` is touched -
 * `pred`/`lower`/`upper`/`band` are left alone, since the forecast line is
 * *supposed* to extend into the future. `nowIso` defaults to the real
 * current time but is a parameter so tests don't depend on wall-clock time. */
export function truncateGeneratedToNow(rows: ChartRow[], nowIso: string = new Date().toISOString()): ChartRow[] {
  const nowMs = new Date(nowIso).getTime()
  return rows.map((row) => (new Date(row.timestamp).getTime() > nowMs ? { ...row, generated: null } : row))
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

/** `algorithm` is deliberately dropped (set to null) for the aggregate: each
 * zone's hour-ahead auto-select can pick a different winner independently, so
 * there is no single "the" algorithm to report for a summed "All" (รวม)
 * point - the dot-coloring feature is only meaningful per-zone. `error`
 * (RMSE, roughly extensive like lower/upper) is summed the same
 * approximate way lower/upper already are.
 *
 * `keyFn` defaults to `hourKey` (correct for Day-ahead/Intra-day's hourly
 * cadence, where it also absorbs a few seconds of cross-zone request jitter)
 * - callers aggregating a finer-resolution series (minute-ahead) must pass
 * `exactTimeKey` instead, see that function's own docstring. */
export function sumForecastAcrossZones(perZone: ForecastPoint[][], keyFn: (iso: string) => string = hourKey): ForecastPoint[] {
  const acc = new Map<
    string,
    { timestamp: string; pred: number; lower: number; upper: number; error: number; candidateErrors: Record<string, number>; n: number }
  >()
  for (const series of perZone) {
    for (const point of series) {
      const key = keyFn(point.timestamp)
      const entry = acc.get(key) ?? { timestamp: point.timestamp, pred: 0, lower: 0, upper: 0, error: 0, candidateErrors: {}, n: 0 }
      entry.pred += point.pred
      entry.lower += point.lower ?? point.pred
      entry.upper += point.upper ?? point.pred
      entry.error += point.error ?? 0
      // Summed the same approximate "roughly extensive" way `error` above
      // already is - each zone's per-candidate RMSE is its own independent
      // measurement, not a value that averages meaningfully, but a sum still
      // lets the "All" (รวม) competition panel show relative model ranking
      // across the whole site rather than going blank for it.
      for (const [algo, rmse] of Object.entries(point.candidate_errors ?? {})) {
        entry.candidateErrors[algo] = (entry.candidateErrors[algo] ?? 0) + rmse
      }
      entry.n += 1
      acc.set(key, entry)
    }
  }
  return [...acc.values()]
    .filter((entry) => entry.n === perZone.length)
    .map((entry) => ({
      timestamp: entry.timestamp,
      pred: entry.pred,
      lower: entry.lower,
      upper: entry.upper,
      algorithm: null,
      error: entry.error,
      candidate_errors: entry.candidateErrors,
    }))
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
}

export interface CompetitionRow {
  key: string
  timestamp: string
  // "+1h".."+6h" - HourAheadKStepModel always trains HOUR_LEAD_HOURS = 1..6,
  // and rows here are already sorted ascending by timestamp, so index+1 is
  // exactly that model's own lead hour without needing to recompute an
  // offset from `timestamp` (which would need a clock and a "now" anchor
  // this function otherwise has no reason to take a dependency on).
  leadLabel: string
  winner: string | null
  lightgbm: number | null
  randomForest: number | null
  sumKLstm: number | null
  // max - min across whichever candidates competed that lead hour - a cheap
  // "how much did the model choice actually matter here" signal (added
  // 2026-07-18 per the user's own suggestion of an inter-model comparison
  // metric, alongside RMSE-vs-actual): a small spread means all candidates
  // were close, so the auto-select winner barely outperformed the
  // alternatives; a large spread means the winner meaningfully beat the
  // others. This is still a *validation-time* comparison (computed from the
  // same held-out RMSE candidate_errors already carries), not a live
  // prediction-disagreement/ensemble-spread metric - see ForecastPage.tsx's
  // ViewerGuidePanel for why the richer live version isn't built here (it
  // would need every losing candidate's trained model kept around for
  // inference, not just its validation score - a materially bigger backend
  // change than this session's other additions). null if fewer than 2
  // candidates have a recorded RMSE for that lead hour.
  spread: number | null
}

/** Builds the Model Competition panel's rows straight from hour-ahead
 * ForecastPoints - one row per lead hour, all three candidates' own RMSE
 * side by side plus which one actually won (`winner`, from `algorithm`).
 * Only points at/after `nowIso` are kept (a live k-step forecast's 6 lead
 * hours), then capped to 6: `points` may also carry accumulated *past*
 * history (server-side forecast_history persistence, see serving.py) mixed
 * into the same array by the caller's existing per-poll accumulation - that
 * history is exactly what the main chart's error lines want to show over
 * time, but this panel is "right now's competition", not a timeline. */
export function buildCompetitionRows(points: ForecastPoint[], nowIso: string = new Date().toISOString()): CompetitionRow[] {
  const nowMs = new Date(nowIso).getTime()
  return points
    .filter((p) => new Date(p.timestamp).getTime() >= nowMs - 60 * 60 * 1000)
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
    .slice(0, 6)
    .map((p, i) => {
      const values = Object.values(p.candidate_errors ?? {})
      return {
        key: p.timestamp,
        timestamp: p.timestamp,
        leadLabel: `+${i + 1}h`,
        winner: p.algorithm,
        lightgbm: p.candidate_errors?.lightgbm ?? null,
        randomForest: p.candidate_errors?.random_forest ?? null,
        sumKLstm: p.candidate_errors?.sum_k_lstm ?? null,
        spread: values.length >= 2 ? Math.max(...values) - Math.min(...values) : null,
      }
    })
}

/** The point (of any series carrying a `timestamp`) whose timestamp is
 * closest to `targetIso` - same "pick the nearest row" idea as the
 * backend's /ws/live snapshot (there is no single "current" row otherwise,
 * since a series like `hourly` is a full synthetic day). Used both for
 * "nearest to right now" (`nearestToNow`) and, for the 3D page's sun-path
 * scrub (Feature C tied to Feature A - see Solar3DPage.tsx), "nearest to
 * the scrubbed time", which is deliberately NOT always "now". */
export function nearestToTimestamp<T extends { timestamp: string }>(points: T[], targetIso: string): T | undefined {
  if (points.length === 0) return undefined
  const target = new Date(targetIso).getTime()
  return points.reduce((closest, point) =>
    Math.abs(new Date(point.timestamp).getTime() - target) < Math.abs(new Date(closest.timestamp).getTime() - target)
      ? point
      : closest,
  )
}

/** The hourly point whose timestamp is closest to right now. */
export function nearestToNow(hourly: HourlyPoint[]): HourlyPoint | undefined {
  return nearestToTimestamp(hourly, new Date().toISOString())
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
