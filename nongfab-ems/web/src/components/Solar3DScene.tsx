// The actual WebGL canvas for Feature B/C - not unit-testable in jsdom (no
// WebGL context), so this file has no companion test; correctness is
// verified live (see web/README.md "Verified live"). All the testable
// logic (color scale, compass math, sun position) lives in lib/solar3d.ts,
// which this component just calls into.

import { Grid, Line, OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { useMemo } from 'react'
import { solarAccessColor, sunPositionVector } from '../lib/solar3d'
import type { Panel, SunPathPoint } from '../lib/types'

const SUN_MARKER_RADIUS_M = 40

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
  isPier: boolean
}

// Roof/deck overhang beyond the panels' own footprint, purely so panel edges
// don't sit flush with (or clip through) the building/deck edge - not a
// measurement.
const FOOTPRINT_MARGIN_M = 2

function BuildingMass({ minEast, maxEast, minNorth, maxNorth, isPier }: BuildingMassProps) {
  const width = maxEast - minEast + FOOTPRINT_MARGIN_M * 2
  const depth = maxNorth - minNorth + FOOTPRINT_MARGIN_M * 2
  const centerEast = (minEast + maxEast) / 2
  const centerNorth = (minNorth + maxNorth) / 2
  const height = isPier ? PIER_DECK_THICKNESS_M : BUILDING_HEIGHT_M
  const baseY = isPier ? PIER_DECK_HEIGHT_M : 0
  const legRadius = 0.4

  return (
    <group>
      <mesh position={[centerEast, baseY + height / 2, -centerNorth]}>
        <boxGeometry args={[width, height, depth]} />
        <meshStandardMaterial color={isPier ? '#4b5563' : '#6b7280'} />
      </mesh>
      {isPier &&
        // Support piles at the deck's 4 corners, purely a visual "this is
        // an elevated pier, not solid ground" cue - not a structural model.
        [
          [minEast, minNorth],
          [minEast, maxNorth],
          [maxEast, minNorth],
          [maxEast, maxNorth],
        ].map(([e, n]) => (
          <mesh key={`${e}-${n}`} position={[e, baseY / 2, -n]}>
            <cylinderGeometry args={[legRadius, legRadius, baseY, 8]} />
            <meshStandardMaterial color="#374151" />
          </mesh>
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
  viewMode: 'access' | 'string'
  // Jetty's trestle/pier structure renders as an elevated deck instead of a
  // solid building block - see PIER_DECK_HEIGHT_M's own docstring. Keyed by
  // zone id (not a generic "isElevatedStructure" flag) since this is the
  // one real structural distinction this app's asset registry currently
  // knows about; a future zone with its own real structure type would need
  // this widened, not a reason to invent an abstraction for one case today.
  zone: string
}

export function Solar3DScene({ panels, tiltDeg, azimuthDeg, sunAzimuthDeg, sunElevationDeg, sunPathPoints, viewMode, zone }: Solar3DSceneProps) {
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
  const isPierStructure = zone === 'Jetty'

  const sunPathLine = useMemo(
    () => sunPathPoints.map((p) => sunPositionVector(p.azimuth_deg, p.elevation_deg, SUN_MARKER_RADIUS_M)),
    [sunPathPoints],
  )
  const sunPosition = useMemo(() => sunPositionVector(sunAzimuthDeg, sunElevationDeg, SUN_MARKER_RADIUS_M), [sunAzimuthDeg, sunElevationDeg])

  const focusCenterScene: [number, number] = [bounds.focus.center[0], -bounds.focus.center[1]]
  // Panels sit on top of the roof/deck, not at ground level - see
  // BUILDING_HEIGHT_M/PIER_DECK_HEIGHT_M's own docstrings.
  const panelBaseY = isPierStructure ? PIER_DECK_HEIGHT_M + PIER_DECK_THICKNESS_M : BUILDING_HEIGHT_M

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

      {/* Dark ground plane + grid overlay - the "abstract block + grid floor"
          style this was modeled on (a reference solar-monitoring product's
          digital-twin widget), rather than the flat single-color ground
          this scene had before. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[bounds.full.center[0], -0.05, -bounds.full.center[1]]}>
        <planeGeometry args={[bounds.full.span * 1.5, bounds.full.span * 1.5]} />
        <meshStandardMaterial color="#0f172a" />
      </mesh>
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

      {blockFootprints.map((f) => (
        <BuildingMass key={f.blockId} minEast={f.minEast} maxEast={f.maxEast} minNorth={f.minNorth} maxNorth={f.maxNorth} isPier={isPierStructure} />
      ))}

      {panels.map((panel) => (
        <PanelMesh
          key={`${panel.block_id}-${panel.row}-${panel.col}`}
          panel={panel}
          tiltDeg={tiltDeg}
          azimuthDeg={azimuthDeg}
          color={viewMode === 'access' ? solarAccessColor(panel.solar_access_pct) : stringColor(panel.block_id)}
          baseY={panelBaseY}
        />
      ))}

      {sunPathLine.length > 1 && <Line points={sunPathLine} color="#f59e0b" lineWidth={1.5} />}
      {sunElevationDeg > 0 && (
        <mesh position={sunPosition}>
          <sphereGeometry args={[2, 16, 16]} />
          <meshBasicMaterial color="#fde047" />
        </mesh>
      )}

      <OrbitControls target={[focusCenterScene[0], panelBaseY, focusCenterScene[1]]} />
    </Canvas>
  )
}
