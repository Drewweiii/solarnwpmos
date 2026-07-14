// The actual WebGL canvas for Feature B/C - not unit-testable in jsdom (no
// WebGL context), so this file has no companion test; correctness is
// verified live (see web/README.md "Verified live"). All the testable
// logic (color scale, compass math, sun position) lives in lib/solar3d.ts,
// which this component just calls into.

import { Line, OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { useMemo } from 'react'
import { solarAccessColor, sunPositionVector } from '../lib/solar3d'
import type { Panel, SunPathPoint } from '../lib/types'

const SUN_MARKER_RADIUS_M = 40

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
}

function PanelMesh({ panel, tiltDeg, azimuthDeg, color }: PanelMeshProps) {
  const tiltRad = (tiltDeg * Math.PI) / 180
  const azimuthRad = (azimuthDeg * Math.PI) / 180
  const thickness = 0.05

  return (
    <group position={[panel.east_m, 0, -panel.north_m]} rotation={[0, -azimuthRad, 0]}>
      <mesh rotation={[-tiltRad, 0, 0]} position={[0, (panel.slant_height_m / 2) * Math.sin(tiltRad), 0]}>
        <boxGeometry args={[panel.width_m * 0.92, thickness, panel.slant_height_m * 0.92]} />
        <meshStandardMaterial color={color} />
      </mesh>
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
}

export function Solar3DScene({ panels, tiltDeg, azimuthDeg, sunAzimuthDeg, sunElevationDeg, sunPathPoints, viewMode }: Solar3DSceneProps) {
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

  const sunPathLine = useMemo(
    () => sunPathPoints.map((p) => sunPositionVector(p.azimuth_deg, p.elevation_deg, SUN_MARKER_RADIUS_M)),
    [sunPathPoints],
  )
  const sunPosition = useMemo(() => sunPositionVector(sunAzimuthDeg, sunElevationDeg, SUN_MARKER_RADIUS_M), [sunAzimuthDeg, sunElevationDeg])

  const focusCenterScene: [number, number] = [bounds.focus.center[0], -bounds.focus.center[1]]

  return (
    <Canvas
      camera={{
        position: [focusCenterScene[0] + bounds.focus.span * 0.9, bounds.focus.span * 0.7, focusCenterScene[1] + bounds.focus.span * 0.9],
        fov: 45,
      }}
      data-testid="solar3d-canvas"
    >
      <ambientLight intensity={0.6} />
      <directionalLight position={sunPosition} intensity={Math.max(0.2, Math.sin((sunElevationDeg * Math.PI) / 180))} />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[bounds.full.center[0], -0.05, -bounds.full.center[1]]}>
        <planeGeometry args={[bounds.full.span * 1.3, bounds.full.span * 1.3]} />
        <meshStandardMaterial color="#3a3a2e" />
      </mesh>

      {panels.map((panel) => (
        <PanelMesh
          key={`${panel.block_id}-${panel.row}-${panel.col}`}
          panel={panel}
          tiltDeg={tiltDeg}
          azimuthDeg={azimuthDeg}
          color={viewMode === 'access' ? solarAccessColor(panel.solar_access_pct) : stringColor(panel.block_id)}
        />
      ))}

      {sunPathLine.length > 1 && <Line points={sunPathLine} color="#f59e0b" lineWidth={1.5} />}
      {sunElevationDeg > 0 && (
        <mesh position={sunPosition}>
          <sphereGeometry args={[2, 16, 16]} />
          <meshBasicMaterial color="#fde047" />
        </mesh>
      )}

      <OrbitControls target={[focusCenterScene[0], 0, focusCenterScene[1]]} />
    </Canvas>
  )
}
