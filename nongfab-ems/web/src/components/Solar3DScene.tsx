// The actual WebGL canvas for Feature B/C - not unit-testable in jsdom (no
// WebGL context), so this file has no companion test; correctness is
// verified live (see web/README.md "Verified live"). All the testable
// logic (color scale, compass math, sun position) lives in lib/solar3d.ts,
// which this component just calls into.

import { Grid, Line, OrbitControls } from '@react-three/drei'
import { Canvas, useFrame } from '@react-three/fiber'
import { useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import type { Ref } from 'react'
import type { DirectionalLight, Group } from 'three'
import { TextureLoader, type Texture } from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { interpolateSunPosition, solarAccessColor, sunPositionVector } from '../lib/solar3d'
import type { Panel, SunPathPoint } from '../lib/types'

// Exposed to Solar3DPage's icon rail "reset camera" button - React 19 takes
// `ref` as a plain prop (no forwardRef wrapper needed), see this component's
// own signature below.
export interface Solar3DSceneHandle {
  resetCamera: () => void
}

// Floor, not a fixed value: the real orbit radius is scaled to each zone's
// own `bounds.focus.span` below (Jetty's 4 sub-arrays sit tens of km apart
// on a ~1.25km trestle, so a fixed distance tuned for a ~20-30m GIS/ISB
// block either buried the sun marker inside the panels on a huge layout or,
// as reported live 2026-07-18, rendered it as a barely-visible speck once
// the camera itself was framed proportionally further back than this fixed
// number assumed.
const SUN_MARKER_RADIUS_FLOOR_M = 40
// Sun ball radius as a fraction of however far away it actually orbits
// (see `sunOrbitRadius` below) - keeps it a legible, clearly-a-marker size
// at any zone's scale, rather than the old fixed 2m that only happened to
// read as reasonable at the one scale it was tuned against.
const SUN_RADIUS_FRACTION = 0.09
const SUN_GLOW_RADIUS_FRACTION = 0.16

// Simulated sim-minutes advanced per real second while the icon-rail play
// button is on - tuned so a typical Thailand daylight span (~12-13h) glides
// sunrise-to-sunset in roughly 50-55 real seconds (a "watch it sweep" pace,
// not a several-minute wait or a single blink). See SunMarker's own
// docstring for why this now interpolates continuously off `sunPathPoints`
// instead of jumping between fetched geometry snapshots (the "laggy"
// animation reported live 2026-07-18).
const PLAY_SIM_MINUTES_PER_REAL_SECOND = 15
// How often (ms of real time) SunMarker calls `onAnimatedTimeChange` while
// playing - frequent enough that the parent page's slider/readouts feel
// live, far short of every animation frame (60/s) so it doesn't re-trigger
// `useGeometry`'s network fetch or re-render the parent page 60 times/sec.
const SYNC_CALLBACK_INTERVAL_MS = 200

// Not a measured value - config/assets.yaml has no building height for any
// zone (only ground-corner elevation, used for terrain, not structure
// height). A typical single-story industrial/warehouse roof height at a
// facility like this, documented the same way pv_conversion.py's
// temperature coefficient is: a reasonable literature default standing in
// for a real survey that doesn't exist yet.
const BUILDING_HEIGHT_M = 10
// Jetty's real structure is a ~1.25km trestle/pier over water (see
// panel_geometry.py's own docstring) - a solid BUILDING_HEIGHT_M block
// there would misrepresent it as a building that doesn't exist. Rendered as
// a thin elevated deck instead, at a lower height (piers/catwalks sit a few
// meters above water, not building-scale).
const PIER_DECK_HEIGHT_M = 4
const PIER_DECK_THICKNESS_M = 0.6
// GIS is ground-mount, not rooftop - config/assets.yaml's own tilt_deg
// comment already says so ("not measured - SLD is electrical-only; looks
// ground-mount from photos"), confirmed again by the user's own Google
// Earth corner-pin screenshots (2026-07-16): GIS's panel array sits at
// grade in an open yard next to the substation building, not on its roof.
// A solid BUILDING_HEIGHT_M block there would misrepresent a real
// building that isn't under those panels. Typical minimum ground
// clearance under a fixed-tilt ground-mount rack's low edge - not a
// measurement.
const GROUND_MOUNT_CLEARANCE_M = 1.0

type MountType = 'ground' | 'rooftop' | 'pier'

// ISB ("Instrument Substation Building") is the one zone config/assets.
// yaml's own tilt_deg comment calls rooftop ("looks like rooftop tilted
// rows from photos") - it's the BUILDING_HEIGHT_M default below. Jetty is
// the pier. GIS is ground-mount (see GROUND_MOUNT_CLEARANCE_M's own
// docstring). Keyed by zone id, same reasoning as the pier check this
// replaces - see Solar3DSceneProps' own `zone` field docstring.
function mountTypeForZone(zone: string): MountType {
  if (zone === 'Jetty') return 'pier'
  if (zone === 'GIS') return 'ground'
  return 'rooftop'
}

function stringColor(blockId: string): string {
  let hash = 0
  for (let i = 0; i < blockId.length; i++) hash = (hash * 31 + blockId.charCodeAt(i)) >>> 0
  return `hsl(${hash % 360}, 65%, 50%)`
}

interface PanelMeshProps {
  panel: Panel
  tiltDeg: number
  azimuthDeg: number
  color: string
  baseY: number
}

function PanelMesh({ panel, tiltDeg, azimuthDeg, color, baseY }: PanelMeshProps) {
  const tiltRad = (tiltDeg * Math.PI) / 180
  const azimuthRad = (azimuthDeg * Math.PI) / 180
  const thickness = 0.05

  return (
    <group position={[panel.east_m, baseY, -panel.north_m]} rotation={[0, -azimuthRad, 0]}>
      <mesh rotation={[-tiltRad, 0, 0]} position={[0, (panel.slant_height_m / 2) * Math.sin(tiltRad), 0]}>
        <boxGeometry args={[panel.width_m * 0.92, thickness, panel.slant_height_m * 0.92]} />
        <meshStandardMaterial color={color} />
      </mesh>
    </group>
  )
}

interface BuildingMassProps {
  minEast: number
  maxEast: number
  minNorth: number
  maxNorth: number
  mountType: MountType
}

// Roof/deck overhang beyond the panels' own footprint, purely so panel edges
// don't sit flush with (or clip through) the building/deck edge - not a
// measurement.
const FOOTPRINT_MARGIN_M = 2

function BuildingMass({ minEast, maxEast, minNorth, maxNorth, mountType }: BuildingMassProps) {
  const width = maxEast - minEast + FOOTPRINT_MARGIN_M * 2
  const depth = maxNorth - minNorth + FOOTPRINT_MARGIN_M * 2
  const centerEast = (minEast + maxEast) / 2
  const centerNorth = (minNorth + maxNorth) / 2
  const legRadius = 0.4
  const corners: [number, number][] = [
    [minEast, minNorth],
    [minEast, maxNorth],
    [maxEast, minNorth],
    [maxEast, maxNorth],
  ]

  if (mountType === 'ground') {
    // No solid mass at all - GIS's real structure is ground-mount racking
    // in an open yard, not a building (see GROUND_MOUNT_CLEARANCE_M's own
    // docstring). Short corner support legs are the same "this isn't
    // solid ground" visual cue the pier deck uses below, just much shorter.
    return (
      <group>
        {corners.map(([e, n]) => (
          <mesh key={`${e}-${n}`} position={[e, GROUND_MOUNT_CLEARANCE_M / 2, -n]}>
            <cylinderGeometry args={[legRadius * 0.5, legRadius * 0.5, GROUND_MOUNT_CLEARANCE_M, 8]} />
            <meshStandardMaterial color="#374151" />
          </mesh>
        ))}
      </group>
    )
  }

  const isPier = mountType === 'pier'
  const height = isPier ? PIER_DECK_THICKNESS_M : BUILDING_HEIGHT_M
  const baseY = isPier ? PIER_DECK_HEIGHT_M : 0

  return (
    <group>
      <mesh position={[centerEast, baseY + height / 2, -centerNorth]}>
        <boxGeometry args={[width, height, depth]} />
        <meshStandardMaterial color={isPier ? '#4b5563' : '#6b7280'} />
      </mesh>
      {isPier &&
        // Support piles at the deck's 4 corners, purely a visual "this is
        // an elevated pier, not solid ground" cue - not a structural model.
        corners.map(([e, n]) => (
          <mesh key={`${e}-${n}`} position={[e, baseY / 2, -n]}>
            <cylinderGeometry args={[legRadius, legRadius, baseY, 8]} />
            <meshStandardMaterial color="#374151" />
          </mesh>
        ))}
    </group>
  )
}

interface SatelliteGroundPlaneProps {
  tileUrl: string
  center: [number, number]
  size: number
}

// Loads a single Esri World Imagery tile as a ground texture - the
// reslink.org reference video's "photorealistic satellite" ground style
// (see lib/satelliteTile.ts's own docstring for the tile-math/zoom-choice
// rationale and, importantly, its "never confirmed to actually load from
// this environment" caveat). Uses THREE.TextureLoader's callback API
// directly rather than drei's Suspense-based useTexture, specifically so a
// failed/blocked fetch degrades to "render nothing" (the existing grid
// floor underneath stays visible) instead of throwing into a Suspense
// boundary this scene doesn't otherwise need - the one deliberately
// defensive piece of this component, given the fetch is genuinely unverified.
function SatelliteGroundPlane({ tileUrl, center, size }: SatelliteGroundPlaneProps) {
  const [texture, setTexture] = useState<Texture | null>(null)

  useEffect(() => {
    setTexture(null)
    const loader = new TextureLoader()
    loader.setCrossOrigin('anonymous')
    let cancelled = false
    loader.load(
      tileUrl,
      (loaded) => {
        if (!cancelled) setTexture(loaded)
      },
      undefined,
      () => {
        // Blocked/failed fetch - stay null, grid floor remains the fallback.
      },
    )
    return () => {
      cancelled = true
    }
  }, [tileUrl])

  if (!texture) return null

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[center[0], 0.01, -center[1]]}>
      <planeGeometry args={[size, size]} />
      <meshStandardMaterial map={texture} />
    </mesh>
  )
}

interface SunMarkerProps {
  sunPathPoints: SunPathPoint[]
  atIso: string
  isPlaying: boolean
  fallbackAzimuthDeg: number
  fallbackElevationDeg: number
  orbitRadius: number
  sunRadius: number
  glowRadius: number
  onAnimatedTimeChange?: (atIso: string) => void
}

// Renders the sun marker + its directional light, and (while playing)
// smoothly sweeps them across `sunPathPoints`' daylight arc rather than
// jumping between whatever instant the parent page's `useGeometry` call
// last fetched. Runs entirely inside react-three-fiber's own per-frame loop
// (`useFrame`, imperative ref mutation) rather than React state, so the
// glide is a true 60fps interpolation with zero extra network calls and
// zero extra parent re-renders per frame - `onAnimatedTimeChange` is the
// only bridge back to the parent, and it's throttled (see
// SYNC_CALLBACK_INTERVAL_MS) specifically so it stays that way. Paused (or
// mid-manual-scrub), this just tracks `atIso`/the fallback angles exactly,
// same as the plain prop-driven rendering this replaced.
function SunMarker({
  sunPathPoints,
  atIso,
  isPlaying,
  fallbackAzimuthDeg,
  fallbackElevationDeg,
  orbitRadius,
  sunRadius,
  glowRadius,
  onAnimatedTimeChange,
}: SunMarkerProps) {
  const groupRef = useRef<Group>(null)
  const lightRef = useRef<DirectionalLight>(null)
  const animatedMsRef = useRef(new Date(atIso).getTime())
  const lastCallbackMsRef = useRef(0)

  // Re-anchor the smooth internal clock whenever the authoritative `atIso`
  // moves for a reason other than this component's own animation (a manual
  // scrub while paused, or play just starting from wherever the slider
  // currently sits) - without this the internal clock would silently drift
  // away from what the rest of the page (readouts, panel colors) shows.
  useEffect(() => {
    animatedMsRef.current = new Date(atIso).getTime()
  }, [atIso])

  useFrame((_, delta) => {
    if (isPlaying && sunPathPoints.length > 1) {
      const firstMs = new Date(sunPathPoints[0].time).getTime()
      const lastMs = new Date(sunPathPoints[sunPathPoints.length - 1].time).getTime()
      const spanMs = lastMs - firstMs
      if (spanMs > 0) {
        animatedMsRef.current += delta * PLAY_SIM_MINUTES_PER_REAL_SECOND * 60 * 1000
        if (animatedMsRef.current > lastMs) {
          animatedMsRef.current = firstMs + ((animatedMsRef.current - firstMs) % spanMs)
        }
      }
    }

    const atIsoNow = new Date(animatedMsRef.current).toISOString()
    const interpolated = interpolateSunPosition(sunPathPoints, atIsoNow)
    const azimuthDeg = interpolated?.azimuthDeg ?? fallbackAzimuthDeg
    const elevationDeg = interpolated?.elevationDeg ?? fallbackElevationDeg
    const [x, y, z] = sunPositionVector(azimuthDeg, elevationDeg, orbitRadius)

    if (groupRef.current) {
      groupRef.current.position.set(x, y, z)
      groupRef.current.visible = elevationDeg > 0
    }
    if (lightRef.current) {
      lightRef.current.position.set(x, y, z)
      lightRef.current.intensity = Math.max(0.2, Math.sin((elevationDeg * Math.PI) / 180))
    }

    if (isPlaying && onAnimatedTimeChange) {
      const nowMs = performance.now()
      if (nowMs - lastCallbackMsRef.current >= SYNC_CALLBACK_INTERVAL_MS) {
        lastCallbackMsRef.current = nowMs
        onAnimatedTimeChange(atIsoNow)
      }
    }
  })

  return (
    <>
      <directionalLight ref={lightRef} intensity={0.5} />
      <group ref={groupRef}>
        {/* Soft outer glow first (semi-transparent, no depth-write so it
            never occludes the solid core behind it) - a bare small sphere
            read as an unlabeled speck from any distance (the user's own
            2026-07-18 report); the glow is what actually makes it legible
            as "the sun marker" at a glance, not just physically present. */}
        <mesh>
          <sphereGeometry args={[glowRadius, 16, 16]} />
          <meshBasicMaterial color="#fde047" transparent opacity={0.25} depthWrite={false} />
        </mesh>
        <mesh>
          <sphereGeometry args={[sunRadius, 24, 24]} />
          <meshBasicMaterial color="#fde047" />
        </mesh>
      </group>
    </>
  )
}

interface CloudLayerProps {
  center: [number, number]
  span: number
  opacityPct: number | null
  motionSpeedKmh: number | null
  motionDirectionDeg: number | null
}

const CLOUD_COUNT = 6
// km/h -> scene-units/sec: not a literal physical conversion (this scene's
// scale is schematic throughout - see BUILDING_HEIGHT_M's own docstring for
// the same "reasonable, not measured" spirit) - picked so a typical
// ~15-20 km/h real reading drifts a cloud across the whole visible field in
// a legible ~20-30 real seconds, not so fast it reads as noise or so slow
// it looks frozen.
const CLOUD_SPEED_SCALE = 0.03

// A drifting cloud-cover layer over the scene, driven by the site's real
// latest Himawari reading (GET /weather/clouds - opacity % + motion vector,
// the same source Module 4's Sum-k LSTM cloud-index feature and the
// minute-ahead model's motion features already read) - added per the
// user's own 2026-07-18 request, after noticing every panel's color seemed
// to move in lockstep with the sun alone. Honesty caveat, worth keeping
// explicit: the lightweight cloud_history table only ever stores one
// site-wide opacity scalar + a motion vector, not a spatial raster (the raw
// per-pixel tile arrays live in MinIO, a separate, heavier fetch not wired
// up here) - so this is a stylized "there is X% cloud cover, drifting this
// way" visualization (several overlapping soft spheres per puff, a common
// cheap "cloud silhouette" technique), not a spatially-accurate rendering
// of real cloud shapes or a per-panel shadow simulation. It communicates
// "yes, clouds are real and moving" honestly; it does not claim to show
// exactly which panel is shaded at this instant, since no data source in
// this app currently supports that claim.
function CloudLayer({ center, span, opacityPct, motionSpeedKmh, motionDirectionDeg }: CloudLayerProps) {
  const groupRef = useRef<Group>(null)
  const driftRef = useRef({ x: 0, z: 0 })
  const fieldSpan = span * 2.2
  const height = span * 0.9 + 20
  const sceneScale = Math.max(0.4, span / 30)

  // Deterministic pseudo-random offsets (not Math.random() - a fresh random
  // layout on every re-render, e.g. every zone switch, would look like the
  // whole cloud field teleporting rather than persisting) sized to the
  // field span, recomputed only when that span actually changes.
  const cloudOffsets = useMemo(() => {
    let seed = 1
    const rand = () => {
      seed = (seed * 9301 + 49297) % 233280
      return seed / 233280
    }
    return Array.from({ length: CLOUD_COUNT }, () => ({
      x: (rand() - 0.5) * fieldSpan,
      z: (rand() - 0.5) * fieldSpan,
      scale: (0.6 + rand() * 0.8) * sceneScale,
    }))
  }, [fieldSpan, sceneScale])

  const directionRad = ((motionDirectionDeg ?? 0) * Math.PI) / 180
  const speed = (motionSpeedKmh ?? 0) * CLOUD_SPEED_SCALE
  const driftDx = Math.sin(directionRad) * speed
  const driftDz = -Math.cos(directionRad) * speed

  useFrame((_, delta) => {
    if (!groupRef.current) return
    const wrap = (v: number) => (((v + fieldSpan / 2) % fieldSpan) + fieldSpan) % fieldSpan - fieldSpan / 2
    driftRef.current.x = wrap(driftRef.current.x + driftDx * delta)
    driftRef.current.z = wrap(driftRef.current.z + driftDz * delta)
    groupRef.current.position.set(center[0] + driftRef.current.x, height, -center[1] + driftRef.current.z)
  })

  if (opacityPct == null || opacityPct <= 1) return null

  const puffOpacity = Math.min(0.55, (opacityPct / 100) * 0.6)

  return (
    <group ref={groupRef}>
      {cloudOffsets.map((c, i) => (
        <group key={i} position={[c.x, 0, c.z]} scale={c.scale}>
          <mesh position={[0, 0, 0]}>
            <sphereGeometry args={[6, 10, 10]} />
            <meshBasicMaterial color="#e2e8f0" transparent opacity={puffOpacity} depthWrite={false} />
          </mesh>
          <mesh position={[5, -1, 2]}>
            <sphereGeometry args={[4.5, 10, 10]} />
            <meshBasicMaterial color="#e2e8f0" transparent opacity={puffOpacity} depthWrite={false} />
          </mesh>
          <mesh position={[-5, -1, -2]}>
            <sphereGeometry args={[4.5, 10, 10]} />
            <meshBasicMaterial color="#e2e8f0" transparent opacity={puffOpacity} depthWrite={false} />
          </mesh>
          <mesh position={[1, 2, -3]}>
            <sphereGeometry args={[4, 10, 10]} />
            <meshBasicMaterial color="#e2e8f0" transparent opacity={puffOpacity} depthWrite={false} />
          </mesh>
        </group>
      ))}
    </group>
  )
}

interface Solar3DSceneProps {
  panels: Panel[]
  tiltDeg: number
  azimuthDeg: number
  sunAzimuthDeg: number
  sunElevationDeg: number
  sunPathPoints: SunPathPoint[]
  // The instant currently being shown - the authoritative source SunMarker
  // re-anchors its own smooth animated clock to whenever it isn't actively
  // playing (paused, or a manual scrub). See SunMarker's own docstring.
  atIso: string
  isPlaying: boolean
  // Throttled (not once per frame - see SYNC_CALLBACK_INTERVAL_MS) callback
  // so the parent page's slider/readouts/panel-color fetch can follow the
  // smooth in-scene animation without either driving it (that would be the
  // old laggy jump-per-fetch behavior) or being driven at 60fps themselves.
  onAnimatedTimeChange?: (atIso: string) => void
  // Latest real Himawari reading (GET /weather/clouds) for the drifting
  // cloud layer - see CloudLayer's own docstring for what this can and
  // can't honestly claim to show. `null` fields render no cloud layer at
  // all (no live reading available) rather than a fabricated one.
  cloudOpacityPct: number | null
  cloudMotionSpeedKmh: number | null
  cloudMotionDirectionDeg: number | null
  viewMode: 'access' | 'string'
  // Jetty's trestle/pier structure renders as an elevated deck instead of a
  // solid building block - see PIER_DECK_HEIGHT_M's own docstring. Keyed by
  // zone id (not a generic "isElevatedStructure" flag) since this is the
  // one real structural distinction this app's asset registry currently
  // knows about; a future zone with its own real structure type would need
  // this widened, not a reason to invent an abstraction for one case today.
  zone: string
  // 'grid' (default): the dark grid-line floor. 'satellite': also attempts
  // SatelliteGroundPlane using satelliteTileUrl (falls back to the grid
  // floor showing through if the tile fetch fails/is blocked - see that
  // component's own docstring). satelliteTileUrl is required when
  // groundStyle is 'satellite' (Solar3DPage computes it from the zone's
  // real centroid via lib/satelliteTile.ts).
  groundStyle: 'grid' | 'satellite'
  satelliteTileUrl?: string
  // 0-1: the zone's current output vs. its rated AC capacity (from
  // /performance's live-scaled `ac_kw` - see routes_performance.py's
  // 2026-07-16 docstring for why it's bounded/time-varying, not frozen).
  // 'access' mode multiplies each panel's own solar_access_pct by this
  // before coloring, so the gradient reflects real generation level across
  // the whole day (dawn/dusk/cloudy = orange/yellow, not just a binary
  // day/night shading switch) rather than pure row-shading geometry, which
  // in practice is almost always 0% or 100% except right at sunrise/sunset
  // - approved 2026-07-16 over keeping pure shading. Defaults to 1 (no
  // dimming) if the caller has no performance data yet.
  zoneOutputRatio?: number
}

export function Solar3DScene({
  panels,
  tiltDeg,
  azimuthDeg,
  sunAzimuthDeg,
  sunElevationDeg,
  sunPathPoints,
  atIso,
  isPlaying,
  onAnimatedTimeChange,
  cloudOpacityPct,
  cloudMotionSpeedKmh,
  cloudMotionDirectionDeg,
  viewMode,
  zone,
  groundStyle,
  satelliteTileUrl,
  zoneOutputRatio = 1,
  ref,
}: Solar3DSceneProps & { ref?: Ref<Solar3DSceneHandle> }) {
  const controlsRef = useRef<OrbitControlsImpl | null>(null)
  useImperativeHandle(ref, () => ({ resetCamera: () => controlsRef.current?.reset() }), [])

  // Default camera frames the *first block* (sub-array), not the whole
  // layout's bounding box: Jetty's 4 real sub-arrays are spread across its
  // ~1.25km trestle span, so a camera fit to the whole layout would either
  // shrink every panel to an invisible speck, or - if capped to a sane
  // zoom distance - end up centered on empty space between blocks (no
  // sub-array sits at the geometric middle of a symmetric 4-block spread).
  // Framing on one real block always shows real panels by default; every
  // other block still renders and is reachable by scrolling/panning out
  // (OrbitControls has no distance limit here).
  const bounds = useMemo(() => {
    const boundsOf = (subset: typeof panels) => {
      const easts = subset.map((p) => p.east_m)
      const norths = subset.map((p) => p.north_m)
      return {
        span: Math.max(5, Math.max(...easts) - Math.min(...easts), Math.max(...norths) - Math.min(...norths)),
        center: [(Math.max(...easts) + Math.min(...easts)) / 2 || 0, (Math.max(...norths) + Math.min(...norths)) / 2 || 0] as [number, number],
      }
    }

    const focusBlockId = panels[0]?.block_id
    const focusPanels = panels.filter((p) => p.block_id === focusBlockId)
    return { focus: boundsOf(focusPanels.length ? focusPanels : panels), full: boundsOf(panels) }
  }, [panels])

  // One building mass (or, for Jetty, one pier deck segment) per block - not
  // one for the whole layout, since GIS/ISB's single block is one real
  // rooftop but Jetty's 4 sub-arrays are spread across a ~1.25km trestle
  // with open water between them (a single box spanning all 4 would render
  // as one giant structure connecting sub-arrays that aren't physically
  // connected).
  const blockFootprints = useMemo(() => {
    const byBlock = new Map<string, Panel[]>()
    for (const p of panels) {
      const list = byBlock.get(p.block_id)
      if (list) list.push(p)
      else byBlock.set(p.block_id, [p])
    }
    return [...byBlock.entries()].map(([blockId, blockPanels]) => {
      const easts = blockPanels.map((p) => p.east_m)
      const norths = blockPanels.map((p) => p.north_m)
      return {
        blockId,
        minEast: Math.min(...easts),
        maxEast: Math.max(...easts),
        minNorth: Math.min(...norths),
        maxNorth: Math.max(...norths),
      }
    })
  }, [panels])
  const mountType = mountTypeForZone(zone)

  // Scaled to the camera's own actual framing distance (~1.5x bounds.focus.span,
  // see the Canvas camera position below), not a fixed meters value - see
  // SUN_MARKER_RADIUS_FLOOR_M's own docstring for why a fixed distance broke
  // down across this app's real range of zone scales.
  const sunOrbitRadius = Math.max(SUN_MARKER_RADIUS_FLOOR_M, bounds.focus.span * 1.8)
  const sunRadius = sunOrbitRadius * SUN_RADIUS_FRACTION
  const sunGlowRadius = sunOrbitRadius * SUN_GLOW_RADIUS_FRACTION

  const sunPathLine = useMemo(
    () => sunPathPoints.map((p) => sunPositionVector(p.azimuth_deg, p.elevation_deg, sunOrbitRadius)),
    [sunPathPoints, sunOrbitRadius],
  )

  const focusCenterScene: [number, number] = [bounds.focus.center[0], -bounds.focus.center[1]]
  // Panels sit on top of the roof/deck (rooftop/pier), or just above grade on
  // their support legs (ground-mount) - see BUILDING_HEIGHT_M/PIER_DECK_HEIGHT_M/
  // GROUND_MOUNT_CLEARANCE_M's own docstrings.
  const panelBaseY =
    mountType === 'pier'
      ? PIER_DECK_HEIGHT_M + PIER_DECK_THICKNESS_M
      : mountType === 'ground'
        ? GROUND_MOUNT_CLEARANCE_M
        : BUILDING_HEIGHT_M

  return (
    <Canvas
      camera={{
        position: [
          focusCenterScene[0] + bounds.focus.span * 0.9,
          panelBaseY + bounds.focus.span * 0.7,
          focusCenterScene[1] + bounds.focus.span * 0.9,
        ],
        fov: 45,
      }}
      data-testid="solar3d-canvas"
    >
      <ambientLight intensity={0.6} />

      {/* Dark ground plane, always rendered as the base/fallback - either
          under the grid overlay (groundStyle="grid") or under the
          satellite texture, which stays transparent-until-loaded and
          simply never covers this if its fetch fails/is blocked (see
          SatelliteGroundPlane's own docstring). */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[bounds.full.center[0], -0.05, -bounds.full.center[1]]}>
        <planeGeometry args={[bounds.full.span * 1.5, bounds.full.span * 1.5]} />
        <meshStandardMaterial color="#0f172a" />
      </mesh>
      {groundStyle === 'grid' && (
        <Grid
          position={[bounds.full.center[0], 0, -bounds.full.center[1]]}
          args={[bounds.full.span * 1.5, bounds.full.span * 1.5]}
          cellSize={5}
          cellThickness={0.5}
          cellColor="#334155"
          sectionSize={25}
          sectionThickness={1}
          sectionColor="#475569"
          fadeDistance={bounds.full.span * 3}
          infiniteGrid={false}
        />
      )}
      {groundStyle === 'satellite' && satelliteTileUrl && (
        <SatelliteGroundPlane tileUrl={satelliteTileUrl} center={bounds.full.center} size={bounds.full.span * 1.5} />
      )}

      {blockFootprints.map((f) => (
        <BuildingMass key={f.blockId} minEast={f.minEast} maxEast={f.maxEast} minNorth={f.minNorth} maxNorth={f.maxNorth} mountType={mountType} />
      ))}

      {panels.map((panel) => (
        <PanelMesh
          key={`${panel.block_id}-${panel.row}-${panel.col}`}
          panel={panel}
          tiltDeg={tiltDeg}
          azimuthDeg={azimuthDeg}
          color={
            viewMode === 'access'
              ? solarAccessColor(panel.solar_access_pct * zoneOutputRatio)
              : stringColor(panel.block_id)
          }
          baseY={panelBaseY}
        />
      ))}

      {sunPathLine.length > 1 && <Line points={sunPathLine} color="#f59e0b" lineWidth={1.5} />}
      <SunMarker
        sunPathPoints={sunPathPoints}
        atIso={atIso}
        isPlaying={isPlaying}
        fallbackAzimuthDeg={sunAzimuthDeg}
        fallbackElevationDeg={sunElevationDeg}
        orbitRadius={sunOrbitRadius}
        sunRadius={sunRadius}
        glowRadius={sunGlowRadius}
        onAnimatedTimeChange={onAnimatedTimeChange}
      />
      <CloudLayer
        center={bounds.full.center}
        span={bounds.full.span}
        opacityPct={cloudOpacityPct}
        motionSpeedKmh={cloudMotionSpeedKmh}
        motionDirectionDeg={cloudMotionDirectionDeg}
      />

      <OrbitControls ref={controlsRef} target={[focusCenterScene[0], panelBaseY, focusCenterScene[1]]} />
    </Canvas>
  )
}
