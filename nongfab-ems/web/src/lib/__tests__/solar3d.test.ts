import { describe, expect, it } from 'vitest'
import {
  advanceSimClockMs,
  angleArcPoints,
  compassLabel,
  interpolateSunPosition,
  irradianceGhiColor,
  latLonToLocalMeters,
  solarAccessColor,
  sunPositionVector,
  zenithAngleDeg,
} from '../solar3d'

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

describe('zenithAngleDeg', () => {
  it('is 0 straight overhead and 90 at the horizon', () => {
    expect(zenithAngleDeg(90)).toBe(0)
    expect(zenithAngleDeg(0)).toBe(90)
  })

  it('goes negative below the horizon, matching a negative elevation', () => {
    expect(zenithAngleDeg(-10)).toBe(100)
  })
})

describe('interpolateSunPosition', () => {
  const points = [
    { time: '2026-07-18T00:00:00Z', azimuth_deg: 80, elevation_deg: 0 },
    { time: '2026-07-18T00:15:00Z', azimuth_deg: 90, elevation_deg: 10 },
    { time: '2026-07-18T00:30:00Z', azimuth_deg: 100, elevation_deg: 20 },
  ]

  it('returns the exact point when atIso lands exactly on a sample', () => {
    expect(interpolateSunPosition(points, '2026-07-18T00:15:00Z')).toEqual({ azimuthDeg: 90, elevationDeg: 10 })
  })

  it('linearly interpolates halfway between two samples', () => {
    const result = interpolateSunPosition(points, '2026-07-18T00:07:30Z')
    expect(result?.azimuthDeg).toBeCloseTo(85)
    expect(result?.elevationDeg).toBeCloseTo(5)
  })

  it('returns null before the first point (before sunrise) rather than clamping', () => {
    expect(interpolateSunPosition(points, '2026-07-17T23:00:00Z')).toBeNull()
  })

  it('returns null after the last point (after sunset) rather than clamping', () => {
    expect(interpolateSunPosition(points, '2026-07-18T01:00:00Z')).toBeNull()
  })

  it('returns null for an empty points array', () => {
    expect(interpolateSunPosition([], '2026-07-18T00:15:00Z')).toBeNull()
  })

  it('returns the single point directly when only one sample exists', () => {
    expect(interpolateSunPosition([points[1]], '2026-07-18T00:15:00Z')).toEqual({ azimuthDeg: 90, elevationDeg: 10 })
  })

  // Found live 2026-07-19: /sun-path returns only elevation>0 samples, which
  // routinely jump straight from today's last pre-sunset sample to the next
  // day's first post-sunrise sample - both land inside one UTC calendar day
  // whenever local sunrise falls close to UTC midnight (true for Thailand).
  // A target time in that removed overnight gap used to still pass the
  // first/last bounds check (it's within the *overall* first/last range)
  // and get linearly interpolated across the two far-apart bracketing
  // samples, producing a fictional small-positive elevation for the whole
  // night - which kept the Sun marker visible long after sunset and, in
  // turn, kept MoonMarker's "sun is down" check from ever turning true.
  it('returns null for a target time that falls in an overnight gap between elevation-filtered samples, even though it is within the array\'s overall first/last bounds', () => {
    const overnightGapPoints = [
      { time: '2026-07-19T00:00:00Z', azimuth_deg: 71, elevation_deg: 13 },
      { time: '2026-07-19T11:15:00Z', azimuth_deg: 290, elevation_deg: 6 },
      // Real sunset sample - the next kept sample jumps to tomorrow's sunrise.
      { time: '2026-07-19T11:30:00Z', azimuth_deg: 291, elevation_deg: 2.6 },
      { time: '2026-07-19T23:15:00Z', azimuth_deg: 69, elevation_deg: 2.9 }, // next day's sunrise creeping into this UTC day
      { time: '2026-07-19T23:45:00Z', azimuth_deg: 71, elevation_deg: 10 },
    ]
    // Squarely in the middle of the night, ~1 hour after sunset.
    expect(interpolateSunPosition(overnightGapPoints, '2026-07-19T12:30:00Z')).toBeNull()
  })

  it('still interpolates normally between two genuinely-adjacent 15-minute samples near the edge of an overnight gap', () => {
    const overnightGapPoints = [
      { time: '2026-07-19T11:15:00Z', azimuth_deg: 290, elevation_deg: 6 },
      { time: '2026-07-19T11:30:00Z', azimuth_deg: 291, elevation_deg: 2.6 },
      { time: '2026-07-19T23:15:00Z', azimuth_deg: 69, elevation_deg: 2.9 },
    ]
    const result = interpolateSunPosition(overnightGapPoints, '2026-07-19T11:22:30Z')
    expect(result?.elevationDeg).toBeCloseTo(4.3, 1)
  })
})

describe('advanceSimClockMs', () => {
  const start = Date.parse('2026-07-18T00:00:00Z')
  const end = Date.parse('2026-07-19T00:00:00Z') // a full 24h wrap window

  it('advances by delta * sim-minutes-per-real-second, unwrapped', () => {
    // 1 real second at 15 sim-min/real-sec = 15 sim-minutes forward
    const next = advanceSimClockMs(start, 1, 15, start, end)
    expect(next).toBe(start + 15 * 60 * 1000)
  })

  it('wraps back to wrapStartMs once it passes wrapEndMs, carrying the overshoot', () => {
    const justBeforeEnd = end - 5 * 60 * 1000 // 5 minutes before the wrap boundary
    // 1 real second advances 15 sim-minutes, overshooting the boundary by 10
    const next = advanceSimClockMs(justBeforeEnd, 1, 15, start, end)
    expect(next).toBe(start + 10 * 60 * 1000)
  })

  it('lands exactly on wrapEndMs without wrapping (boundary is inclusive)', () => {
    const next = advanceSimClockMs(end, 0, 15, start, end)
    expect(next).toBe(end)
  })

  it('two markers fed identical inputs each frame stay in lockstep', () => {
    let sunMs = start
    let moonMs = start
    for (const delta of [0.5, 0.7, 1.2, 0.3]) {
      sunMs = advanceSimClockMs(sunMs, delta, 15, start, end)
      moonMs = advanceSimClockMs(moonMs, delta, 15, start, end)
    }
    expect(sunMs).toBe(moonMs)
  })

  it('advances unwrapped when the wrap window is null (no path data loaded yet)', () => {
    const next = advanceSimClockMs(start, 2, 15, null, null)
    expect(next).toBe(start + 30 * 60 * 1000)
  })

  it('advances unwrapped when the wrap window is empty/invalid', () => {
    const next = advanceSimClockMs(start, 2, 15, end, start) // end before start
    expect(next).toBe(start + 30 * 60 * 1000)
  })
})

describe('angleArcPoints', () => {
  it('starts and ends exactly at the from/to azimuth+elevation', () => {
    const points = angleArcPoints(0, 90, 0, 45, 10, 4)
    expect(points[0]).toEqual(sunPositionVector(0, 0, 10))
    expect(points[points.length - 1]).toEqual(sunPositionVector(90, 45, 10))
  })

  it('returns segments + 1 points', () => {
    expect(angleArcPoints(0, 90, 0, 0, 10, 8)).toHaveLength(9)
  })

  it('sweeps azimuth only when elevation is held constant (the azimuth arc case)', () => {
    const points = angleArcPoints(0, 40, 0, 0, 10, 4)
    for (const [x, y, z] of points) {
      expect(y).toBeCloseTo(0) // elevation 0 the whole way -> stays at y=0
      expect(x * x + z * z).toBeCloseTo(100) // stays on the radius-10 circle
    }
  })

  it('sweeps elevation only when azimuth is held constant (the altitude/zenith arc case)', () => {
    const points = angleArcPoints(90, 90, 0, 90, 10, 2)
    expect(points[0]).toEqual(sunPositionVector(90, 0, 10))
    expect(points[1]).toEqual(sunPositionVector(90, 45, 10))
    expect(points[2]).toEqual(sunPositionVector(90, 90, 10))
  })

  it('defaults to 32 segments (33 points) when not specified', () => {
    expect(angleArcPoints(0, 10, 0, 10, 10)).toHaveLength(33)
  })
})

describe('latLonToLocalMeters', () => {
  it('is (0, 0) exactly at the origin', () => {
    const { eastM, northM } = latLonToLocalMeters(12.7, 101.1, 12.7, 101.1)
    expect(eastM).toBeCloseTo(0, 6)
    expect(northM).toBeCloseTo(0, 6)
  })

  it('one degree of latitude north is ~111,320m north, 0m east', () => {
    const { eastM, northM } = latLonToLocalMeters(13.7, 101.1, 12.7, 101.1)
    expect(northM).toBeCloseTo(111_320, 0)
    expect(eastM).toBeCloseTo(0, 6)
  })

  it('one degree of longitude east is scaled by cos(originLat), 0m north', () => {
    const originLat = 12.7
    const { eastM, northM } = latLonToLocalMeters(originLat, 102.1, originLat, 101.1)
    expect(eastM).toBeCloseTo(111_320 * Math.cos((originLat * Math.PI) / 180), 0)
    expect(northM).toBeCloseTo(0, 6)
  })

  it('south/west of the origin comes back negative', () => {
    const { eastM, northM } = latLonToLocalMeters(12.6, 101.0, 12.7, 101.1)
    expect(eastM).toBeLessThan(0)
    expect(northM).toBeLessThan(0)
  })
})

describe('irradianceGhiColor', () => {
  it('matches the 4 documented color stops exactly', () => {
    expect(irradianceGhiColor(0)).toBe('rgb(30, 58, 138)')
    expect(irradianceGhiColor(300)).toBe('rgb(37, 99, 235)')
    expect(irradianceGhiColor(600)).toBe('rgb(245, 158, 11)')
    expect(irradianceGhiColor(1000)).toBe('rgb(239, 68, 68)')
  })

  it('interpolates halfway between two stops', () => {
    expect(irradianceGhiColor(150)).toBe('rgb(34, 79, 187)')
  })

  it('clamps outside [0, 1000]', () => {
    expect(irradianceGhiColor(-50)).toBe(irradianceGhiColor(0))
    expect(irradianceGhiColor(5000)).toBe(irradianceGhiColor(1000))
  })
})
