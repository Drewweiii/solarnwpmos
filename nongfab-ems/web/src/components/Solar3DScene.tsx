// The actual WebGL canvas for Feature B/C - not unit-testable in jsdom (no
// WebGL context), so this file has no companion test; correctness is
// verified live (see web/README.md "Verified live"). All the testable
// logic (color scale, compass math, sun position) lives in lib/solar3d.ts,
// which this component just calls into.

import { Grid, Html, Line, OrbitControls } from '@react-three/drei'
import { Canvas, useFrame } from '@react-three/fiber'
import { useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import type { Ref } from 'react'
import type { DirectionalLight, Group } from 'three'
import { TextureLoader, type Texture } from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import {
  advanceSimClockMs,
  angleArcPoints,
  interpolateSunPosition,
  irradianceGhiColor,
  latLonToLocalMeters,
  solarAccessColor,
  sunPositionVector,
  zenithAngleDeg,
} from '../lib/solar3d'
import type { IrradianceGridPoint, MoonPathPoint, Panel, PrecipitationIntensity, SunPathPoint } from '../lib/types'

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
// Smaller than the sun's own fractions - conventionally the moon reads as
// the visually smaller body of the two, and keeping it modest avoids it
// competing with the sun for attention on the (much rarer) instants both
// might render at once (twilight, one clock tick before/after the other's
// visibility flips).
const MOON_RADIUS_FRACTION = 0.065
const MOON_GLOW_RADIUS_FRACTION = 0.1
// Equal to the sun's own orbit radius (fraction 1.0) so every angle-diagram
// arc/reference-ray (see SunAngleDiagram) literally terminates AT the sun
// marker's real rendered position, instead of stopping short at a smaller
// reference-instrument radius - changed 2026-07-18 per the user's explicit
// follow-up request that the angle lines visibly "ลากวัดไปหาดวงอาทิตย์" (draw/
// measure out to reach the sun itself), after an earlier round had this at
// 0.3 (a compact protractor near the observer, not reaching the sun) and the
// user reported that wasn't what they meant.
const ANGLE_DIAGRAM_RADIUS_FRACTION = 1.0

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
  // The shared full-24h clock-wrap window (see `advanceSimClockMs`'s own
  // docstring) - both SunMarker and MoonMarker wrap at the same instants so
  // they stay in lockstep, rather than the Sun looping only its own
  // daylight-only span the way it did before the Moon existed.
  wrapStartMs: number | null
  wrapEndMs: number | null
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
  wrapStartMs,
  wrapEndMs,
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
    if (isPlaying) {
      animatedMsRef.current = advanceSimClockMs(animatedMsRef.current, delta, PLAY_SIM_MINUTES_PER_REAL_SECOND, wrapStartMs, wrapEndMs)
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

interface MoonMarkerProps {
  moonPathPoints: MoonPathPoint[]
  sunPathPoints: SunPathPoint[]
  atIso: string
  isPlaying: boolean
  fallbackMoonAzimuthDeg: number
  fallbackMoonElevationDeg: number
  fallbackSunElevationDeg: number
  orbitRadius: number
  moonRadius: number
  glowRadius: number
  wrapStartMs: number | null
  wrapEndMs: number | null
}

// Mirrors SunMarker's own "own imperative clock, no React re-render per
// frame" structure (see that component's docstring) - added 2026-07-18 per
// the user's own request that the Moon "rise to replace the Sun" once it
// sets, moving just as smoothly. Deliberately does NOT call
// `onAnimatedTimeChange` itself: SunMarker already owns that bridge back to
// the parent page, and both markers are fed the exact same `wrapStartMs`/
// `wrapEndMs`/`atIso`/`isPlaying` inputs and the same per-frame `delta`
// (see `advanceSimClockMs`), so their internal clocks stay in lockstep
// without a second callback duplicating the same update.
//
// Unlike the Sun, `moonPathPoints` is NOT daylight-filtered (see
// routes_solar3d.py's own `/moon-path` docstring for why) - it's a
// continuous 24h arc, so `interpolateSunPosition` (generic over any
// {time, azimuth_deg, elevation_deg}[] - reused here rather than writing a
// near-identical "interpolateMoonPosition") never returns null for it.
// Visibility instead requires two real conditions at once: the Moon's own
// elevation is genuinely above its horizon, AND the Sun is currently below
// its own horizon (`interpolateSunPosition(sunPathPoints, ...)` returning
// null - sunPathPoints only covers daylight, so null there already means
// "sun is down"). This is a deliberate "one or the other, not both" scene
// convention (the request was literally "replace the sun"), not a claim
// that the real sun and moon are never in the sky at once.
function MoonMarker({
  moonPathPoints,
  sunPathPoints,
  atIso,
  isPlaying,
  fallbackMoonAzimuthDeg,
  fallbackMoonElevationDeg,
  fallbackSunElevationDeg,
  orbitRadius,
  moonRadius,
  glowRadius,
  wrapStartMs,
  wrapEndMs,
}: MoonMarkerProps) {
  const groupRef = useRef<Group>(null)
  const animatedMsRef = useRef(new Date(atIso).getTime())

  useEffect(() => {
    animatedMsRef.current = new Date(atIso).getTime()
  }, [atIso])

  useFrame((_, delta) => {
    if (isPlaying) {
      animatedMsRef.current = advanceSimClockMs(animatedMsRef.current, delta, PLAY_SIM_MINUTES_PER_REAL_SECOND, wrapStartMs, wrapEndMs)
    }

    const atIsoNow = new Date(animatedMsRef.current).toISOString()
    const interpolatedMoon = interpolateSunPosition(moonPathPoints, atIsoNow)
    const azimuthDeg = interpolatedMoon?.azimuthDeg ?? fallbackMoonAzimuthDeg
    const elevationDeg = interpolatedMoon?.elevationDeg ?? fallbackMoonElevationDeg
    const [x, y, z] = sunPositionVector(azimuthDeg, elevationDeg, orbitRadius)

    const interpolatedSun = interpolateSunPosition(sunPathPoints, atIsoNow)
    const sunIsDown = interpolatedSun ? interpolatedSun.elevationDeg <= 0 : fallbackSunElevationDeg <= 0

    if (groupRef.current) {
      groupRef.current.position.set(x, y, z)
      groupRef.current.visible = sunIsDown && elevationDeg > 0
    }
  })

  return (
    <group ref={groupRef}>
      {/* Same soft-glow-plus-core convention as SunMarker's own mesh pair,
          just pale blue-white instead of yellow. */}
      <mesh>
        <sphereGeometry args={[glowRadius, 16, 16]} />
        <meshBasicMaterial color="#e2e8f0" transparent opacity={0.2} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[moonRadius, 24, 24]} />
        <meshBasicMaterial color="#f1f5f9" />
      </mesh>
    </group>
  )
}

// Small helper so the 3 <Html> labels below share one look without
// repeating the inline style object 3 times.
const ANGLE_LABEL_STYLE: Record<'azimuth' | 'altitude' | 'zenith', string> = {
  azimuth: '#38bdf8',
  altitude: '#34d399',
  zenith: '#a78bfa',
}

interface SunAngleDiagramProps {
  azimuthDeg: number
  elevationDeg: number
  radius: number
}

// In-scene azimuth/altitude/zenith-angle protractor for the Sun only - per
// the user's own 2026-07-18 request ("(สำคัญมาก)ตรงเส้น3Dให้แสดงการวัดมุม
// เข้าไปด้วย...ทำเฉพาะดวงอาิตย์ ดวงจันทน์ไม่ต้องทำ มีมุม azimuth, altitude,
// zenith angle"), matching the standard solar-position diagram convention
// (e.g. Duffie & Beckman's "Solar Engineering of Thermal Processes"):
//  - Azimuth (cyan): the ground-plane arc from North to the sun's compass
//    bearing.
//  - Altitude (green): the vertical-plane arc from the horizon up to the
//    sun, in the sun's own azimuth direction.
//  - Zenith angle (violet): the vertical-plane arc from directly overhead
//    down to the sun - complementary to altitude (they always sum to 90deg
//    and share the sun as one endpoint), matching `zenithAngleDeg`'s own
//    convention.
// Deliberately prop-driven, NOT a `useFrame` clock like SunMarker/
// MoonMarker: it re-renders whenever `azimuthDeg`/`elevationDeg` (the same
// `geometry.data.sun` value Solar3DPage's own Compass/Zenith text readouts
// already use) changes - the same update cadence as every other
// non-animated element in this scene (panels, buildings). Hidden entirely
// below the horizon - an angle-to-the-sun diagram for a sun that isn't up
// doesn't mean anything.
function SunAngleDiagram({ azimuthDeg, elevationDeg, radius }: SunAngleDiagramProps) {
  const azimuthArc = useMemo(() => angleArcPoints(0, azimuthDeg, 0, 0, radius), [azimuthDeg, radius])
  const altitudeArc = useMemo(() => angleArcPoints(azimuthDeg, azimuthDeg, 0, elevationDeg, radius), [azimuthDeg, elevationDeg, radius])
  const zenithArc = useMemo(() => angleArcPoints(azimuthDeg, azimuthDeg, 90, elevationDeg, radius), [azimuthDeg, elevationDeg, radius])

  if (elevationDeg <= 0) return null

  const origin: [number, number, number] = [0, 0, 0]
  const northPoint = sunPositionVector(0, 0, radius)
  const zenithPoint = sunPositionVector(azimuthDeg, 90, radius)
  const sunPoint = sunPositionVector(azimuthDeg, elevationDeg, radius)
  const groundProjectionPoint = sunPositionVector(azimuthDeg, 0, radius)

  const azimuthLabelPos = sunPositionVector(azimuthDeg / 2, 0, radius * 1.2)
  const altitudeLabelPos = sunPositionVector(azimuthDeg, elevationDeg / 2, radius * 1.2)
  const zenithLabelPos = sunPositionVector(azimuthDeg, (elevationDeg + 90) / 2, radius * 1.2)

  return (
    <group>
      {/* Reference rays - subtle, just anchoring the arcs to real
          directions (North, straight up, the sun's ground projection, and
          the sun itself). */}
      <Line points={[origin, northPoint]} color="#94a3b8" lineWidth={1} transparent opacity={0.5} />
      <Line points={[origin, zenithPoint]} color="#94a3b8" lineWidth={1} transparent opacity={0.5} />
      <Line points={[origin, groundProjectionPoint]} color="#94a3b8" lineWidth={1} transparent opacity={0.35} />
      <Line points={[origin, sunPoint]} color="#fde047" lineWidth={1.5} transparent opacity={0.7} />

      <Line points={azimuthArc} color={ANGLE_LABEL_STYLE.azimuth} lineWidth={2.5} />
      <Line points={altitudeArc} color={ANGLE_LABEL_STYLE.altitude} lineWidth={2.5} />
      <Line points={zenithArc} color={ANGLE_LABEL_STYLE.zenith} lineWidth={2.5} />

      <Html position={azimuthLabelPos} center>
        <span className="solar3d-angle-label" style={{ color: ANGLE_LABEL_STYLE.azimuth }}>
          Azimuth {Math.round(azimuthDeg)}&deg;
        </span>
      </Html>
      <Html position={altitudeLabelPos} center>
        <span className="solar3d-angle-label" style={{ color: ANGLE_LABEL_STYLE.altitude }}>
          Altitude {Math.round(elevationDeg)}&deg;
        </span>
      </Html>
      <Html position={zenithLabelPos} center>
        <span className="solar3d-angle-label" style={{ color: ANGLE_LABEL_STYLE.zenith }}>
          Zenith {Math.round(zenithAngleDeg(elevationDeg))}&deg;
        </span>
      </Html>
    </group>
  )
}

interface IrradianceGroundOverlayProps {
  points: IrradianceGridPoint[]
  originLat: number
  originLon: number
  markerRadiusM: number
  visible: boolean
}

// Literal single-image merge of the former standalone MapLibre Irradiance
// Map into this WebGL scene (2026-07-18, per the user's own explicit
// request/confirmed design: "วาง irradiance เป็นจุดสีบนพื้นดินในฉาก 3D" -
// place irradiance as colored points on the ground in the 3D scene, rather
// than a separate map section below it). Reuses the exact same plant-wide
// grid (GET /irradiance-map's `grid`, 10x10 = 100 points spanning the
// plant's full target bbox) and the exact same 4-stop color ramp the old
// MapLibre `circle-color` paint expression used (see irradianceGhiColor's
// own docstring) - not a redesign, just a different rendering surface.
//
// Each point's real (lat, lon) is projected into this zone's own local
// (east_m, north_m) frame via `latLonToLocalMeters`, anchored at the SAME
// centroid `nongfab_features.panel_geometry` already uses as (0, 0) for
// this zone's own panels - so a grid point and a panel share one ground
// plane with no separate coordinate system. Honesty caveat worth keeping
// explicit: the grid spans the whole ~2km plant, so most of its 100 points
// land well outside any one zone's own local panel footprint (GIS/ISB's
// block is tens of meters across) - they simply render far out on/beyond
// the ground plane rather than being filtered down to "nearby only", since
// a real irradiance field is continuous across that whole distance, not
// just at the panels themselves.
function IrradianceGroundOverlay({ points, originLat, originLon, markerRadiusM, visible }: IrradianceGroundOverlayProps) {
  if (!visible || points.length === 0) return null
  return (
    <group>
      {points.map((p, i) => {
        const { eastM, northM } = latLonToLocalMeters(p.lat, p.lon, originLat, originLon)
        return (
          <mesh key={i} rotation={[-Math.PI / 2, 0, 0]} position={[eastM, 0.04, -northM]}>
            <circleGeometry args={[markerRadiusM, 24]} />
            <meshBasicMaterial color={irradianceGhiColor(p.ghi_w_m2)} transparent opacity={0.55} depthWrite={false} />
          </mesh>
        )
      })}
    </group>
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

interface RainLayerProps {
  center: [number, number]
  span: number
  precipMm: number | null
  intensity: PrecipitationIntensity | null
}

// Particle counts per WMO intensity band (see routes_weather.py's own
// _PRECIP_LIGHT_MM/_PRECIP_MODERATE_MM docstring for where these bands come
// from) - individual meshes, not InstancedMesh, matching this file's existing
// "keep it simple" convention (PanelMesh/CloudLayer already render one mesh
// per panel/puff rather than instancing) - these counts were kept modest
// specifically so that stays cheap enough at "heavy" too.
const RAIN_PARTICLE_COUNTS: Record<Exclude<PrecipitationIntensity, 'none'>, number> = {
  light: 60,
  moderate: 120,
  heavy: 200,
}

// Scene-units/sec fall speed - schematic, not physical (same "reasonable,
// not measured" spirit as CLOUD_SPEED_SCALE's own docstring), tuned so drops
// read as fast, clearly-falling streaks rather than drifting snow-like specks
// - a real, deliberate visual distinction, not an oversight: the user
// explicitly asked for rain only, no snow (Thailand has none).
const RAIN_FALL_SPEED = 26

// A falling-rain particle layer, driven by the site's real latest GFS
// precipitation reading (GET /weather/precipitation - see that route's own
// docstring for the accumulated-mm honesty caveat behind these intensity
// bands) - added per the user's own 2026-07-18 request, gated on Thailand's
// real rainy-season data rather than a decorative always-on effect. Renders
// nothing at all (not just an empty group) when there's no real precip
// reading or intensity is "none", so an unavailable/dry reading never shows
// fabricated rain - same "honest absence over guessed presence" pattern
// CloudLayer already established for cloud cover.
function RainLayer({ center, span, precipMm, intensity }: RainLayerProps) {
  const dropRefs = useRef<(Group | null)[]>([])
  const fieldSpan = span * 2.2
  const height = span * 0.9 + 20
  const count = intensity && intensity !== 'none' ? RAIN_PARTICLE_COUNTS[intensity] : 0

  const drops = useMemo(() => {
    let seed = 7
    const rand = () => {
      seed = (seed * 9301 + 49297) % 233280
      return seed / 233280
    }
    return Array.from({ length: count }, () => ({
      x: (rand() - 0.5) * fieldSpan,
      z: (rand() - 0.5) * fieldSpan,
      y0: rand() * height,
      speedFactor: 0.8 + rand() * 0.4,
    }))
  }, [count, fieldSpan, height])

  useFrame((_, delta) => {
    for (let i = 0; i < drops.length; i++) {
      const node = dropRefs.current[i]
      if (!node) continue
      let y = node.position.y - RAIN_FALL_SPEED * drops[i].speedFactor * delta
      if (y < 0) y += height
      node.position.y = y
    }
  })

  if (count === 0 || precipMm == null || precipMm <= 0) return null

  return (
    <group position={[center[0], 0, -center[1]]}>
      {drops.map((d, i) => (
        <group
          key={i}
          ref={(el) => {
            dropRefs.current[i] = el
          }}
          position={[d.x, d.y0, d.z]}
        >
          <mesh>
            <cylinderGeometry args={[0.035, 0.035, 0.9, 4]} />
            <meshBasicMaterial color="#93c5fd" transparent opacity={0.5} depthWrite={false} />
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
  // Decorative Moon (2026-07-18) - see MoonMarker's own docstring for the
  // visibility rule (only shown once the Sun is down) and moon.py's for the
  // low/medium-precision caveat behind these numbers. `moonPathPoints`
  // covers the full 24h day (NOT daylight-filtered, unlike sunPathPoints)
  // and doubles as the shared clock's wrap-around window - see
  // `advanceSimClockMs`.
  moonAzimuthDeg: number
  moonElevationDeg: number
  moonPathPoints: MoonPathPoint[]
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
  // Latest real GFS precipitation reading (GET /weather/precipitation) for
  // the falling-rain layer - see RainLayer's own docstring. `null`/`"none"`
  // render no rain at all rather than a fabricated drizzle.
  precipMm: number | null
  precipIntensity: PrecipitationIntensity | null
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
  // Multiplies each panel's own solar_access_pct before coloring, so the
  // gradient reflects real generation level across the whole day (dawn/
  // dusk/cloudy = orange/yellow, not just a binary day/night shading
  // switch) rather than pure row-shading geometry, which in practice is
  // almost always 0% or 100% except right at sunrise/sunset - approved
  // 2026-07-16 over keeping pure shading. Defaults to 1 (no dimming) if the
  // caller has no performance data yet.
  zoneOutputRatio?: number
  // Plant-wide irradiance grid (GET /irradiance-map's `grid`) + this zone's
  // own real surveyed centroid (the origin every grid point gets projected
  // relative to) - see IrradianceGroundOverlay's own docstring for the full
  // 2026-07-18 "merge the separate map into this scene" story. `visible`
  // toggles the overlay on/off (Solar3DPage's own checkbox) without an
  // extra network request either way. Both default to "off"/empty so every
  // existing caller (and every test that doesn't pass them) keeps rendering
  // exactly as before.
  irradianceGrid?: IrradianceGridPoint[]
  irradianceOriginLat?: number
  irradianceOriginLon?: number
  showIrradianceOverlay?: boolean
}

export function Solar3DScene({
  panels,
  tiltDeg,
  azimuthDeg,
  sunAzimuthDeg,
  sunElevationDeg,
  sunPathPoints,
  moonAzimuthDeg,
  moonElevationDeg,
  moonPathPoints,
  atIso,
  isPlaying,
  onAnimatedTimeChange,
  cloudOpacityPct,
  cloudMotionSpeedKmh,
  cloudMotionDirectionDeg,
  precipMm,
  precipIntensity,
  zone,
  groundStyle,
  satelliteTileUrl,
  zoneOutputRatio = 1,
  irradianceGrid = [],
  irradianceOriginLat = 0,
  irradianceOriginLon = 0,
  showIrradianceOverlay = false,
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
  const moonRadius = sunOrbitRadius * MOON_RADIUS_FRACTION
  const moonGlowRadius = sunOrbitRadius * MOON_GLOW_RADIUS_FRACTION
  const angleDiagramRadius = sunOrbitRadius * ANGLE_DIAGRAM_RADIUS_FRACTION
  // Scaled to this zone's own full layout span (not a fixed meters value -
  // same floor+scale pattern as the sun/moon markers above), so a grid
  // point reads as a legible ground disk at any zone's real scale, from
  // GIS/ISB's tens-of-meters block up to Jetty's ~1.25km trestle.
  const irradianceMarkerRadiusM = Math.max(4, bounds.full.span * 0.06)

  const sunPathLine = useMemo(
    () => sunPathPoints.map((p) => sunPositionVector(p.azimuth_deg, p.elevation_deg, sunOrbitRadius)),
    [sunPathPoints, sunOrbitRadius],
  )
  // Only the above-horizon stretch is drawn as a guide line (matching the
  // sun's own line, whose source data is daylight-pre-filtered) - the full
  // `moonPathPoints` array itself (including its below-horizon points) is
  // still what MoonMarker interpolates off, so a moonrise/moonset
  // transition still glides smoothly even though the line vanishes at the
  // horizon crossing.
  const moonPathLine = useMemo(
    () =>
      moonPathPoints.filter((p) => p.elevation_deg > 0).map((p) => sunPositionVector(p.azimuth_deg, p.elevation_deg, sunOrbitRadius)),
    [moonPathPoints, sunOrbitRadius],
  )
  // The shared "play" clock's wrap-around window - the Moon's own path
  // already spans the full 24h day (unlike the Sun's daylight-only
  // sunPathPoints), so it's the natural source for "when does one full lap
  // end" for both markers. `null` before the Moon data has loaded, in which
  // case both markers just advance unwrapped for that one frame (see
  // `advanceSimClockMs`'s own docstring).
  const wrapStartMs = moonPathPoints.length > 0 ? new Date(moonPathPoints[0].time).getTime() : null
  const wrapEndMs = moonPathPoints.length > 0 ? new Date(moonPathPoints[moonPathPoints.length - 1].time).getTime() : null

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

      <IrradianceGroundOverlay
        points={irradianceGrid}
        originLat={irradianceOriginLat}
        originLon={irradianceOriginLon}
        markerRadiusM={irradianceMarkerRadiusM}
        visible={showIrradianceOverlay}
      />

      {blockFootprints.map((f) => (
        <BuildingMass key={f.blockId} minEast={f.minEast} maxEast={f.maxEast} minNorth={f.minNorth} maxNorth={f.maxNorth} mountType={mountType} />
      ))}

      {panels.map((panel) => (
        <PanelMesh
          key={`${panel.block_id}-${panel.row}-${panel.col}`}
          panel={panel}
          tiltDeg={tiltDeg}
          azimuthDeg={azimuthDeg}
          // Collapsed 2026-07-19 from two separate view modes (a per-panel
          // solar-access gradient vs. a static per-string color, switched
          // via an icon-rail toggle the user found confusing) into this one
          // "how is each panel reacting to the sun right now" gradient - per
          // the user's own request. `sunElevationDeg <= 0` forces every
          // panel to the gradient's 0% (red/off) end the instant the sun is
          // down, regardless of what zoneOutputRatio's own real-power
          // lookup computed - a deliberate belt-and-suspenders guard (not
          // just trusting that lookup to always land on a genuine zero) so
          // panels can never read as "producing" off residual moonlight or
          // a stale nearest-timestamp match landing on an earlier daytime
          // reading, the exact failure the user explicitly flagged.
          color={solarAccessColor(sunElevationDeg > 0 ? panel.solar_access_pct * zoneOutputRatio : 0)}
          baseY={panelBaseY}
        />
      ))}

      {sunPathLine.length > 1 && <Line points={sunPathLine} color="#f59e0b" lineWidth={1.5} />}
      <SunAngleDiagram azimuthDeg={sunAzimuthDeg} elevationDeg={sunElevationDeg} radius={angleDiagramRadius} />
      <SunMarker
        sunPathPoints={sunPathPoints}
        atIso={atIso}
        isPlaying={isPlaying}
        fallbackAzimuthDeg={sunAzimuthDeg}
        fallbackElevationDeg={sunElevationDeg}
        orbitRadius={sunOrbitRadius}
        sunRadius={sunRadius}
        glowRadius={sunGlowRadius}
        wrapStartMs={wrapStartMs}
        wrapEndMs={wrapEndMs}
        onAnimatedTimeChange={onAnimatedTimeChange}
      />
      {moonPathLine.length > 1 && <Line points={moonPathLine} color="#94a3b8" lineWidth={1} />}
      <MoonMarker
        moonPathPoints={moonPathPoints}
        sunPathPoints={sunPathPoints}
        atIso={atIso}
        isPlaying={isPlaying}
        fallbackMoonAzimuthDeg={moonAzimuthDeg}
        fallbackMoonElevationDeg={moonElevationDeg}
        fallbackSunElevationDeg={sunElevationDeg}
        orbitRadius={sunOrbitRadius}
        moonRadius={moonRadius}
        glowRadius={moonGlowRadius}
        wrapStartMs={wrapStartMs}
        wrapEndMs={wrapEndMs}
      />
      <CloudLayer
        center={bounds.full.center}
        span={bounds.full.span}
        opacityPct={cloudOpacityPct}
        motionSpeedKmh={cloudMotionSpeedKmh}
        motionDirectionDeg={cloudMotionDirectionDeg}
      />
      <RainLayer center={bounds.full.center} span={bounds.full.span} precipMm={precipMm} intensity={precipIntensity} />

      <OrbitControls ref={controlsRef} target={[focusCenterScene[0], panelBaseY, focusCenterScene[1]]} />
    </Canvas>
  )
}
