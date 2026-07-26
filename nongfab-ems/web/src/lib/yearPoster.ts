import type { PosterDay, PosterMonth, PosterResponse } from './types'

/** Geometry for "หนึ่งปีของแสงที่หนองแฟบ" (project S, 2026-07-26).
 *
 * A radial dial. Each day of the year is one ray, and along that ray a segment
 * runs from the day's sunrise to its sunset - so the ring the segments trace
 * out is the site's daylight window breathing across the seasons. Colour comes
 * from the month.
 *
 * WHY THE TWO LAYERS ARE AT DIFFERENT RESOLUTIONS, ON PURPOSE. The shape is
 * per-day and exact: sunrise and sunset from pvlib at Nong Fab's real
 * coordinates, which is astronomy rather than measurement. The colour is
 * per-month and modelled, because this project's annual energy figure *is*
 * twelve representative days - one per calendar month - and smearing that into
 * 365 daily shades would invent 353 values nobody computed. A prettier poster
 * was available and it would have been a lie in pixels. The image labels both
 * layers.
 *
 * Everything here is pure: the component renders what these functions return,
 * and the download serialises the same SVG the screen shows.
 */

export interface Spoke {
  x1: number
  y1: number
  x2: number
  y2: number
  /** 0-1, this day's month's share of the best month. Drives colour only. */
  intensity: number
  isRainySeason: boolean
}

export interface MonthTick {
  label: string
  /** Where the month's name sits, outside the ring. */
  x: number
  y: number
  /** Radial boundary line at the month's first day. */
  lineX1: number
  lineY1: number
  lineX2: number
  lineY2: number
}

export interface PosterGeometry {
  size: number
  centre: number
  innerRadius: number
  outerRadius: number
  spokes: Spoke[]
  monthTicks: MonthTick[]
  /** Hour rings actually drawn, so the component and the tests agree. */
  hourRings: { hour: number; radius: number }[]
}

export const POSTER_SIZE = 900
const INNER_FRACTION = 0.24
const OUTER_FRACTION = 0.40
/** Hours mapped onto the radius. The sun at Nong Fab is up roughly 05:45-18:45
 * all year, so a 0-24 scale would waste most of the band on darkness. */
export const HOUR_MIN = 5
export const HOUR_MAX = 19
/* Three-hourly, not two-hourly. The labels sit in a column on the upward
   vertical - the only place a radial axis can be read - and seven of them
   collided with each other and with the January spokes when this was first
   rendered and looked at. Five read as a scale. */
const HOUR_RING_STEP = 3

export function hourToRadius(hour: number, inner: number, outer: number): number {
  const clamped = Math.min(HOUR_MAX, Math.max(HOUR_MIN, hour))
  return inner + ((clamped - HOUR_MIN) / (HOUR_MAX - HOUR_MIN)) * (outer - inner)
}

/** Day 1 at the top, running clockwise - the direction a calendar is read. */
export function dayToAngle(dayIndex: number, dayCount: number): number {
  return (dayIndex / dayCount) * Math.PI * 2 - Math.PI / 2
}

function monthOfDay(dayOfYear: number, months: PosterMonth[]): PosterMonth {
  let remaining = dayOfYear
  for (const m of months) {
    if (remaining <= m.days_in_month) return m
    remaining -= m.days_in_month
  }
  return months[months.length - 1]
}

/** Index of the first day of each month, from the real day counts the API
 * sent rather than a hardcoded table - which would be wrong every leap year. */
export function monthStartIndices(months: PosterMonth[]): number[] {
  const starts: number[] = []
  let acc = 0
  for (const m of months) {
    starts.push(acc)
    acc += m.days_in_month
  }
  return starts
}

export function buildPosterGeometry(data: PosterResponse, size = POSTER_SIZE): PosterGeometry {
  const centre = size / 2
  const innerRadius = size * INNER_FRACTION
  const outerRadius = size * OUTER_FRACTION
  const dayCount = data.days.length
  const peakMonth = Math.max(...data.months.map((m) => m.ac_energy_kwh), 0)

  const spokes: Spoke[] = []
  data.days.forEach((day: PosterDay, i) => {
    // A day with no computable sunrise draws nothing. Substituting a default
    // would put a segment on the dial for a day the geometry could not answer.
    if (day.sunrise_hour === null || day.sunset_hour === null) return
    const month = monthOfDay(day.day_of_year, data.months)
    const angle = dayToAngle(i, dayCount)
    const rise = hourToRadius(day.sunrise_hour, innerRadius, outerRadius)
    const set = hourToRadius(day.sunset_hour, innerRadius, outerRadius)
    spokes.push({
      x1: centre + Math.cos(angle) * rise,
      y1: centre + Math.sin(angle) * rise,
      x2: centre + Math.cos(angle) * set,
      y2: centre + Math.sin(angle) * set,
      intensity: peakMonth > 0 ? month.ac_energy_kwh / peakMonth : 0,
      isRainySeason: month.is_rainy_season,
    })
  })

  const labelRadius = outerRadius + size * 0.055
  const monthTicks: MonthTick[] = monthStartIndices(data.months).map((startIndex, i) => {
    const boundary = dayToAngle(startIndex, dayCount)
    // The name sits at the month's middle, the rule at its first day.
    const mid = dayToAngle(startIndex + data.months[i].days_in_month / 2, dayCount)
    return {
      label: data.months[i].label,
      x: centre + Math.cos(mid) * labelRadius,
      y: centre + Math.sin(mid) * labelRadius,
      lineX1: centre + Math.cos(boundary) * (innerRadius - size * 0.012),
      lineY1: centre + Math.sin(boundary) * (innerRadius - size * 0.012),
      lineX2: centre + Math.cos(boundary) * (outerRadius + size * 0.012),
      lineY2: centre + Math.sin(boundary) * (outerRadius + size * 0.012),
    }
  })

  const hourRings: { hour: number; radius: number }[] = []
  for (let h = HOUR_MIN + 1; h < HOUR_MAX; h += HOUR_RING_STEP) {
    hourRings.push({ hour: h, radius: hourToRadius(h, innerRadius, outerRadius) })
  }

  return { size, centre, innerRadius, outerRadius, spokes, monthTicks, hourRings }
}

/** Warm gold for the dry months, cooler for the rainy ones, both darkening
 * with the month's output. Two hue families rather than one gradient so the
 * rainy season is legible as a season and not merely as "less".
 *
 * Intensity is measured against the best month from **zero**, not stretched
 * between the weakest and strongest. Nong Fab's months really do only range
 * about 8.4k-11.2k kWh, so a min-max stretch would render a 25% spread as the
 * full colour range and make the seasons look far more dramatic than they are.
 * The washed-out result is the honest one: this site's output is remarkably
 * flat across the year, and the picture should say that. */
export function spokeColour(spoke: Spoke): string {
  const light = 78 - spoke.intensity * 42
  return spoke.isRainySeason ? `hsl(196 62% ${light}%)` : `hsl(38 92% ${light}%)`
}

/** Turn the rendered <svg> into a downloadable file.
 *
 * Serialises the live node rather than re-generating a second SVG, so what
 * downloads cannot drift from what the viewer approved on screen.
 */
export function svgToBlob(svg: SVGSVGElement): Blob {
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  const source = new XMLSerializer().serializeToString(clone)
  return new Blob([`<?xml version="1.0" encoding="UTF-8"?>\n${source}`], {
    type: 'image/svg+xml;charset=utf-8',
  })
}

export function posterFilename(zone: string, year: number): string {
  return `nongfab-year-of-light-${zone}-${year}.svg`
}
