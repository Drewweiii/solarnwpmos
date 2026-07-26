/** Turning the 3D scene's light into something that casts (2026-07-26, project L).
 *
 * The scene already positions its directional light at the REAL solar position
 * for the instant being viewed, and already scales its intensity by
 * sin(elevation). What it never did was cast a shadow: `castShadow` appeared
 * only on the mascot's body meshes, so the panels floated in a world where
 * nothing blocked the sun.
 *
 * Switching shadows on makes INTER-ROW SELF-SHADING appear for free, and that
 * shadow is physically real: it comes from surveyed panel corners, the real row
 * pitch, the real tilt and the real sun vector - the same geometry
 * `annual_shading_loss_pct` already turns into a loss percentage. This is the
 * first time the number and the picture describe the same thing.
 *
 * WHAT CLOUDS CAN AND CANNOT DO HERE. The site's cloud data is ONE site-wide
 * opacity scalar plus a motion vector - there is no spatial raster anywhere the
 * app can reach (the per-pixel Himawari tiles live in MinIO, which Railway is
 * not wired to; see CloudLayer's and routes_irradiance_map's own docstrings).
 * So cloud cover DIMS THE WHOLE SITE here and does not cast a shaped shadow.
 * Drawing a cloud-shadow edge crossing the rows would be inventing spatial
 * detail the data does not have - fabrication carried out in pixels rather
 * than in numbers, which this project forbids either way.
 */

/** Direct sun vs. sky light, as multipliers the scene applies to its two lights. */
export interface SceneLighting {
  /** Scales the sun's own directional light - the one that casts shadows. */
  directional: number
  /** Ambient/sky fill. Rises as the sun's share falls: an overcast sky is not
   * darker so much as SOFTER, and dropping the direct light without lifting the
   * fill would render a cloudy noon as dusk. */
  ambient: number
}

/** Fully overcast still leaves real light on the ground - diffuse light through
 * thick cloud is typically 10-25% of clear-sky GHI, never zero. Killing the
 * directional term entirely would also kill the shadows abruptly at 100%
 * cloud, which reads as a rendering glitch rather than as weather. */
const MIN_DIRECTIONAL_FRACTION = 0.15

/** Ambient at clear sky and at full overcast. The rise is what keeps an
 * overcast scene readable instead of merely dark. */
const AMBIENT_CLEAR = 0.6
const AMBIENT_OVERCAST = 0.95

/** How much sun and sky to use for a given cloud cover.
 *
 * `opacityPct` is the site-wide Himawari reading. Null means no reading was
 * available, which must render as clear sky rather than as darkness - an
 * ingestion gap is not weather.
 */
export function lightingForCloudCover(opacityPct: number | null): SceneLighting {
  if (opacityPct === null || !Number.isFinite(opacityPct)) {
    return { directional: 1, ambient: AMBIENT_CLEAR }
  }
  const cover = Math.min(100, Math.max(0, opacityPct)) / 100
  return {
    directional: 1 - (1 - MIN_DIRECTIONAL_FRACTION) * cover,
    ambient: AMBIENT_CLEAR + (AMBIENT_OVERCAST - AMBIENT_CLEAR) * cover,
  }
}

/** Half-width of the sun light's orthographic shadow camera.
 *
 * A directional light's shadow only exists inside this box, so it has to cover
 * the array - but every metre of slack spends shadow-map resolution on empty
 * ground, and a box sized to the whole scene turns crisp row shadows into a
 * grey smear. The margin is generous enough for long shadows at low sun
 * without being generous enough to blur them.
 */
export function shadowCameraExtent(sceneSpan: number): number {
  return Math.max(20, sceneSpan * 0.85)
}

/** Whether shadows are worth rendering at all for this sun elevation.
 *
 * Below the horizon there is no sun to cast from, and within a couple of
 * degrees of it the shadows stretch to many times the array's own size, which
 * costs the whole shadow map to render a smear nobody can read. Returning false
 * at night is also what stops the moon-lit scene from showing sunlit shadows.
 */
export function shadowsWorthRendering(sunElevationDeg: number): boolean {
  return sunElevationDeg > 3
}
