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
