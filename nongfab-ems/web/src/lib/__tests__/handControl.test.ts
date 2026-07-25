import { describe, expect, it } from 'vitest'
import {
  DEFAULT_HAND_CONTROL_CONFIG,
  NEUTRAL_SIGNAL,
  clamp01,
  clampSym,
  createHandSignalFilter,
  createOneEuroState,
  damp,
  dampAngle,
  detectGesture,
  filterHandSignal,
  fingersExtended,
  handCentroid,
  mapHandToSignal,
  oneEuroStep,
  pinchRatio,
  smoothSignal,
  thumbExtended,
  verticalOffset,
  wrapAngle,
  ZERO_RATES,
  createGestureLatch,
  integrateHandCamera,
  mapSignalToRates,
  stepGestureLatch,
  type Landmark,
} from '../handControl'

// Build a full 21-point hand as a fist (all fingertips curled near the palm),
// then let callers "extend" specific fingers by pushing their tip out past the
// pip joint along -y (up). Wrist at bottom center; fingers point up.
function fistHand(): Landmark[] {
  const lm: Landmark[] = Array.from({ length: 21 }, () => ({ x: 0.5, y: 0.6 }))
  lm[0] = { x: 0.5, y: 0.9 } // wrist, low
  // pip joints sit mid-palm; tips default curled BELOW their pip (still low).
  for (const [pip, tip] of [
    [6, 8],
    [10, 12],
    [14, 16],
    [18, 20],
  ]) {
    lm[pip] = { x: 0.5, y: 0.55 }
    lm[tip] = { x: 0.5, y: 0.62 } // tip closer to wrist than pip -> curled
  }
  return lm
}

function extendFinger(lm: Landmark[], pip: number, tip: number): void {
  lm[pip] = { x: lm[pip].x, y: 0.5 }
  lm[tip] = { x: lm[tip].x, y: 0.2 } // tip well above pip, far from wrist
}

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

describe('damp (frame-rate-independent smoothing)', () => {
  it('dt<=0 holds; moves toward target and never overshoots', () => {
    expect(damp(0, 10, 8, 0)).toBe(0)
    const a = damp(0, 10, 8, 1 / 60)
    expect(a).toBeGreaterThan(0)
    expect(a).toBeLessThan(10)
  })

  it('is (nearly) frame-rate independent: one 2dt step ~= two dt steps', () => {
    const lambda = 6
    const dt = 1 / 60
    const oneBig = damp(0, 1, lambda, 2 * dt)
    const twoSmall = damp(damp(0, 1, lambda, dt), 1, lambda, dt)
    expect(oneBig).toBeCloseTo(twoSmall, 6)
  })

  it('converges to the target over time', () => {
    let v = 0
    for (let i = 0; i < 300; i++) v = damp(v, 5, 8, 1 / 60)
    expect(v).toBeCloseTo(5, 3)
  })
})

describe('wrapAngle / dampAngle', () => {
  it('wraps into (-pi, pi]', () => {
    expect(wrapAngle(0)).toBeCloseTo(0, 9)
    expect(wrapAngle(Math.PI)).toBeCloseTo(Math.PI, 9)
    expect(wrapAngle(Math.PI + 0.1)).toBeCloseTo(-Math.PI + 0.1, 6)
    expect(wrapAngle(3 * Math.PI)).toBeCloseTo(Math.PI, 6)
  })

  it('takes the SHORT way across the +/-pi seam', () => {
    // from ~+170deg toward ~-170deg: the shortest move is +20deg (crossing pi),
    // so the damped result should increase past +pi's wrap, not plunge negative.
    const from = (170 * Math.PI) / 180
    const to = (-170 * Math.PI) / 180
    const stepped = dampAngle(from, to, 8, 1 / 60)
    // moved a small positive amount in the wrapped sense
    expect(wrapAngle(stepped - from)).toBeGreaterThan(0)
    expect(Math.abs(wrapAngle(stepped - from))).toBeLessThan(20 * (Math.PI / 180))
  })

  it('dt<=0 holds the angle', () => {
    expect(dampAngle(1, -1, 8, 0)).toBe(1)
  })
})

describe('fingersExtended / detectGesture', () => {
  it('reads a fist as all fingers curled', () => {
    expect(fingersExtended(fistHand())).toEqual([false, false, false, false])
  })

  it('reads an open hand as all four fingers extended', () => {
    const lm = fistHand()
    extendFinger(lm, 6, 8)
    extendFinger(lm, 10, 12)
    extendFinger(lm, 14, 16)
    extendFinger(lm, 18, 20)
    expect(fingersExtended(lm)).toEqual([true, true, true, true])
  })

  it('a fist -> hold, an open hand -> control', () => {
    expect(detectGesture(fistHand())).toBe('hold')
    const open = fistHand()
    extendFinger(open, 6, 8)
    extendFinger(open, 10, 12)
    extendFinger(open, 14, 16)
    extendFinger(open, 18, 20)
    expect(detectGesture(open)).toBe('control')
  })

  it('index+middle only (a "V") -> recenter', () => {
    const v = fistHand()
    extendFinger(v, 6, 8)
    extendFinger(v, 10, 12)
    expect(detectGesture(v)).toBe('recenter')
  })

  it('a missing/degenerate hand -> none', () => {
    expect(detectGesture(null)).toBe('none')
    expect(detectGesture([])).toBe('none')
  })
})

describe('One-Euro filter', () => {
  it('passes the first sample through unchanged, then eases toward new values', () => {
    const s = createOneEuroState()
    expect(oneEuroStep(s, 5, 0)).toBe(5)
    const next = oneEuroStep(s, 10, 1 / 60)
    expect(next).toBeGreaterThan(5)
    expect(next).toBeLessThan(10)
  })

  it('converges to a held value over time', () => {
    const s = createOneEuroState()
    let v = oneEuroStep(s, 0, 0)
    for (let i = 1; i <= 400; i++) v = oneEuroStep(s, 1, i / 60)
    expect(v).toBeCloseTo(1, 2)
  })

  it('is more responsive (less lag) when the input moves fast - the whole point', () => {
    // Same one-step jump, but with a high beta the cutoff opens with speed, so
    // it should land CLOSER to the target than a low-beta (steadier) filter.
    const slow = createOneEuroState()
    const fast = createOneEuroState()
    oneEuroStep(slow, 0, 0, { minCutoff: 1, beta: 0, dCutoff: 1 })
    oneEuroStep(fast, 0, 0, { minCutoff: 1, beta: 5, dCutoff: 1 })
    const slowV = oneEuroStep(slow, 1, 1 / 60, { minCutoff: 1, beta: 0, dCutoff: 1 })
    const fastV = oneEuroStep(fast, 1, 1 / 60, { minCutoff: 1, beta: 5, dCutoff: 1 })
    expect(fastV).toBeGreaterThan(slowV)
  })

  it('filters all three signal channels together', () => {
    const f = createHandSignalFilter()
    const first = filterHandSignal(f, { azimuthNorm: 0.5, polarNorm: 0.3, zoomNorm: 0.8 }, 0)
    expect(first).toEqual({ azimuthNorm: 0.5, polarNorm: 0.3, zoomNorm: 0.8 })
    const second = filterHandSignal(f, { azimuthNorm: 1, polarNorm: 0, zoomNorm: 0 }, 1 / 60)
    expect(second.azimuthNorm).toBeGreaterThan(0.5)
    expect(second.polarNorm).toBeLessThan(0.3)
    expect(second.zoomNorm).toBeLessThan(0.8)
  })
})

// --- Rate control + the new gesture modes (2026-07-25) ----------------------
// The user reported zoom and left/right were hard to use with the original
// ABSOLUTE mapping (hand position = camera position). These cover the rework:
// gestures select an axis, and the hand's offset from centre is a RATE.

describe('thumbExtended / the new gesture modes', () => {
  it('a fist does NOT read as a thumbs-up (the thumb is folded against the palm)', () => {
    expect(thumbExtended(fistHand())).toBe(false)
    expect(detectGesture(fistHand())).toBe('hold')
  })

  it('👍 thumb out with every finger curled -> toggleRun', () => {
    const lm = fistHand()
    lm[3] = { x: 0.5, y: 0.6 } // thumb IP, mid-palm
    lm[4] = { x: 0.5, y: 0.3 } // thumb tip, well clear of the index knuckle
    expect(thumbExtended(lm)).toBe(true)
    expect(detectGesture(lm)).toBe('toggleRun')
  })

  it('🤏 index curled onto the thumb with other fingers out -> zoom', () => {
    const lm = fistHand()
    extendFinger(lm, 10, 12)
    extendFinger(lm, 14, 16)
    extendFinger(lm, 18, 20)
    lm[4] = { x: 0.5, y: 0.63 } // thumb tip touching the curled index tip
    expect(detectGesture(lm)).toBe('zoom')
  })

  it('🤟 three fingers (pinky down) -> pan, and does not steal the "V" -> recenter', () => {
    const pan = fistHand()
    extendFinger(pan, 6, 8)
    extendFinger(pan, 10, 12)
    extendFinger(pan, 14, 16)
    expect(detectGesture(pan)).toBe('pan')

    const v = fistHand()
    extendFinger(v, 6, 8)
    extendFinger(v, 10, 12)
    expect(detectGesture(v)).toBe('recenter')
  })
})

describe('verticalOffset / mapSignalToRates', () => {
  it('verticalOffset is + when the hand is HIGH in frame', () => {
    expect(verticalOffset({ azimuthNorm: 0, polarNorm: 0.1, zoomNorm: 0.5 })).toBeGreaterThan(0)
    expect(verticalOffset({ azimuthNorm: 0, polarNorm: 0.9, zoomNorm: 0.5 })).toBeLessThan(0)
    expect(verticalOffset({ azimuthNorm: 0, polarNorm: 0.5, zoomNorm: 0.5 })).toBeCloseTo(0, 6)
  })

  it('open hand drives orbit only - a high hand raises the camera (polar shrinks)', () => {
    const r = mapSignalToRates({ azimuthNorm: 0.5, polarNorm: 0.2, zoomNorm: 0.5 }, 'control')
    expect(r.azimuthRate).toBeGreaterThan(0)
    expect(r.polarRate).toBeLessThan(0)
    expect(r.zoomRate).toBe(0)
    expect(r.panXRate).toBe(0)
    expect(r.panYRate).toBe(0)
  })

  it('pinch drives zoom only - lifting the pinched hand zooms IN', () => {
    const up = mapSignalToRates({ azimuthNorm: 0.9, polarNorm: 0.1, zoomNorm: 0.5 }, 'zoom')
    expect(up.zoomRate).toBeGreaterThan(0)
    // The hand is far off-centre horizontally, but zoom mode must ignore that.
    expect(up.azimuthRate).toBe(0)
    const down = mapSignalToRates({ azimuthNorm: 0, polarNorm: 0.9, zoomNorm: 0.5 }, 'zoom')
    expect(down.zoomRate).toBeLessThan(0)
  })

  it('three fingers drive pan only', () => {
    const r = mapSignalToRates({ azimuthNorm: -0.5, polarNorm: 0.2, zoomNorm: 0.5 }, 'pan')
    expect(r.panXRate).toBeLessThan(0)
    expect(r.panYRate).toBeGreaterThan(0)
    expect(r.azimuthRate).toBe(0)
    expect(r.zoomRate).toBe(0)
  })

  it('hold / recenter / toggleRun / no hand command no motion at all', () => {
    const far = { azimuthNorm: 1, polarNorm: 0, zoomNorm: 1 }
    expect(mapSignalToRates(far, 'hold')).toEqual(ZERO_RATES)
    expect(mapSignalToRates(far, 'recenter')).toEqual(ZERO_RATES)
    expect(mapSignalToRates(far, 'toggleRun')).toEqual(ZERO_RATES)
    expect(mapSignalToRates(null, 'control')).toEqual(ZERO_RATES)
  })

  it('a centred hand inside the deadzone commands nothing', () => {
    expect(mapSignalToRates({ azimuthNorm: 0, polarNorm: 0.5, zoomNorm: 0.5 }, 'control')).toEqual(ZERO_RATES)
  })
})

describe('integrateHandCamera', () => {
  const limits = {
    azimuthSpeed: 2,
    polarSpeed: 1,
    zoomSpeed: 0.8,
    minDistance: 10,
    maxDistance: 100,
    minPolar: 0.15,
    maxPolar: 1.45,
  }
  const start = { azimuth: 0, polar: 0.9, distance: 50 }

  it('dt<=0 holds the state unchanged', () => {
    expect(integrateHandCamera(start, { ...ZERO_RATES, azimuthRate: 1 }, 0, limits)).toBe(start)
  })

  it('a held rate keeps accumulating - so any angle is reachable', () => {
    let s = start
    for (let i = 0; i < 30; i++) s = integrateHandCamera(s, { ...ZERO_RATES, azimuthRate: 1 }, 1 / 60, limits)
    // 30 frames at 1/60s x 2 rad/s = ~1 rad, far past what one hand-span could
    // command under the old absolute mapping.
    expect(s.azimuth).toBeCloseTo(1, 1)
  })

  it('zoom is multiplicative and clamps at both ends', () => {
    const inOne = integrateHandCamera(start, { ...ZERO_RATES, zoomRate: 1 }, 0.5, limits)
    expect(inOne.distance).toBeLessThan(start.distance)
    let s = start
    for (let i = 0; i < 600; i++) s = integrateHandCamera(s, { ...ZERO_RATES, zoomRate: 1 }, 1 / 60, limits)
    expect(s.distance).toBeCloseTo(limits.minDistance, 6)
    for (let i = 0; i < 1200; i++) s = integrateHandCamera(s, { ...ZERO_RATES, zoomRate: -1 }, 1 / 60, limits)
    expect(s.distance).toBeCloseTo(limits.maxDistance, 6)
  })

  it('polar stays inside its clamps and azimuth wraps', () => {
    let s = start
    for (let i = 0; i < 600; i++) s = integrateHandCamera(s, { ...ZERO_RATES, polarRate: -1 }, 1 / 60, limits)
    expect(s.polar).toBeCloseTo(limits.minPolar, 6)
    for (let i = 0; i < 1200; i++) s = integrateHandCamera(s, { ...ZERO_RATES, polarRate: 1 }, 1 / 60, limits)
    expect(s.polar).toBeCloseTo(limits.maxPolar, 6)
    let spun = start
    for (let i = 0; i < 600; i++) spun = integrateHandCamera(spun, { ...ZERO_RATES, azimuthRate: 1 }, 1 / 60, limits)
    expect(spun.azimuth).toBeGreaterThan(-Math.PI)
    expect(spun.azimuth).toBeLessThanOrEqual(Math.PI)
  })
})

describe('stepGestureLatch', () => {
  it('fires exactly once per held gesture, then rearms only after release', () => {
    const latch = createGestureLatch()
    let fires = 0
    // Held for a full second at 60fps: must fire once, not 60 times.
    for (let i = 0; i < 60; i++) if (stepGestureLatch(latch, true, 1 / 60)) fires++
    expect(fires).toBe(1)
    // Still held - no second fire.
    for (let i = 0; i < 60; i++) if (stepGestureLatch(latch, true, 1 / 60)) fires++
    expect(fires).toBe(1)
    // Release, then hold again -> one more fire.
    stepGestureLatch(latch, false, 1 / 60)
    for (let i = 0; i < 60; i++) if (stepGestureLatch(latch, true, 1 / 60)) fires++
    expect(fires).toBe(2)
  })

  it('a gesture flashing by faster than the hold time never fires', () => {
    const latch = createGestureLatch()
    let fired = false
    for (let i = 0; i < 10; i++) {
      if (stepGestureLatch(latch, true, 1 / 60)) fired = true // ~0.17s, under the 0.35s hold
      if (stepGestureLatch(latch, false, 1 / 60)) fired = true
    }
    expect(fired).toBe(false)
  })
})
