import type { ForecastPoint } from './types'
import { ictDateKey } from './timeScrub'

/** Headline numbers about the FORECAST, for the big-number block (2026-07-25).
 *
 * The page already had a `kpi-row`, but all four of its tiles describe the
 * plant right now - capacity, energy so far, current power, plant factor.
 * Nothing in it says anything about what the forecast is predicting, which is
 * the one thing this page exists for. These are the numbers a viewer actually
 * wants at a glance: how much, when the peak lands, how sure the model is, and
 * how long the array will be producing.
 *
 * Everything here is derived from the forecast series the page has already
 * fetched - no new endpoint, no new model. Deliberately pure so the arithmetic
 * (which is where an energy figure goes quietly wrong) is unit-testable.
 */

/** A forecast hour counts as "producing" above this fraction of the day's own
 * peak. Relative rather than an absolute kW floor so it means the same thing
 * for GIS (50 kW) and Jetty (200 kW), and so it survives a change of zone or
 * of season without being retuned. */
const PRODUCTIVE_FRACTION_OF_PEAK = 0.05

export interface ForecastKpi {
  /** Energy over the window. null when the window holds no points at all -
   * an honest "nothing to say" rather than a confident 0 kWh. */
  energyKwh: number | null
  peakKw: number | null
  peakAtIso: string | null
  /** Half-width of the prediction interval at the peak hour, in kW and as a
   * percentage of the predicted value. Null when the model published no
   * interval (the physics-baseline fallback does not) - and null is the point:
   * "no interval" must not render as "±0", which reads as certainty. */
  bandKw: number | null
  bandPct: number | null
  /** Hours the array is expected to be producing, at the series' own
   * resolution. */
  productiveHours: number | null
  /** How many forecast points the window actually contained. Surfaced so a
   * figure computed from two points can be told apart from one computed from a
   * full day. */
  pointCount: number
  /** Hours between consecutive samples, inferred from the data rather than
   * assumed - it is what turns kW into kWh, so a wrong guess here silently
   * scales the headline energy figure. */
  stepHours: number
}

export const EMPTY_KPI: ForecastKpi = {
  energyKwh: null,
  peakKw: null,
  peakAtIso: null,
  bandKw: null,
  bandPct: null,
  productiveHours: null,
  pointCount: 0,
  stepHours: 0,
}

/** Median gap between consecutive samples, in hours.
 *
 * Median, not mean: a forecast series can have a gap in it (a missing issuance,
 * a zone that came online late), and one 6-hour hole would drag a mean step far
 * enough to inflate the energy total by a visible margin. Falls back to 1 hour
 * for a single point, which matches every horizon this system serves.
 */
export function inferStepHours(points: ForecastPoint[]): number {
  if (points.length < 2) return 1
  const times = points.map((p) => new Date(p.timestamp).getTime()).sort((a, b) => a - b)
  const gaps: number[] = []
  for (let i = 1; i < times.length; i++) {
    const gap = (times[i] - times[i - 1]) / 3_600_000
    if (gap > 0) gaps.push(gap)
  }
  if (gaps.length === 0) return 1
  gaps.sort((a, b) => a - b)
  const mid = Math.floor(gaps.length / 2)
  return gaps.length % 2 === 0 ? (gaps[mid - 1] + gaps[mid]) / 2 : gaps[mid]
}

/** The points falling on tomorrow's ICT calendar date.
 *
 * ICT, not UTC: 00:00-06:59 ICT is still the previous UTC day, so a UTC-based
 * "tomorrow" would cut the Thai morning off one day's window and staple it onto
 * the other - the same trap `ictDateKey` was written for.
 */
export function pointsForTomorrow(points: ForecastPoint[], nowIso: string): ForecastPoint[] {
  const tomorrow = new Date(new Date(nowIso).getTime() + 24 * 3_600_000)
  const key = ictDateKey(tomorrow.toISOString())
  return points.filter((p) => ictDateKey(p.timestamp) === key)
}

/** The points still ahead of `nowIso`. Used for the intra-day tab, whose
 * horizon is only +1..+6h - so this is "the rest of what the model can see",
 * not "the rest of the day", and the label on screen has to say so. */
export function pointsAhead(points: ForecastPoint[], nowIso: string): ForecastPoint[] {
  const now = new Date(nowIso).getTime()
  return points.filter((p) => new Date(p.timestamp).getTime() > now)
}

export function computeForecastKpi(points: ForecastPoint[]): ForecastKpi {
  const usable = points.filter((p) => Number.isFinite(p.pred))
  if (usable.length === 0) return EMPTY_KPI

  const stepHours = inferStepHours(usable)
  const energyKwh = usable.reduce((sum, p) => sum + Math.max(0, p.pred) * stepHours, 0)

  let peak = usable[0]
  for (const p of usable) if (p.pred > peak.pred) peak = p

  // An interval is only meaningful when both bounds exist AND the prediction is
  // large enough for a percentage to mean anything - at 0.2 kW a ±0.3 kW band
  // is 150%, which is arithmetically right and tells the reader nothing.
  const hasBand = peak.lower !== null && peak.upper !== null && peak.pred > 0
  const bandKw = hasBand ? (peak.upper! - peak.lower!) / 2 : null
  const bandPct = bandKw !== null ? (100 * bandKw) / peak.pred : null

  const floor = peak.pred * PRODUCTIVE_FRACTION_OF_PEAK
  const productiveHours = usable.filter((p) => p.pred >= floor && p.pred > 0).length * stepHours

  return {
    energyKwh,
    peakKw: peak.pred,
    peakAtIso: peak.timestamp,
    bandKw,
    bandPct,
    productiveHours,
    pointCount: usable.length,
    stepHours,
  }
}
