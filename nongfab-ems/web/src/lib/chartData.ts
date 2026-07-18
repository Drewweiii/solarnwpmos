import { ictDateKey } from './timeScrub'
import type { ForecastPoint, GeneratedPowerPoint, HourlyPoint } from './types'

export interface ChartRow {
  key: string
  timestamp: string
  // Actual/generated power, split into 3 recency tiers (2026-07-18, replacing
  // the single `generated` field) so a viewer can tell at a glance how old a
  // given reading is without having to read the x-axis - added because a
  // single purple bar/line for "everything real" was hard to compare against
  // the blue Forecast line at a glance (the user's own report). Exactly one
  // of these three is non-null for any given already-happened timestamp -
  // see mergeGeneratedAndForecast's own docstring for the exact boundary
  // rules. All three are null for a future timestamp (not yet happened).
  actualPast: number | null // previous days (not today, ICT calendar date)
  actualToday: number | null // today (ICT), but strictly before `actualNow`'s point
  actualNow: number | null // the single most recent already-happened reading
  // True when whichever of the 3 actual-power tiers above is set came from a
  // cold-start-backfilled physics estimate (GeneratedPowerPoint.estimated),
  // not a genuinely live-polled reading - see that type's own docstring for
  // why this matters. False (not just absent) when no actual reading exists
  // for this row at all, same as the 3 tiers themselves default to null
  // rather than undefined.
  actualEstimated: boolean
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

/** Keeps only points from `minutesBack` minutes before `nowIso` onward - no
 * upper bound, so future points (a forward-looking forecast) are always
 * kept regardless of how far out they reach. Used to bound `
 * useForecastHistory`'s otherwise-unbounded client-side accumulation
 * (2026-07-18) for the Minute-ahead panel, which only wants a short
 * trailing window ("ย้อนหลังซัก 30 นาที" - about 30 min back, per the
 * user's own request), not the panel's entire accumulated session
 * history. */
export function filterToRecentPast<T extends { timestamp: string }>(points: T[], nowIso: string, minutesBack: number): T[] {
  const cutoffMs = new Date(nowIso).getTime() - minutesBack * 60 * 1000
  return points.filter((p) => new Date(p.timestamp).getTime() >= cutoffMs)
}

function emptyChartRow(key: string, timestamp: string): ChartRow {
  return {
    key,
    timestamp,
    actualPast: null,
    actualToday: null,
    actualNow: null,
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

/** Outer-joins actual/generated power (today's `hourly` from /performance,
 * plus `history` - persisted actual power for *previous* days, 2026-07-18)
 * with "forecast" (from /forecast) on their hour bucket. The series can have
 * different, only partially overlapping time ranges (a day-ahead forecast
 * rolls forward from "now", today's baseline is calendar-aligned) - this
 * keeps every hour either side reported, with the other side's fields left
 * null rather than forcing a false alignment.
 *
 * Actual/generated power is split into 3 recency tiers rather than one flat
 * `generated` value (see ChartRow's own docstring for why): the single
 * already-happened point closest to `nowIso` is `actualNow`; every other
 * already-happened point on the same ICT calendar date as `nowIso` is
 * `actualToday`; every already-happened point on an earlier ICT date is
 * `actualPast`. A point later than `nowIso` (hasn't happened yet) gets none
 * of the three here - `truncateGeneratedToNow` below is what actually
 * enforces that boundary for `hourly`'s own future-dated entries (this
 * function's own tier assignment would otherwise still bucket them as
 * "today" purely by calendar date, same reasoning `truncateGeneratedToNow`
 * already documented for the old single-field version). */
export function mergeGeneratedAndForecast(
  hourly: HourlyPoint[],
  forecastPoints: ForecastPoint[],
  history: GeneratedPowerPoint[] = [],
  nowIso: string = new Date().toISOString(),
): ChartRow[] {
  const rows = new Map<string, ChartRow>()
  const nowMs = new Date(nowIso).getTime()
  const nowDateKey = ictDateKey(nowIso)

  const allActual = [...history, ...hourly].filter((p) => new Date(p.timestamp).getTime() <= nowMs)
  const mostRecentTimestamp = allActual.reduce<string | null>(
    (latest, p) => (latest == null || new Date(p.timestamp).getTime() > new Date(latest).getTime() ? p.timestamp : latest),
    null,
  )

  function assignActualTier(row: ChartRow, timestamp: string, ac_kw: number) {
    if (timestamp === mostRecentTimestamp) row.actualNow = ac_kw
    else if (ictDateKey(timestamp) === nowDateKey) row.actualToday = ac_kw
    else row.actualPast = ac_kw
  }

  for (const point of history) {
    const key = hourKey(point.timestamp)
    const row = rows.get(key) ?? emptyChartRow(key, point.timestamp)
    assignActualTier(row, point.timestamp, point.ac_kw)
    row.actualEstimated = point.estimated
    rows.set(key, row)
  }

  for (const point of hourly) {
    const key = hourKey(point.timestamp)
    const row = rows.get(key) ?? emptyChartRow(key, point.timestamp)
    assignActualTier(row, point.timestamp, point.ac_kw)
    rows.set(key, row)
  }

  for (const point of forecastPoints) {
    const key = hourKey(point.timestamp)
    const band = point.lower != null && point.upper != null ? point.upper - point.lower : null
    const row = rows.get(key) ?? emptyChartRow(key, point.timestamp)
    row.pred = point.pred
    row.lower = point.lower
    row.upper = point.upper
    row.band = band
    row.algorithm = point.algorithm
    row.error = point.error
    row.errorLightgbm = point.candidate_errors?.lightgbm ?? null
    row.errorRandomForest = point.candidate_errors?.random_forest ?? null
    row.errorSumKLstm = point.candidate_errors?.sum_k_lstm ?? null
    rows.set(key, row)
  }

  return [...rows.values()].sort((a, b) => a.key.localeCompare(b.key))
}

export interface MinuteChartRow {
  key: string
  timestamp: string
  pred: number | null
  actualPast: number | null
  actualToday: number | null
  actualNow: number | null
}

/** Merges the Minute-ahead panel's forecast points (10-minute resolution)
 * and its actual-power overlay (`ChartRow[]`, hourly resolution, a wider
 * window than the forecast's own - see ForecastPage.tsx's
 * `minuteWindowActualRows` docstring) into ONE time-sorted array, rather
 * than the panel handing Recharts two independently-shaped arrays via
 * separate per-`<Line data=...>` props on a shared categorical XAxis.
 *
 * That separate-arrays approach is a real Recharts footgun, not just a
 * style preference: a categorical XAxis's tick domain is the union of every
 * series' own category values, appended in first-encountered order, NOT
 * re-sorted by value - so a timestamp that only appears in the *second*
 * series (the wider actual-power window reaching an hour outside the
 * forecast's own narrower span) lands at the *end* of the axis regardless
 * of its real time value. Found live 2026-07-18 as the reported "the x-axis
 * shows 20:00..20:50 then 19:00 out of order" bug. A single shared, sorted
 * array is exactly the pattern the main chart's own `ChartRow`/
 * `mergeGeneratedAndForecast` already uses for the same reason - this
 * mirrors it for the Minute-ahead panel specifically. */
export function mergeMinuteAheadRows(minutePoints: ForecastPoint[], actualRows: ChartRow[]): MinuteChartRow[] {
  const rows = new Map<string, MinuteChartRow>()
  for (const row of actualRows) {
    rows.set(row.timestamp, {
      key: row.timestamp,
      timestamp: row.timestamp,
      pred: null,
      actualPast: row.actualPast,
      actualToday: row.actualToday,
      actualNow: row.actualNow,
    })
  }
  for (const point of minutePoints) {
    const existing = rows.get(point.timestamp)
    if (existing) existing.pred = point.pred
    else rows.set(point.timestamp, { key: point.timestamp, timestamp: point.timestamp, pred: point.pred, actualPast: null, actualToday: null, actualNow: null })
  }
  return [...rows.values()].sort((a, b) => a.timestamp.localeCompare(b.timestamp))
}

/** Nulls out the 3 actual-power tiers (`actualPast`/`actualToday`/
 * `actualNow`) for any row whose timestamp is later than `nowIso` -
 * `hourly`'s underlying series is a full synthetic *today* (see
 * mergeGeneratedAndForecast's own docstring above), so without this a chart
 * opened at, say, 08:45 would already show data out to 17:00 that hasn't
 * happened yet, making a series meant to read as "what was actually
 * produced" look like it was itself a forecast (found live 2026-07-17,
 * across all/GIS/ISB/Jetty alike, back when this was a single `generated`
 * field). Only the 3 actual-power fields are touched - `pred`/`lower`/
 * `upper`/`band` are left alone, since the forecast line is *supposed* to
 * extend into the future. `nowIso` defaults to the real current time but is
 * a parameter so tests don't depend on wall-clock time. */
export function truncateGeneratedToNow(rows: ChartRow[], nowIso: string = new Date().toISOString()): ChartRow[] {
  const nowMs = new Date(nowIso).getTime()
  return rows.map((row) =>
    new Date(row.timestamp).getTime() > nowMs ? { ...row, actualPast: null, actualToday: null, actualNow: null } : row,
  )
}

/** Site-wide aggregate for the "All" (รวม) zone selection: power (ac_kw) is
 * extensive and sums across zones; irradiance/temperature are intensive
 * (site-wide averages across however many zones reported, via `entry.n`).
 *
 * Sums whatever zones *did* report for an hour, rather than requiring every
 * zone to agree on that exact hour first - an earlier version required
 * `entry.n === perZone.length`, which meant a single zone's request landing
 * a few hundred ms on the other side of an hour boundary from the other two
 * (three independent network calls, each computing its own "ceil to next
 * hour" anchor server-side - see forecast/serving.py's `_ceil_to`) silently
 * dropped that *entire* hour from the "All" aggregate, not just that one
 * zone's contribution - found live 2026-07-18 as the reported "Model
 * Competition chart / Minute-ahead actual-power lines show nothing at all"
 * (this same aggregation pattern also feeds `hourly`, which the Minute-ahead
 * panel's actual-power overlay depends on). A partial-zone sum that
 * undercounts by one zone for a transient moment is a more honest, more
 * useful result than blanking the entire chart over it - this mismatch
 * self-corrects on the very next poll under normal operation. */
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
    .map((entry) => ({ timestamp: entry.timestamp, ac_kw: entry.ac_kw, ssrd_w_m2: entry.ssrd_w_m2 / entry.n, temp_c: entry.temp_c / entry.n }))
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
}

/** Same "All" (รวม) aggregation as `sumHourlyAcrossZones` above, for
 * `/performance`'s `history` field (persisted actual/generated power for
 * previous days, 2026-07-18) instead of `hourly` - sums across zones,
 * tolerating partial coverage the same way and for the same reason (see
 * `sumHourlyAcrossZones`'s own docstring). `estimated` is true for the
 * summed row if *any* contributing zone's own reading was a backfilled
 * estimate (see GeneratedPowerPoint.estimated's own docstring) - a sum with
 * even one estimated component isn't a fully-live reading either. */
export function sumGeneratedPowerHistoryAcrossZones(perZone: GeneratedPowerPoint[][]): GeneratedPowerPoint[] {
  const acc = new Map<string, { timestamp: string; ac_kw: number; estimated: boolean; n: number }>()
  for (const series of perZone) {
    for (const point of series) {
      const key = hourKey(point.timestamp)
      const entry = acc.get(key) ?? { timestamp: point.timestamp, ac_kw: 0, estimated: false, n: 0 }
      entry.ac_kw += point.ac_kw
      entry.estimated = entry.estimated || point.estimated
      entry.n += 1
      acc.set(key, entry)
    }
  }
  return [...acc.values()]
    .map((entry) => ({ timestamp: entry.timestamp, ac_kw: entry.ac_kw, estimated: entry.estimated }))
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
 * `exactTimeKey` instead, see that function's own docstring.
 *
 * Tolerates partial zone coverage per hour (sums whatever zones reported,
 * doesn't require every zone to agree on that exact hour first) - same fix
 * and same reasoning as `sumHourlyAcrossZones`'s own docstring: an earlier
 * strict `entry.n === perZone.length` requirement meant one zone's request
 * landing on the other side of an hour boundary from the others (three
 * independent network calls, see `sumHourlyAcrossZones`) silently dropped
 * *every* row, not just that zone's share - found live 2026-07-18 as the
 * reported "Model Competition chart shows nothing at all" for the default
 * "All zones" view. */
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
 * time, but this panel is "right now's competition", not a timeline.
 *
 * Strictly `>= nowMs`, no grace window: an earlier version subtracted 1h
 * here, which let an already-passed hour (persisted with `algorithm=null`/
 * `candidate_errors={}` once it ages out of the live forward window) sort
 * ahead of the real k-step points, get mislabeled "+1h", and bump a genuine
 * +6h point out of the `.slice(0, 6)` cap - found live 2026-07-18 as the
 * reported "empty Model Competition chart" (every bar null for that
 * mislabeled row, and a real column silently missing). */
export function buildCompetitionRows(points: ForecastPoint[], nowIso: string = new Date().toISOString()): CompetitionRow[] {
  const nowMs = new Date(nowIso).getTime()
  return points
    .filter((p) => new Date(p.timestamp).getTime() >= nowMs)
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
