import { describe, expect, it } from 'vitest'
import {
  lightingForCloudCover,
  shadowCameraExtent,
  shadowsWorthRendering,
} from '../sceneLighting'

describe('lightingForCloudCover', () => {
  it('leaves a clear sky at full sun', () => {
    expect(lightingForCloudCover(0)).toEqual({ directional: 1, ambient: 0.6 })
  })

  it('treats a missing reading as clear sky, not as darkness', () => {
    // An ingestion gap is not weather. Rendering it as an overcast scene would
    // be reporting cloud that was never observed.
    expect(lightingForCloudCover(null).directional).toBe(1)
    expect(lightingForCloudCover(Number.NaN).directional).toBe(1)
  })

  it('never kills the sun entirely, even fully overcast', () => {
    // Diffuse light through thick cloud is real; zero would also snap the
    // shadows off at 100% cover, which reads as a glitch, not as weather.
    const overcast = lightingForCloudCover(100)
    expect(overcast.directional).toBeCloseTo(0.15)
    expect(overcast.directional).toBeGreaterThan(0)
  })

  it('lifts the ambient fill as it dims the sun, so overcast is softer not darker', () => {
    const clear = lightingForCloudCover(0)
    const overcast = lightingForCloudCover(100)
    expect(overcast.directional).toBeLessThan(clear.directional)
    expect(overcast.ambient).toBeGreaterThan(clear.ambient)
  })

  it('moves monotonically between the two', () => {
    const values = [0, 25, 50, 75, 100].map((pct) => lightingForCloudCover(pct))
    for (let i = 1; i < values.length; i++) {
      expect(values[i].directional).toBeLessThan(values[i - 1].directional)
      expect(values[i].ambient).toBeGreaterThan(values[i - 1].ambient)
    }
  })

  it('clamps a reading outside 0-100 instead of extrapolating past it', () => {
    expect(lightingForCloudCover(-20)).toEqual(lightingForCloudCover(0))
    expect(lightingForCloudCover(140)).toEqual(lightingForCloudCover(100))
  })
})

describe('shadowCameraExtent', () => {
  it('scales with the scene so far rows keep their shadows', () => {
    expect(shadowCameraExtent(200)).toBeGreaterThan(shadowCameraExtent(50))
  })

  it('keeps a floor, so a tiny zone does not get a degenerate shadow box', () => {
    expect(shadowCameraExtent(1)).toBe(20)
  })
})

describe('shadowsWorthRendering', () => {
  it('is off at night - there is no sun to cast from', () => {
    expect(shadowsWorthRendering(-10)).toBe(false)
    expect(shadowsWorthRendering(0)).toBe(false)
  })

  it('is off at a grazing sun, where the shadow is a smear across the whole map', () => {
    expect(shadowsWorthRendering(2)).toBe(false)
  })

  it('is on for a sun that is properly up', () => {
    expect(shadowsWorthRendering(30)).toBe(true)
  })
})
