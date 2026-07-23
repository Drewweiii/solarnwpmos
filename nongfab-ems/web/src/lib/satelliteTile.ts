// Satellite ground texture for the 3D view's "satellite" ground style -
// the reslink.org reference video's photorealistic mode. This sandbox
// blocks every map/tile provider's domain outright (arcgisonline.com,
// mapbox.com, maptiler.com, tile.openstreetmap.org - confirmed via the
// agent proxy's own diagnostics: 403 at the CONNECT tunnel for all of
// them, same restriction that blocked reslink.org itself and NASA POWER
// earlier in this project - see forecast/README.md's own "not live-
// verified" precedent for UV ingestion). This module is written and unit-
// tested (the pure tile-math below), but the actual image fetch
// (SatelliteGroundPlane in Solar3DScene.tsx) has never been confirmed to
// load a real tile from this environment - only confirmed once this
// deploys somewhere with real egress.
//
// Esri World Imagery was chosen because it's keyless (no API token/account
// needed, unlike Mapbox/MapTiler) - reachable at
// https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer,
// under Esri's "basic" free-tier ToS for this kind of low-volume,
// non-cached display use.

const TILE_SIZE_PX = 256

/** Standard Web Mercator slippy-map tile indices for a (lat, lon) at a given
 * zoom - https://en.wikipedia.org/wiki/Tiled_web_map#Programming. Valid for
 * |lat| < ~85.05 (Web Mercator's own latitude limit) - Nong Fab's ~12.7N is
 * nowhere near that bound. */
export function latLonToTile(lat: number, lon: number, zoom: number): { x: number; y: number; z: number } {
  const latRad = (lat * Math.PI) / 180
  const n = 2 ** zoom
  const x = Math.floor(((lon + 180) / 360) * n)
  const y = Math.floor(((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n)
  return { x: Math.max(0, Math.min(n - 1, x)), y: Math.max(0, Math.min(n - 1, y)), z: zoom }
}

/** Ground resolution (meters/pixel) at a given zoom and latitude - used to
 * decide how big a single tile's real-world footprint is, so the ground
 * plane this texture is applied to is sized in the same ballpark (not
 * pixel-perfect georeferencing - a single square tile approximated as a
 * flat local patch, same "documented approximation, not survey-grade"
 * pattern as this app's other geometry assumptions). Formula:
 * https://wiki.openstreetmap.org/wiki/Zoom_levels */
export function metersPerPixel(lat: number, zoom: number): number {
  const EARTH_CIRCUMFERENCE_M = 40075016.686
  return (EARTH_CIRCUMFERENCE_M * Math.cos((lat * Math.PI) / 180)) / 2 ** (zoom + 8)
}

/** The real-world width/height (meters) a single tile covers at (lat, zoom). */
export function tileFootprintMeters(lat: number, zoom: number): number {
  return metersPerPixel(lat, zoom) * TILE_SIZE_PX
}

// z=17: ~1.17m/px at this latitude, a single tile covers ~300m x 300m -
// comfortably larger than GIS/ISB's own panel-array footprint (tens of
// meters), so the texture covers the whole zone rather than just a corner
// of it, while still resolving individual rooftops. This is a single-tile
// visual approximation, not a georeferencing tool - Jetty's ~1.25km
// trestle span is still far bigger than one tile either way, so its
// texture only ever covers the central portion of the layout, by design
// (stitching multiple tiles together is a follow-up, not attempted here).
export const DEFAULT_SATELLITE_ZOOM = 17

export function esriWorldImageryTileUrl(lat: number, lon: number, zoom: number = DEFAULT_SATELLITE_ZOOM): string {
  const { x, y, z } = latLonToTile(lat, lon, zoom)
  return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`
}

export interface SatelliteTile {
  url: string
  /** meters east of the grid center - where to place this tile's plane. */
  offsetEastM: number
  /** meters north of the grid center. */
  offsetNorthM: number
  /** this tile's real-world footprint size (meters, square). */
  sizeM: number
}

/** A `cols` x `rows` grid of Esri tiles centered on (lat, lon), for covering an
 * area larger than one tile - e.g. Jetty's long north-south trestle, which at a
 * single z17 tile (~300 m) can't span the array's ~1.25 km extent. `cols` is
 * the east-west count, `rows` the north-south count; both are clamped to a sane
 * odd >= 1 so the grid stays centered on the middle tile. Each returned tile
 * carries its own scene offset in meters (east/north) so the caller can lay the
 * planes out edge-to-edge. Pure math (same "documented approximation, not
 * survey-grade georeferencing" bar as the single-tile helpers above) - the
 * actual image fetch still pends a deploy with real egress (see this module's
 * top docstring; tile providers are blocked in the dev sandbox). */
export function esriWorldImageryTileGrid(
  lat: number,
  lon: number,
  cols: number,
  rows: number,
  zoom: number = DEFAULT_SATELLITE_ZOOM,
): SatelliteTile[] {
  const oddClamp = (v: number) => {
    const n = Math.max(1, Math.floor(v))
    return n % 2 === 0 ? n + 1 : n
  }
  const c = oddClamp(cols)
  const r = oddClamp(rows)
  const { x: cx, y: cy, z } = latLonToTile(lat, lon, zoom)
  const footprint = tileFootprintMeters(lat, zoom)
  const maxIndex = 2 ** z - 1
  const tiles: SatelliteTile[] = []
  for (let j = 0; j < r; j++) {
    for (let i = 0; i < c; i++) {
      const di = i - (c - 1) / 2
      const dj = j - (r - 1) / 2
      const tileX = Math.max(0, Math.min(maxIndex, cx + di))
      const tileY = Math.max(0, Math.min(maxIndex, cy + dj))
      tiles.push({
        url: `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${tileY}/${tileX}`,
        offsetEastM: di * footprint,
        // Tile y grows southward, so a higher dj means further south (-north).
        offsetNorthM: -dj * footprint,
        sizeM: footprint,
      })
    }
  }
  return tiles
}
