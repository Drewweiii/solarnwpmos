import { describe, expect, it } from 'vitest'
import type { PosterDay, PosterMonth, PosterResponse } from '../types'
import { buildPosterGeometry, dayToAngle, hourToRadius, monthStartIndices, spokeColour, HOUR_MAX, HOUR_MIN } from '../yearPoster'

const DAYS_IN_MONTH_2026 = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

function months(): PosterMonth[] {
  return DAYS_IN_MONTH_2026.map((days, i) => ({
    month: i + 1,
    label: `M${i + 1}`,
    // June (index 5) is the strongest month here, so intensity has a clear peak.
    ac_energy_kwh: i === 5 ? 12000 : 6000,
    is_rainy_season: i >= 5 && i <= 9,
    days_in_month: days,
  }))
}

function days(count = 365, gapAt: number | null = null): PosterDay[] {
  return Array.from({ length: count }, (_, i) => ({
    day_of_year: i + 1,
    sunrise_hour: i === gapAt ? null : 6.2,
    sunset_hour: i === gapAt ? null : 18.4,
    daylight_hours: i === gapAt ? null : 12.2,
    noon_elevation_deg: 70,
  }))
}

function poster(overrides: Partial<PosterResponse> = {}): PosterResponse {
  return {
    zone: 'GIS',
    year: 2026,
    lat: 12.71,
    lon: 101.15,
    days: days(),
    months: months(),
    annual_ac_energy_kwh: 78000,
    longest_day: 171,
    shortest_day: 354,
    geometry_note: 'g',
    energy_note: 'e',
    why_note: 'w',
    ...overrides,
  }
}

describe('yearPoster geometry', () => {
  it('puts 1 January at the top and runs clockwise', () => {
    // A year dial that started somewhere else, or ran anticlockwise, would be
    // read wrong by everyone before they noticed.
    expect(dayToAngle(0, 365)).toBeCloseTo(-Math.PI / 2)
    const q = dayToAngle(365 / 4, 365)
    expect(Math.cos(q)).toBeCloseTo(1, 5) // a quarter year later is due right
  })

  it('maps sunrise nearer the centre than sunset', () => {
    const rise = hourToRadius(6, 100, 200)
    const set = hourToRadius(18, 100, 200)
    expect(rise).toBeLessThan(set)
    expect(hourToRadius(HOUR_MIN, 100, 200)).toBe(100)
    expect(hourToRadius(HOUR_MAX, 100, 200)).toBe(200)
  })

  it('clamps hours outside the drawn band instead of drawing off the dial', () => {
    expect(hourToRadius(0, 100, 200)).toBe(100)
    expect(hourToRadius(23.9, 100, 200)).toBe(200)
  })

  it('derives month boundaries from the real day counts, not a fixed table', () => {
    const leap = months()
    leap[1] = { ...leap[1], days_in_month: 29 }
    // Every boundary after February shifts in a leap year; a hardcoded table
    // would point each month label at the wrong arc for that whole year.
    expect(monthStartIndices(months())[2]).toBe(59)
    expect(monthStartIndices(leap)[2]).toBe(60)
  })

  it('draws one spoke per day and twelve month ticks', () => {
    const g = buildPosterGeometry(poster())
    expect(g.spokes).toHaveLength(365)
    expect(g.monthTicks).toHaveLength(12)
  })

  it('omits a day whose geometry could not be computed rather than defaulting it', () => {
    // Substituting a stand-in sunrise would put a segment on the dial for a day
    // the astronomy did not answer - a drawn line implying a fact.
    const g = buildPosterGeometry(poster({ days: days(365, 100) }))
    expect(g.spokes).toHaveLength(364)
  })

  it('scales intensity against the best month, so the peak month is full strength', () => {
    const g = buildPosterGeometry(poster())
    const juneSpoke = g.spokes[160] // mid-June
    const janSpoke = g.spokes[10]
    expect(juneSpoke.intensity).toBeCloseTo(1)
    expect(janSpoke.intensity).toBeCloseTo(0.5)
  })

  it('colours the rainy season a different hue, not merely a paler one', () => {
    const dry = spokeColour({ x1: 0, y1: 0, x2: 0, y2: 0, intensity: 0.5, isRainySeason: false })
    const wet = spokeColour({ x1: 0, y1: 0, x2: 0, y2: 0, intensity: 0.5, isRainySeason: true })
    // Same lightness, different hue - so "rainy" reads as a season rather than
    // being confused with "a weaker dry month".
    expect(dry).toContain('hsl(38')
    expect(wet).toContain('hsl(196')
    expect(dry).not.toBe(wet)
  })

  it('handles a leap year without leaving a wedge undrawn', () => {
    const leapMonths = months()
    leapMonths[1] = { ...leapMonths[1], days_in_month: 29 }
    const g = buildPosterGeometry(poster({ days: days(366), months: leapMonths }))
    expect(g.spokes).toHaveLength(366)
    expect(g.monthTicks).toHaveLength(12)
  })
})
