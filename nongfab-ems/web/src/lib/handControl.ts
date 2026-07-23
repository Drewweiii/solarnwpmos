// Pure hand-gesture -> camera-control mapping for the 3D View's optional
// webcam hand control (2026-07-23, "🖐️ ควบคุมด้วยมือ" Phase 1). This module is
// deliberately free of any DOM/MediaPipe/three imports so it's fully
// unit-testable: it takes normalized hand landmarks (what MediaPipe's
// HandLandmarker emits - 21 points, x/y in 0..1 image coords) and returns a
// normalized control signal, plus the exponential-smoothing helper the live
// loop uses so a jittery hand doesn't jitter the camera. The component
// (useHandTracking + Solar3DScene) turns the returned signal into actual
// azimuth/polar/distance - see those files. Sign choices here are the "feels
// natural in a selfie-mirrored webcam" defaults and are easy to flip.

export interface Landmark {
  x: number
  y: number
  z?: number
}

// A normalized control request, each component in a documented range so the
// scene can map it to real camera angles without knowing anything about hands.
export interface HandSignal {
  azimuthNorm: number // -1 (rotate one way) .. +1 (the other), 0 = centered
  polarNorm: number // 0 (look from high above) .. 1 (look from near the horizon)
  zoomNorm: number // 0 (far) .. 1 (near)
}

export const NEUTRAL_SIGNAL: HandSignal = { azimuthNorm: 0, polarNorm: 0.5, zoomNorm: 0.5 }

export function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v))
}

export function clampSym(v: number): number {
  return Math.max(-1, Math.min(1, v))
}

// MediaPipe hand landmark indices we use (subset of its 21-point model).
const WRIST = 0
const THUMB_TIP = 4
const INDEX_MCP = 5
const INDEX_TIP = 8
const MIDDLE_MCP = 9

function dist(a: Landmark, b: Landmark): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

/** Palm center, approximated as the mean of the wrist and the finger-base
 * knuckles (more stable than any single fingertip, which flick around). */
export function handCentroid(landmarks: Landmark[]): { x: number; y: number } {
  const pts = [landmarks[WRIST], landmarks[INDEX_MCP], landmarks[MIDDLE_MCP]].filter(Boolean)
  if (pts.length === 0) return { x: 0.5, y: 0.5 }
  return {
    x: pts.reduce((s, p) => s + p.x, 0) / pts.length,
    y: pts.reduce((s, p) => s + p.y, 0) / pts.length,
  }
}

/** Pinch amount, scale-invariant: the thumb-tip↔index-tip gap divided by the
 * hand's own size (wrist↔middle-knuckle), so it reads the same whether the
 * hand is near or far from the camera. ~0 fingers touching, ~1.5+ wide open. */
export function pinchRatio(landmarks: Landmark[]): number {
  const handScale = dist(landmarks[WRIST], landmarks[MIDDLE_MCP])
  if (handScale <= 1e-6) return 0
  return dist(landmarks[THUMB_TIP], landmarks[INDEX_TIP]) / handScale
}

// Tunable so the live layer / tests can adjust feel without touching the math.
export interface HandControlConfig {
  // Ignore tiny movements around center so a still hand keeps a still camera.
  deadzone: number
  // Pinch ratio that maps to fully zoomed-in / fully zoomed-out.
  pinchNearRatio: number
  pinchFarRatio: number
  // Whether the incoming x is already selfie-mirrored (MediaPipe on a mirrored
  // <video> gives x that grows to the right as the user moves their hand right).
  mirrored: boolean
}

export const DEFAULT_HAND_CONTROL_CONFIG: HandControlConfig = {
  deadzone: 0.06,
  pinchNearRatio: 0.25,
  pinchFarRatio: 1.3,
  mirrored: true,
}

function applyDeadzone(vSym: number, deadzone: number): number {
  if (Math.abs(vSym) <= deadzone) return 0
  // Re-scale so motion resumes smoothly from the deadzone edge, not with a jump.
  const sign = Math.sign(vSym)
  return clampSym(sign * ((Math.abs(vSym) - deadzone) / (1 - deadzone)))
}

/** Map one hand's landmarks to a normalized control signal. Hand left/right of
 * center -> azimuth; up/down -> polar; pinch open/closed -> zoom. Returns the
 * NEUTRAL signal for a missing/degenerate hand so callers can treat "no hand"
 * as "hold position". */
export function mapHandToSignal(
  landmarks: Landmark[] | null | undefined,
  config: HandControlConfig = DEFAULT_HAND_CONTROL_CONFIG,
): HandSignal {
  if (!landmarks || landmarks.length < 10) return NEUTRAL_SIGNAL
  const c = handCentroid(landmarks)
  // x,y in 0..1 -> symmetric -1..1 around the frame center.
  let xSym = (c.x - 0.5) * 2
  if (config.mirrored) xSym = -xSym
  const azimuthNorm = applyDeadzone(xSym, config.deadzone)
  // Hand high in frame (small y) -> look from above (polarNorm small).
  const polarNorm = clamp01((c.y - 0.15) / 0.7)
  // Pinch closed -> zoom in (near, zoomNorm high); open -> far.
  const pinch = pinchRatio(landmarks)
  const zoomNorm = clamp01((config.pinchFarRatio - pinch) / (config.pinchFarRatio - config.pinchNearRatio))
  return { azimuthNorm, polarNorm, zoomNorm }
}

/** Exponential smoothing toward a target signal - `factor` in (0,1], higher =
 * snappier. The live rAF loop calls this every frame so the camera glides. */
export function smoothSignal(prev: HandSignal, target: HandSignal, factor: number): HandSignal {
  const k = Math.max(0, Math.min(1, factor))
  const lerp = (a: number, b: number) => a + (b - a) * k
  return {
    azimuthNorm: lerp(prev.azimuthNorm, target.azimuthNorm),
    polarNorm: lerp(prev.polarNorm, target.polarNorm),
    zoomNorm: lerp(prev.zoomNorm, target.zoomNorm),
  }
}

// The scene-facing target: real spherical camera params. Kept here (pure) so the
// mapping from a normalized signal to angles/distance is testable too.
export interface CameraTarget {
  azimuth: number // radians
  polar: number // radians, from +Y down
  distance: number // scene units (meters)
}

export interface CameraRange {
  minDistance: number
  maxDistance: number
  // Polar clamps keep the camera from going under the ground or straight down.
  minPolar: number
  maxPolar: number
  azimuthSpan: number // how far azimuthNorm=±1 swings, radians
}

export function signalToCameraTarget(signal: HandSignal, range: CameraRange): CameraTarget {
  return {
    azimuth: signal.azimuthNorm * range.azimuthSpan,
    polar: range.minPolar + clamp01(signal.polarNorm) * (range.maxPolar - range.minPolar),
    distance: range.maxDistance + clamp01(signal.zoomNorm) * (range.minDistance - range.maxDistance),
  }
}
