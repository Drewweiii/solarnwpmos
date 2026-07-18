// Pure geometry/color helpers for Feature B/C (3D solar-access view + sun-path
// sweep) - kept free of react-three-fiber/Three.js so they're plain,
// fast-to-test functions; Solar3DScene.tsx is the only place that touches an
// actual WebGL canvas (not unit-testable in jsdom - see its own file header).

const COMPASS_POINTS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'] as const

/** 8-point compass label for a compass-bearing azimuth (0=N, 90=E, ...). */
export function compassLabel(azimuthDeg: number): string {
  const normalized = ((azimuthDeg % 360) + 360) % 360
  const index = Math.round(normalized / 45) % 8
  return COMPASS_POINTS[index]
}

/** Red (0%) -> yellow (50%) -> green (100%) - the same low/high sense as
 * the irradiance heatmap reference screenshots this feature is modeled on. */
export function solarAccessColor(solarAccessPct: number): string {
  const clamped = Math.max(0, Math.min(100, solarAccessPct))
  const hue = (clamped / 100) * 120
  return `hsl(${hue}, 85%, 45%)`
}

interface TimedAngle {
  time: string
  azimuth_deg: number
  elevation_deg: number
}

/** Linearly interpolates azimuth/elevation between the two `points` (sorted
 * ascending by `time`, as `/sun-path` already returns them) bracketing
 * `atIso` - what makes the 3D view's sun glide continuously between the
 * endpoint's 15-minute samples instead of visibly snapping from one to the
 * next (the "laggy"/stepped animation the user reported live 2026-07-18).
 * `points` only covers daylight (`elevation_deg > 0`, see routes_solar3d.
 * py's own `/sun-path` docstring) - `atIso` outside that covered range
 * (before sunrise or after sunset) returns `null` rather than clamping to
 * the first/last point, so a caller doesn't mistake "no data past sunset"
 * for "the sun is still up at the sunset position". Returns `null` for an
 * empty `points` array too. */
export function interpolateSunPosition(points: TimedAngle[], atIso: string): { azimuthDeg: number; elevationDeg: number } | null {
  if (points.length === 0) return null
  const targetMs = new Date(atIso).getTime()
  const firstMs = new Date(points[0].time).getTime()
  const lastMs = new Date(points[points.length - 1].time).getTime()
  if (targetMs < firstMs || targetMs > lastMs) return null
  if (points.length === 1) return { azimuthDeg: points[0].azimuth_deg, elevationDeg: points[0].elevation_deg }

  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i]
    const b = points[i + 1]
    const aMs = new Date(a.time).getTime()
    const bMs = new Date(b.time).getTime()
    if (targetMs >= aMs && targetMs <= bMs) {
      const t = bMs === aMs ? 0 : (targetMs - aMs) / (bMs - aMs)
      return {
        azimuthDeg: a.azimuth_deg + (b.azimuth_deg - a.azimuth_deg) * t,
        elevationDeg: a.elevation_deg + (b.elevation_deg - a.elevation_deg) * t,
      }
    }
  }
  // Unreachable given the bounds check above, but keeps the return type
  // total rather than possibly-undefined.
  const last = points[points.length - 1]
  return { azimuthDeg: last.azimuth_deg, elevationDeg: last.elevation_deg }
}

/** 90 - elevation: the angle from directly overhead (zenith), the
 * complementary way solar position is often quoted alongside elevation/
 * altitude (see e.g. any standard sun-position diagram) - shown on
 * Solar3DPage per the user's own 2026-07-18 request. Negative below the
 * horizon, same sign convention as a negative elevation. */
export function zenithAngleDeg(elevationDeg: number): number {
  return 90 - elevationDeg
}

/** Advances a simulated "play" clock by `deltaSeconds` of real time (at
 * `simMinutesPerRealSecond` sim-minutes per real second), wrapping back to
 * `wrapStartMs` once it passes `wrapEndMs` - the shared clock driving both
 * SunMarker's and MoonMarker's continuous in-canvas animation in
 * Solar3DScene.tsx (2026-07-18, added so the Moon can rise once the Sun
 * sets during Play - see that file's own docstring on why both markers now
 * share one 24h wrap window instead of the Sun's old daylight-only loop).
 * Kept here, not inline in either marker, so both advance off the exact
 * same arithmetic (same `delta` each frame -> identical result) and so this
 * is unit-testable at all (react-three-fiber's `useFrame` itself is not,
 * per this file's own header). Returns `currentMs + delta` unwrapped if the
 * wrap window is empty/invalid (e.g. no path data loaded yet). */
export function advanceSimClockMs(
  currentMs: number,
  deltaSeconds: number,
  simMinutesPerRealSecond: number,
  wrapStartMs: number | null,
  wrapEndMs: number | null,
): number {
  const advanced = currentMs + deltaSeconds * simMinutesPerRealSecond * 60 * 1000
  if (wrapStartMs == null || wrapEndMs == null) return advanced
  const spanMs = wrapEndMs - wrapStartMs
  if (spanMs <= 0) return advanced
  if (advanced <= wrapEndMs) return advanced
  return wrapStartMs + ((advanced - wrapStartMs) % spanMs)
}

/** Converts a compass azimuth + elevation into a 3D Cartesian point (east=X,
 * up=Y, north=-Z - the same axis convention Solar3DScene.tsx uses for panel
 * positions, so the sun marker/sun-path arc line up with the panel grid
 * without any extra per-scene conversion). `radius` is purely a visualization
 * scale (how far out to place the point along that direction), not a
 * physical distance.
 */
export function sunPositionVector(azimuthDeg: number, elevationDeg: number, radius: number): [number, number, number] {
  const az = (azimuthDeg * Math.PI) / 180
  const el = (elevationDeg * Math.PI) / 180
  const horizontal = radius * Math.cos(el)
  const x = horizontal * Math.sin(az)
  const z = -horizontal * Math.cos(az)
  const y = radius * Math.sin(el)
  return [x, y, z]
}

/** Points along an azimuth/altitude/zenith-angle protractor arc on the
 * sun's "sky dome" (see `sunPositionVector`), linearly sweeping azimuth and
 * elevation together from (azFromDeg, elFromDeg) to (azToDeg, elToDeg) -
 * used to draw Solar3DScene's in-scene angle-measurement diagram (2026-07-18
 * user request, sun only - "ตรงเส้น3Dให้แสดงการวัดมุมเข้าไปด้วย...มีมุม
 * azimuth, altitude, zenith angle"). A plain linear sweep in (az, el) space,
 * not a true spherical geodesic - visually indistinguishable at the short
 * sweep angles these diagrams use (each arc covers at most 90deg), and far
 * simpler than a real slerp for a purely decorative protractor. */
export function angleArcPoints(
  azFromDeg: number,
  azToDeg: number,
  elFromDeg: number,
  elToDeg: number,
  radius: number,
  segments = 32,
): [number, number, number][] {
  const points: [number, number, number][] = []
  for (let i = 0; i <= segments; i++) {
    const t = i / segments
    const az = azFromDeg + (azToDeg - azFromDeg) * t
    const el = elFromDeg + (elToDeg - elFromDeg) * t
    points.push(sunPositionVector(az, el, radius))
  }
  return points
}
