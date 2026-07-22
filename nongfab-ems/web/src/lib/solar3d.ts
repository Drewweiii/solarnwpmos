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

/** Interpolates a compass azimuth from `fromDeg` to `toDeg` by fraction `t`,
 * always taking the shorter arc around the 0/360 circle (the true direction
 * a celestial body moves between two close-in-time samples) rather than the
 * naive numeric path. Folds any azimuth difference into (-180, 180] first,
 * so 350deg -> 10deg reads as +20deg (forward through north) not -340deg,
 * and 10deg -> 350deg reads as -20deg (backward through north) not +340deg.
 * The returned angle is normalized back into [0, 360). Exported so the same
 * wrap-safe blend is unit-testable in isolation (see solar3d.test.ts). */
export function interpolateAzimuthDeg(fromDeg: number, toDeg: number, t: number): number {
  let delta = ((toDeg - fromDeg) % 360 + 540) % 360 - 180
  const raw = fromDeg + delta * t
  return ((raw % 360) + 360) % 360
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
 * empty `points` array too.
 *
 * Azimuth is interpolated the SHORT way around the compass (see
 * `interpolateAzimuthDeg`), not by a naive numeric lerp - without this, a
 * body crossing due north between two samples (e.g. 355deg -> 5deg, which
 * both the summer Sun and the Moon really do near their meridian transit at
 * this near-equatorial latitude) would sweep the marker *backward* across
 * the entire sky (355 -> 180 -> 5) in a single 15-minute step instead of
 * the 10deg forward nudge it should be. That backward sweep was the Moon's
 * visible "jerks weirdly" glitch the user reported 2026-07-18; fixing it
 * here fixes it identically for both markers (they share this function), so
 * the Sun and Moon now rise, transit, and set with the same smooth,
 * same-direction motion. */
// /sun-path returns only elevation>0 samples (see routes_solar3d.py's own
// docstring) at a nominal 15-minute cadence - but since that filter is
// applied to a fixed UTC calendar day, the *kept* points routinely jump
// straight from today's last pre-sunset sample to the next day's first
// post-sunrise sample (both can land within the same 00:00-23:45Z window
// whenever local sunrise falls close to UTC midnight, as it does for
// Thailand/ICT). Found live 2026-07-19: a target time that falls in that
// removed overnight gap still satisfies the first/last bounds check below
// (it's still within [points[0].time, points[-1].time] *overall*), so the
// loop below found the two samples bracketing sunset and the next sunrise
// - many hours apart - and happily linearly interpolated a small *positive*
// elevation across the entire night between them. That's what caused the
// Sun marker to stay visible (and drift) long after sunset instead of
// disappearing, and in turn kept MoonMarker's "sun is down" check from ever
// turning true. A genuine adjacent 15-minute sample pair is never more than
// a few minutes apart in practice - anything past this threshold means the
// two points straddle a real gap in the data, not consecutive samples, so
// treat it the same as "outside the covered range" (null) rather than
// interpolating across it.
const MAX_ADJACENT_SAMPLE_GAP_MS = 20 * 60 * 1000

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
      if (bMs - aMs > MAX_ADJACENT_SAMPLE_GAP_MS) return null
      const t = bMs === aMs ? 0 : (targetMs - aMs) / (bMs - aMs)
      return {
        azimuthDeg: interpolateAzimuthDeg(a.azimuth_deg, b.azimuth_deg, t),
        elevationDeg: a.elevation_deg + (b.elevation_deg - a.elevation_deg) * t,
      }
    }
  }
  // Unreachable given the bounds check above, but keeps the return type
  // total rather than possibly-undefined.
  const last = points[points.length - 1]
  return { azimuthDeg: last.azimuth_deg, elevationDeg: last.elevation_deg }
}

/** Thai name for a lunar phase from its lit fraction (0..1) and waxing flag -
 * labels the 3D view's moon marker so a daytime/early crescent reads as an
 * intended phase, not a rendering glitch (the "why is a half-moon up in the
 * afternoon" confusion, 2026-07-19). Thresholds are the conventional phase
 * bands; `waxing` only distinguishes the growing vs shrinking quarter/crescent/
 * gibbous names, and is irrelevant at the new/full extremes. */
export function moonPhaseName(illumination: number, waxing: boolean): string {
  const k = Math.max(0, Math.min(1, illumination))
  if (k < 0.04) return 'จันทร์ดับ (New Moon)'
  if (k > 0.96) return 'จันทร์เต็มดวง (Full Moon)'
  if (k < 0.46) return waxing ? 'จันทร์เสี้ยวข้างขึ้น (Waxing Crescent)' : 'จันทร์เสี้ยวข้างแรม (Waning Crescent)'
  if (k <= 0.54) return waxing ? 'จันทร์ครึ่งดวงข้างขึ้น (First Quarter)' : 'จันทร์ครึ่งดวงข้างแรม (Last Quarter)'
  return waxing ? 'จันทร์ค่อนดวงข้างขึ้น (Waxing Gibbous)' : 'จันทร์ค่อนดวงข้างแรม (Waning Gibbous)'
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

// 111,320 m is the standard equirectangular-projection constant for one
// degree of latitude (WGS84 mean); longitude's own meters-per-degree is
// scaled by cos(latitude) since meridians converge toward the poles.
const METERS_PER_DEG_LAT = 111_320

/** Approximate flat-earth (equirectangular tangent-plane) projection of a
 * (lat, lon) point into local east/north meters relative to an origin point
 * - good to well under 1% error at the <2km scale this plant spans (see
 * `nongfab_features.panel_geometry`'s own docstring, which documents the
 * exact same approximation server-side to lay out each zone's panels
 * relative to that zone's own surveyed centroid; `Panel.east_m`/`north_m`
 * are the output of that same math). Passing a zone's own centroid as
 * `originLat`/`originLon` is what lets an irradiance grid point (real
 * lat/lon, from GET /irradiance-map) land in the exact same local frame a
 * `Panel` already uses, so both can share one ground plane with no further
 * conversion - added 2026-07-18 to merge the separate MapLibre irradiance
 * map into this scene as colored ground points (see Solar3DScene.tsx's
 * IrradianceGroundOverlay), per the user's own explicit request. */
export function latLonToLocalMeters(
  lat: number,
  lon: number,
  originLat: number,
  originLon: number,
): { eastM: number; northM: number } {
  const metersPerDegLon = METERS_PER_DEG_LAT * Math.cos((originLat * Math.PI) / 180)
  return {
    eastM: (lon - originLon) * metersPerDegLon,
    northM: (lat - originLat) * METERS_PER_DEG_LAT,
  }
}

// Same 4-stop blue -> amber -> red ramp (0 / 300 / 600 / 1000 W/m^2) the
// former standalone MapLibre irradiance-map overlay used for its
// `circle-color` paint expression - reused as-is (not redesigned) so the
// merged-into-3D ground overlay reads with the same color meaning a viewer
// may already associate with "clear sky blue -> hazy amber -> intense red".
const IRRADIANCE_COLOR_STOPS: [number, [number, number, number]][] = [
  [0, [30, 58, 138]], // #1e3a8a
  [300, [37, 99, 235]], // #2563eb
  [600, [245, 158, 11]], // #f59e0b
  [1000, [239, 68, 68]], // #ef4444
]

/** Linearly interpolated color for a GHI reading (W/m^2), clamped to the
 * [0, 1000] display range `MAX_DISPLAY_GHI_W_M2` (irradiance_map.py) already
 * clips server-side - see `IRRADIANCE_COLOR_STOPS`'s own docstring for where
 * the 4 stops come from. Returns an `rgb(...)` CSS/Three.js-color-compatible
 * string. */
export function irradianceGhiColor(ghiWm2: number): string {
  const clamped = Math.max(0, Math.min(1000, ghiWm2))
  for (let i = 0; i < IRRADIANCE_COLOR_STOPS.length - 1; i++) {
    const [fromVal, fromRgb] = IRRADIANCE_COLOR_STOPS[i]
    const [toVal, toRgb] = IRRADIANCE_COLOR_STOPS[i + 1]
    if (clamped >= fromVal && clamped <= toVal) {
      const t = toVal === fromVal ? 0 : (clamped - fromVal) / (toVal - fromVal)
      const r = Math.round(fromRgb[0] + (toRgb[0] - fromRgb[0]) * t)
      const g = Math.round(fromRgb[1] + (toRgb[1] - fromRgb[1]) * t)
      const b = Math.round(fromRgb[2] + (toRgb[2] - fromRgb[2]) * t)
      return `rgb(${r}, ${g}, ${b})`
    }
  }
  const lastRgb = IRRADIANCE_COLOR_STOPS[IRRADIANCE_COLOR_STOPS.length - 1][1]
  return `rgb(${lastRgb[0]}, ${lastRgb[1]}, ${lastRgb[2]})`
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
