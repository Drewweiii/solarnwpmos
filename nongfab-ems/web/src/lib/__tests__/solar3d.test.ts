import { describe, expect, it } from 'vitest'
import { compassLabel, solarAccessColor, sunPositionVector } from '../solar3d'

describe('compassLabel', () => {
  it('maps the 8 cardinal/intercardinal directions', () => {
    expect(compassLabel(0)).toBe('N')
    expect(compassLabel(45)).toBe('NE')
    expect(compassLabel(90)).toBe('E')
    expect(compassLabel(135)).toBe('SE')
    expect(compassLabel(180)).toBe('S')
    expect(compassLabel(225)).toBe('SW')
    expect(compassLabel(270)).toBe('W')
    expect(compassLabel(315)).toBe('NW')
  })

  it('normalizes angles outside [0, 360)', () => {
    expect(compassLabel(360)).toBe('N')
    expect(compassLabel(-45)).toBe('NW')
    expect(compassLabel(720 + 90)).toBe('E')
  })
})

describe('solarAccessColor', () => {
  it('is red at 0% and green at 100%', () => {
    expect(solarAccessColor(0)).toBe('hsl(0, 85%, 45%)')
    expect(solarAccessColor(100)).toBe('hsl(120, 85%, 45%)')
  })

  it('is yellow-ish at 50%', () => {
    expect(solarAccessColor(50)).toBe('hsl(60, 85%, 45%)')
  })

  it('clamps out-of-range input', () => {
    expect(solarAccessColor(-10)).toBe(solarAccessColor(0))
    expect(solarAccessColor(150)).toBe(solarAccessColor(100))
  })
})

describe('sunPositionVector', () => {
  it('places a due-north, horizon-level sun on -Z', () => {
    const [x, y, z] = sunPositionVector(0, 0, 10)
    expect(x).toBeCloseTo(0)
    expect(y).toBeCloseTo(0)
    expect(z).toBeCloseTo(-10)
  })

  it('places a due-east, horizon-level sun on +X', () => {
    const [x, y, z] = sunPositionVector(90, 0, 10)
    expect(x).toBeCloseTo(10)
    expect(y).toBeCloseTo(0)
    expect(z).toBeCloseTo(0)
  })

  it('places an overhead sun straight up regardless of azimuth', () => {
    const [x, y, z] = sunPositionVector(180, 90, 10)
    expect(x).toBeCloseTo(0)
    expect(y).toBeCloseTo(10)
    expect(z).toBeCloseTo(0, 4)
  })
})
