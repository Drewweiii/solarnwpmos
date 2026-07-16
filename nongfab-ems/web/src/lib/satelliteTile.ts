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
