import { afterEach, describe, expect, it, vi } from 'vitest'
import { TABLETOP_SPAN_M, isXrModeSupported, scaleRatioLabel, tabletopScale } from '../xr'

afterEach(() => {
  delete (navigator as unknown as Record<string, unknown>).xr
})

describe('isXrModeSupported', () => {
  it('is false where navigator.xr is absent entirely - every iPhone, every plain desktop', () => {
    // Returning false rather than throwing is the point: the caller renders
    // nothing, and an exception would make that harder rather than clearer.
    return expect(isXrModeSupported('immersive-ar')).resolves.toBe(false)
  })

  it('asks per mode, because AR and VR are different answers on one device', async () => {
    const isSessionSupported = vi.fn(async (mode: string) => mode === 'immersive-vr')
    ;(navigator as unknown as Record<string, unknown>).xr = { isSessionSupported }
    await expect(isXrModeSupported('immersive-ar')).resolves.toBe(false)
    await expect(isXrModeSupported('immersive-vr')).resolves.toBe(true)
    expect(isSessionSupported).toHaveBeenCalledTimes(2)
  })

  it('treats a rejected probe as unsupported rather than letting it escape', async () => {
    ;(navigator as unknown as Record<string, unknown>).xr = {
      isSessionSupported: async () => {
        throw new Error('unknown mode')
      },
    }
    await expect(isXrModeSupported('immersive-ar')).resolves.toBe(false)
  })
})

describe('tabletopScale', () => {
  it('maps the site onto a tabletop rather than leaving it life-size', () => {
    // 240 m of array has to fit in 0.6 m, or an AR visitor stands inside a
    // structure bigger than the room.
    expect(tabletopScale(240)).toBeCloseTo(TABLETOP_SPAN_M / 240)
    expect(tabletopScale(240) * 240).toBeCloseTo(TABLETOP_SPAN_M)
  })

  it('falls back to 1:1 for a missing or nonsense span instead of collapsing the scene', () => {
    expect(tabletopScale(0)).toBe(1)
    expect(tabletopScale(-5)).toBe(1)
    expect(tabletopScale(Number.NaN)).toBe(1)
  })
})

describe('scaleRatioLabel', () => {
  it('prints a ratio a person can read', () => {
    expect(scaleRatioLabel(240)).toBe('1 : 400')
    expect(scaleRatioLabel(60)).toBe('1 : 100')
  })

  it('says 1:1 when there is nothing to scale, rather than dividing by zero', () => {
    expect(scaleRatioLabel(0)).toBe('1 : 1')
  })
})
