import { describe, expect, it } from 'vitest'
import { buildStripBlocks, fractionIntoHour } from '../weatherStrip'
import type { WeatherStripPoint } from '../types'

describe('fractionIntoHour', () => {
  it('is 0 exactly on the hour', () => {
    expect(fractionIntoHour(new Date('2026-07-17T14:00:00.000Z'))).toBe(0)
  })

  it('is 0.5 at half past', () => {
    expect(fractionIntoHour(new Date('2026-07-17T14:30:00.000Z'))).toBeCloseTo(0.5, 6)
  })

  it('is just under 1 a moment before the next hour', () => {
    expect(fractionIntoHour(new Date('2026-07-17T14:59:59.000Z'))).toBeCloseTo(3599 / 3600, 6)
  })
})

describe('buildStripBlocks', () => {
  const points: WeatherStripPoint[] = [
    { timestamp: '2026-07-17T12:00:00.000Z', temp_c: 29.0, ssrd_w_m2: 400 },
    { timestamp: '2026-07-17T13:00:00.000Z', temp_c: 30.0, ssrd_w_m2: 600 },
    { timestamp: '2026-07-17T14:00:00.000Z', temp_c: 32.0, ssrd_w_m2: 800 },
    { timestamp: '2026-07-17T15:00:00.000Z', temp_c: 31.5, ssrd_w_m2: 700 },
    { timestamp: '2026-07-17T16:00:00.000Z', temp_c: 30.5, ssrd_w_m2: 500 },
  ]

  it('returns 2*hoursEachSide + 2 blocks, offsets -N..+N+1 inclusive', () => {
    const blocks = buildStripBlocks(points, new Date('2026-07-17T14:00:00.000Z'), 2)
    expect(blocks).toHaveLength(6)
    expect(blocks.map((b) => b.offset)).toEqual([-2, -1, 0, 1, 2, 3])
  })

  it('the current-hour block (offset 0) matches "now" truncated to the hour, exactly on the hour', () => {
    const blocks = buildStripBlocks(points, new Date('2026-07-17T14:00:00.000Z'), 2)
    const center = blocks.find((b) => b.offset === 0)!
    expect(center.timestamp).toBe('2026-07-17T14:00:00.000Z')
    expect(center.temp_c).toBe(32.0)
  })

  it('offset 0 still resolves to the current (not next) hour mid-hour', () => {
    const blocks = buildStripBlocks(points, new Date('2026-07-17T14:45:00.000Z'), 2)
    const center = blocks.find((b) => b.offset === 0)!
    expect(center.timestamp).toBe('2026-07-17T14:00:00.000Z')
    expect(center.temp_c).toBe(32.0)
  })

  it('the example from the user: 4 neighbors each side, centered on the current hour', () => {
    const blocks = buildStripBlocks(points, new Date('2026-07-17T14:00:00.000Z'), 4)
    expect(blocks.map((b) => b.offset)).toEqual([-4, -3, -2, -1, 0, 1, 2, 3, 4, 5])
    const hours = blocks.map((b) => new Date(b.timestamp).getUTCHours())
    expect(hours).toEqual([10, 11, 12, 13, 14, 15, 16, 17, 18, 19])
  })

  it('a missing hour renders as a null placeholder, not a crash', () => {
    const sparse: WeatherStripPoint[] = [{ timestamp: '2026-07-17T14:00:00.000Z', temp_c: 32.0, ssrd_w_m2: 800 }]
    const blocks = buildStripBlocks(sparse, new Date('2026-07-17T14:00:00.000Z'), 1)
    const missing = blocks.find((b) => b.offset === 1)!
    expect(missing.temp_c).toBeNull()
    expect(missing.ssrd_w_m2).toBeNull()
  })
})
