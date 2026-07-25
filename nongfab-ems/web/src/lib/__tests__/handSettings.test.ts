import { describe, expect, it } from 'vitest'
import { DEFAULT_HAND_CONTROL_CONFIG, integrateHandCamera, mapSignalToRates, stepGestureLatch, createGestureLatch } from '../handControl'
import { DEFAULT_HAND_TUNING, resolveHandTuning } from '../handSettings'
import type { SettingItem } from '../types'

function handSetting(key: string, value: number): SettingItem {
  return {
    key,
    group: 'hand',
    group_label: 'ความไวการควบคุมด้วยมือ (Hand control)',
    label: key,
    unit: '',
    default: 0,
    value,
    minimum: 0,
    maximum: 100,
    step: 0.01,
    origin: 'tuning',
    origin_label: 'ค่าตั้งไว้เพื่อความรู้สึกใช้งาน',
    note: '',
    frontend_only: true,
    overridden: true,
    updated_at: null,
    updated_by: null,
  }
}

describe('resolveHandTuning', () => {
  it('falls back to the compiled defaults when settings have not loaded', () => {
    expect(resolveHandTuning(undefined)).toEqual(DEFAULT_HAND_TUNING)
  })

  it('takes published values for every hand.* key', () => {
    const tuning = resolveHandTuning([
      handSetting('hand.deadzone', 0.2),
      handSetting('hand.pinch_engage_ratio', 0.6),
      handSetting('hand.rate_gain', 4),
      handSetting('hand.azimuth_speed_rad_s', 5),
      handSetting('hand.polar_speed_rad_s', 3),
      handSetting('hand.zoom_speed_per_s', 2),
      handSetting('hand.latch_hold_seconds', 1.5),
    ])
    expect(tuning.config.deadzone).toBe(0.2)
    expect(tuning.config.pinchEngageRatio).toBe(0.6)
    expect(tuning.config.rateGain).toBe(4)
    expect(tuning.azimuthSpeed).toBe(5)
    expect(tuning.polarSpeed).toBe(3)
    expect(tuning.zoomSpeed).toBe(2)
    expect(tuning.latchHoldSeconds).toBe(1.5)
    // untouched config fields keep their compiled values
    expect(tuning.config.mirrored).toBe(DEFAULT_HAND_CONTROL_CONFIG.mirrored)
  })

  it('lets a local draft win over the published value (the "try it yourself" path)', () => {
    const tuning = resolveHandTuning([handSetting('hand.rate_gain', 4)], { 'hand.rate_gain': 1.5 })
    expect(tuning.config.rateGain).toBe(1.5)
  })

  it('ignores non-hand settings and unknown keys', () => {
    const other: SettingItem = { ...handSetting('financial.capex_thb_per_kwp', 99), group: 'financial' }
    const tuning = resolveHandTuning([other], { 'hand.nonsense': 5 })
    expect(tuning).toEqual(DEFAULT_HAND_TUNING)
  })

  it('rejects a non-finite drafted value rather than feeding NaN to the camera', () => {
    const tuning = resolveHandTuning([], { 'hand.azimuth_speed_rad_s': Number.NaN })
    expect(tuning.azimuthSpeed).toBe(DEFAULT_HAND_TUNING.azimuthSpeed)
  })
})

// The point of part 3 is that a published number actually changes what the
// camera does - these assert the resolved tuning drives the same pure functions
// the 3D scene calls each frame.
describe('resolved tuning actually drives the camera math', () => {
  it('a bigger azimuth speed turns the camera further in the same time', () => {
    const slow = resolveHandTuning([handSetting('hand.azimuth_speed_rad_s', 1)])
    const fast = resolveHandTuning([handSetting('hand.azimuth_speed_rad_s', 4)])
    const state = { azimuth: 0, polar: 0.9, distance: 50 }
    const rates = { azimuthRate: 1, polarRate: 0, zoomRate: 0, panXRate: 0, panYRate: 0 }
    const limits = { minDistance: 1, maxDistance: 999, minPolar: 0.1, maxPolar: 1.5 }
    const a = integrateHandCamera(state, rates, 0.5, { ...limits, azimuthSpeed: slow.azimuthSpeed, polarSpeed: 1, zoomSpeed: 1 })
    const b = integrateHandCamera(state, rates, 0.5, { ...limits, azimuthSpeed: fast.azimuthSpeed, polarSpeed: 1, zoomSpeed: 1 })
    expect(Math.abs(b.azimuth)).toBeGreaterThan(Math.abs(a.azimuth))
  })

  it('a wider deadzone silences a small hand offset that a narrow one would act on', () => {
    const narrow = resolveHandTuning([handSetting('hand.deadzone', 0.02)])
    const wide = resolveHandTuning([handSetting('hand.deadzone', 0.35)])
    // azimuthNorm is already deadzoned upstream; verticalOffset (derived from
    // polarNorm) is what mapSignalToRates re-deadzones with the config, so
    // drive that: polarNorm 0.42 -> a small 0.16 offset from centre, inside a
    // 0.35 deadzone but outside a 0.02 one.
    const signal = { azimuthNorm: 0, polarNorm: 0.42, zoomNorm: 0 }
    const narrowRates = mapSignalToRates(signal, 'control', narrow.config)
    const wideRates = mapSignalToRates(signal, 'control', wide.config)
    expect(Math.abs(wideRates.polarRate)).toBeLessThan(Math.abs(narrowRates.polarRate))
  })

  it('a longer latch hold makes the 👍 start/stop gesture take longer to fire', () => {
    const quick = resolveHandTuning([handSetting('hand.latch_hold_seconds', 0.1)])
    const slow = resolveHandTuning([handSetting('hand.latch_hold_seconds', 2)])
    const quickLatch = createGestureLatch()
    const slowLatch = createGestureLatch()
    expect(stepGestureLatch(quickLatch, true, 0.2, quick.latchHoldSeconds)).toBe(true)
    expect(stepGestureLatch(slowLatch, true, 0.2, slow.latchHoldSeconds)).toBe(false)
  })
})
