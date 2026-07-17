import type { WeatherStripPoint } from './types'

export interface StripBlock {
  key: string
  timestamp: string
  offset: number
  temp_c: number | null
  ssrd_w_m2: number | null
}

/** 0 (top of the hour) to just-under-1 (about to roll to the next hour) -
 * the continuous "how far into the current hour are we" fraction that
 * drives the weather strip's scroll position (WeatherStrip.tsx). Computed in
 * UTC (all timestamps in this app are UTC ISO strings under the hood -
 * ICT is a display-only conversion, see timeScrub.ts) - Thailand has no DST
 * so an hour is the same 3,600,000ms regardless of which zone's clock you'd
 * rather think in. */
export function fractionIntoHour(now: Date): number {
  const floored = new Date(now)
  floored.setUTCMinutes(0, 0, 0)
  return (now.getTime() - floored.getTime()) / (60 * 60 * 1000)
}

/** Builds `2*hoursEachSide + 2` hour-blocks centered on `now`'s current hour
 * (offsets `-hoursEachSide` through `+hoursEachSide + 1` inclusive - the
 * extra "+1" is the block that's about to slide into view from the right as
 * the current hour elapses, so the strip never shows a blank edge), each
 * matched to the real data point falling in the same hour. `points` need
 * not cover every offset - a missing hour just gets null temp/ssrd (the
 * component renders that as a placeholder, not a crash). */
export function buildStripBlocks(points: WeatherStripPoint[], now: Date, hoursEachSide: number): StripBlock[] {
  const byHour = new Map<string, WeatherStripPoint>()
  for (const p of points) {
    const d = new Date(p.timestamp)
    d.setUTCMinutes(0, 0, 0)
    byHour.set(d.toISOString(), p)
  }

  const floored = new Date(now)
  floored.setUTCMinutes(0, 0, 0)

  const blocks: StripBlock[] = []
  for (let offset = -hoursEachSide; offset <= hoursEachSide + 1; offset++) {
    const ts = new Date(floored.getTime() + offset * 60 * 60 * 1000)
    const iso = ts.toISOString()
    const match = byHour.get(iso)
    blocks.push({
      key: iso,
      timestamp: iso,
      offset,
      temp_c: match?.temp_c ?? null,
      ssrd_w_m2: match?.ssrd_w_m2 ?? null,
    })
  }
  return blocks
}
