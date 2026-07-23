import { describe, expect, it } from 'vitest'
import {
  DEFAULT_HAND_CONTROL_CONFIG,
  NEUTRAL_SIGNAL,
  clamp01,
  clampSym,
  handCentroid,
  mapHandToSignal,
  pinchRatio,
  signalToCameraTarget,
  smoothSignal,
  type Landmark,
} from '../handControl'

// A minimal 21-point hand where every landmark defaults to the palm center,
// then we override just the ones the mapping reads (wrist 0, thumb tip 4,
// index mcp 5, index tip 8, middle mcp 9).
function makeHand(overrides: Record<number, Landmark>, cx = 0.5, cy = 0.5): Landmark[] {
  const lm: Landmark[] = Array.from({ length: 21 }, () => ({ x: cx, y: cy }))
  for (const [i, p] of Object.entries(overrides)) lm[Number(i)] = p
  return lm
}

describe('clamp helpers', () => {
  it('clamp01 / clampSym bound to their ranges', () => {
    expect(clamp01(-1)).toBe(0)
    expect(clamp01(2)).toBe(1)
    expect(clampSym(-3)).toBe(-1)
    expect(clampSym(3)).toBe(1)
  })
})

describe('handCentroid', () => {
  it('averages wrist + the two knuckles', () => {
    const lm = makeHand({ 0: { x: 0.2, y: 0.2 }, 5: { x: 0.4, y: 0.6 }, 9: { x: 0.6, y: 0.4 } })
    expect(handCentroid(lm)).toEqual({ x: expect.closeTo(0.4, 6), y: expect.closeTo(0.4, 6) })
  })
})

describe('pinchRatio', () => {
  it('is scale-invariant: same gesture near or far reads the same', () => {
    // hand scale = wrist(0)->middle-mcp(9); pinch = thumb(4)->index(8)
    const near = makeHand({ 0: { x: 0.4, y: 0.9 }, 9: { x: 0.4, y: 0.5 }, 4: { x: 0.4, y: 0.6 }, 8: { x: 0.4, y: 0.7 } })
    const far = makeHand({ 0: { x: 0.45, y: 0.7 }, 9: { x: 0.45, y: 0.5 }, 4: { x: 0.45, y: 0.55 }, 8: { x: 0.45, y: 0.6 } })
    expect(pinchRatio(near)).toBeCloseTo(pinchRatio(far), 6)
  })

  it('grows as the fingers open', () => {
    const closed = makeHand({ 0: { x: 0.4, y: 0.9 }, 9: { x: 0.4, y: 0.5 }, 4: { x: 0.4, y: 0.6 }, 8: { x: 0.4, y: 0.61 } })
    const open = makeHand({ 0: { x: 0.4, y: 0.9 }, 9: { x: 0.4, y: 0.5 }, 4: { x: 0.3, y: 0.5 }, 8: { x: 0.5, y: 0.5 } })
    expect(pinchRatio(open)).toBeGreaterThan(pinchRatio(closed))
  })
})

describe('mapHandToSignal', () => {
  it('returns the neutral signal for a missing/degenerate hand', () => {
    expect(mapHandToSignal(null)).toEqual(NEUTRAL_SIGNAL)
    expect(mapHandToSignal([])).toEqual(NEUTRAL_SIGNAL)
  })

  it('a centered still hand produces ~zero azimuth (inside the deadzone)', () => {
    const lm = makeHand({ 0: { x: 0.5, y: 0.5 }, 5: { x: 0.5, y: 0.5 }, 9: { x: 0.5, y: 0.5 } })
    expect(mapHandToSignal(lm).azimuthNorm).toBe(0)
  })

  it('moving the hand right vs left flips the azimuth sign (mirrored default)', () => {
    const right = makeHand({ 0: { x: 0.9, y: 0.5 }, 5: { x: 0.9, y: 0.5 }, 9: { x: 0.9, y: 0.5 } })
    const left = makeHand({ 0: { x: 0.1, y: 0.5 }, 5: { x: 0.1, y: 0.5 }, 9: { x: 0.1, y: 0.5 } })
    expect(Math.sign(mapHandToSignal(right).azimuthNorm)).toBe(-Math.sign(mapHandToSignal(left).azimuthNorm))
    expect(mapHandToSignal(right).azimuthNorm).not.toBe(0)
  })

  it('a high hand looks from above (small polarNorm), a low hand from the horizon', () => {
    const high = makeHand({ 0: { x: 0.5, y: 0.15 }, 5: { x: 0.5, y: 0.15 }, 9: { x: 0.5, y: 0.15 } })
    const low = makeHand({ 0: { x: 0.5, y: 0.85 }, 5: { x: 0.5, y: 0.85 }, 9: { x: 0.5, y: 0.85 } })
    expect(mapHandToSignal(high).polarNorm).toBeLessThan(mapHandToSignal(low).polarNorm)
  })

  it('a closed pinch zooms in (higher zoomNorm) than an open hand', () => {
    const closed = makeHand({ 0: { x: 0.5, y: 0.9 }, 9: { x: 0.5, y: 0.5 }, 4: { x: 0.5, y: 0.6 }, 8: { x: 0.5, y: 0.61 } })
    const open = makeHand({ 0: { x: 0.5, y: 0.9 }, 9: { x: 0.5, y: 0.5 }, 4: { x: 0.35, y: 0.5 }, 8: { x: 0.65, y: 0.5 } })
    expect(mapHandToSignal(closed).zoomNorm).toBeGreaterThan(mapHandToSignal(open).zoomNorm)
  })

  it('honors mirrored=false by not flipping x', () => {
    const right = makeHand({ 0: { x: 0.9, y: 0.5 }, 5: { x: 0.9, y: 0.5 }, 9: { x: 0.9, y: 0.5 } })
    const mirrored = mapHandToSignal(right, DEFAULT_HAND_CONTROL_CONFIG)
    const unmirrored = mapHandToSignal(right, { ...DEFAULT_HAND_CONTROL_CONFIG, mirrored: false })
    expect(Math.sign(mirrored.azimuthNorm)).toBe(-Math.sign(unmirrored.azimuthNorm))
  })
})

describe('smoothSignal', () => {
  it('factor 1 snaps to target, factor 0 holds', () => {
    const a = { azimuthNorm: 0, polarNorm: 0, zoomNorm: 0 }
    const b = { azimuthNorm: 1, polarNorm: 1, zoomNorm: 1 }
    expect(smoothSignal(a, b, 1)).toEqual(b)
    expect(smoothSignal(a, b, 0)).toEqual(a)
  })

  it('factor 0.5 lands halfway', () => {
    const a = { azimuthNorm: 0, polarNorm: 0, zoomNorm: 0 }
    const b = { azimuthNorm: 1, polarNorm: 0.4, zoomNorm: 0.8 }
    const s = smoothSignal(a, b, 0.5)
    expect(s.azimuthNorm).toBeCloseTo(0.5, 6)
    expect(s.polarNorm).toBeCloseTo(0.2, 6)
    expect(s.zoomNorm).toBeCloseTo(0.4, 6)
  })
})

describe('signalToCameraTarget', () => {
  const range = { minDistance: 20, maxDistance: 100, minPolar: 0.2, maxPolar: 1.4, azimuthSpan: Math.PI }

  it('maps azimuthNorm across ±azimuthSpan and zoomNorm from far to near', () => {
    expect(signalToCameraTarget({ azimuthNorm: 1, polarNorm: 0.5, zoomNorm: 0 }, range).azimuth).toBeCloseTo(Math.PI, 6)
    expect(signalToCameraTarget({ azimuthNorm: -1, polarNorm: 0.5, zoomNorm: 0 }, range).azimuth).toBeCloseTo(-Math.PI, 6)
    // zoomNorm 0 -> far (max distance), 1 -> near (min distance)
    expect(signalToCameraTarget({ azimuthNorm: 0, polarNorm: 0.5, zoomNorm: 0 }, range).distance).toBeCloseTo(100, 6)
    expect(signalToCameraTarget({ azimuthNorm: 0, polarNorm: 0.5, zoomNorm: 1 }, range).distance).toBeCloseTo(20, 6)
  })

  it('keeps polar within the configured clamps', () => {
    expect(signalToCameraTarget({ azimuthNorm: 0, polarNorm: 0, zoomNorm: 0.5 }, range).polar).toBeCloseTo(0.2, 6)
    expect(signalToCameraTarget({ azimuthNorm: 0, polarNorm: 1, zoomNorm: 0.5 }, range).polar).toBeCloseTo(1.4, 6)
  })
})
