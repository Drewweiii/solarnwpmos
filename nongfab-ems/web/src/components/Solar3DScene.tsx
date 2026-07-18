// The actual WebGL canvas for Feature B/C - not unit-testable in jsdom (no
// WebGL context), so this file has no companion test; correctness is
// verified live (see web/README.md "Verified live"). All the testable
// logic (color scale, compass math, sun position) lives in lib/solar3d.ts,
// which this component just calls into.

import { Grid, Line, OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import type { Ref } from 'react'
import { TextureLoader, type Texture } from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { solarAccessColor, sunPositionVector } from '../lib/solar3d'
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

interface Solar3DSceneProps {
  panels: Panel[]
  tiltDeg: number
  azimuthDeg: number
  sunAzimuthDeg: number
  sunElevationDeg: number
  sunPathPoints: SunPathPoint[]
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
  const sunPosition = useMemo(() => sunPositionVector(sunAzimuthDeg, sunElevationDeg, sunOrbitRadius), [sunAzimuthDeg, sunElevationDeg, sunOrbitRadius])

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
      <directionalLight position={sunPosition} intensity={Math.max(0.2, Math.sin((sunElevationDeg * Math.PI) / 180))} />

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
      {sunElevationDeg > 0 && (
        <group position={sunPosition}>
          {/* Soft outer glow first (semi-transparent, no depth-write so it
              never occludes the solid core behind it) - a bare small sphere
              read as an unlabeled speck from any distance (the user's own
              2026-07-18 report); the glow is what actually makes it legible
              as "the sun marker" at a glance, not just physically present. */}
          <mesh>
            <sphereGeometry args={[sunGlowRadius, 16, 16]} />
            <meshBasicMaterial color="#fde047" transparent opacity={0.25} depthWrite={false} />
          </mesh>
          <mesh>
            <sphereGeometry args={[sunRadius, 24, 24]} />
            <meshBasicMaterial color="#fde047" />
          </mesh>
        </group>
      )}

      <OrbitControls ref={controlsRef} target={[focusCenterScene[0], panelBaseY, focusCenterScene[1]]} />
    </Canvas>
  )
}
