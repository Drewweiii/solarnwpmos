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

// The four non-thumb fingers as [pip, tip] pairs (proximal-interphalangeal
// joint and fingertip). A finger reads "extended" when its tip is farther from
// the wrist than its pip joint - orientation-robust (works whether the hand is
// upright or sideways), unlike a raw y-coordinate test.
const FINGER_PIP_TIP: ReadonlyArray<readonly [number, number]> = [
  [6, 8], // index
  [10, 12], // middle
  [14, 16], // ring
  [18, 20], // pinky
]

// The 21-point hand skeleton as landmark-index pairs, for drawing the live
// preview overlay (see components/HandPreview.tsx). Standard MediaPipe topology.
export const HAND_CONNECTIONS: ReadonlyArray<readonly [number, number]> = [
  [0, 1], [1, 2], [2, 3], [3, 4], // thumb
  [0, 5], [5, 6], [6, 7], [7, 8], // index
  [9, 10], [10, 11], [11, 12], // middle
  [13, 14], [14, 15], [15, 16], // ring
  [0, 17], [17, 18], [18, 19], [19, 20], // pinky
  [5, 9], [9, 13], [13, 17], // palm knuckle bridge
]

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

// --- Frame-rate-independent smoothing (Phase 2, 2026-07-23) ---------------
// The 3D camera eases toward the hand's requested pose every RENDER frame (up to
// 60fps), decoupled from however fast hand DETECTION runs - so motion stays
// buttery even when detection is slower than the display. `damp` is the same
// exponential smoothing THREE.MathUtils.damp uses: independent of the frame
// delta, so it looks identical at 30 or 120fps. Higher `lambda` = snappier.

export function damp(current: number, target: number, lambda: number, dt: number): number {
  if (dt <= 0) return current
  return current + (target - current) * (1 - Math.exp(-lambda * dt))
}

/** Wrap an angle to (-π, π]. */
export function wrapAngle(a: number): number {
  const twoPi = Math.PI * 2
  let x = (a + Math.PI) % twoPi
  if (x <= 0) x += twoPi
  return x - Math.PI
}

/** Damp an angle toward a target along the SHORTEST path, so e.g. rotating from
 * +170° to -170° sweeps 20° across the wrap seam, never 340° the long way. */
export function dampAngle(current: number, target: number, lambda: number, dt: number): number {
  if (dt <= 0) return current
  const delta = wrapAngle(target - current)
  return current + delta * (1 - Math.exp(-lambda * dt))
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

// --- Hand gestures / control modes (2026-07-23, "godlike" round) ------------
// On top of the continuous rotate/zoom signal, a few discrete POSES switch the
// control MODE so the camera does what the hand means, not just where it is:
//   - 'control'  : a normal open/relaxed hand - camera follows the signal.
//   - 'hold'     : a closed fist - freeze the camera where it is (rest your
//                  hand without the view drifting).
//   - 'recenter' : a two-finger "V"/peace sign - ease the camera back to a
//                  neutral home pose.
// 'none' means no usable hand this frame.
export type HandGesture = 'control' | 'hold' | 'recenter' | 'none'

/** Which of the four non-thumb fingers are extended, as [index, middle, ring,
 * pinky]. A finger is extended when its fingertip sits farther from the wrist
 * than its pip joint - orientation-independent, so it holds whether the palm
 * faces the camera upright or turned sideways. */
export function fingersExtended(landmarks: Landmark[]): boolean[] {
  const wrist = landmarks[WRIST]
  if (!wrist) return [false, false, false, false]
  return FINGER_PIP_TIP.map(([pip, tip]) => {
    const p = landmarks[pip]
    const t = landmarks[tip]
    if (!p || !t) return false
    // A small margin so a half-curled finger doesn't flicker between states.
    return dist(t, wrist) > dist(p, wrist) * 1.05
  })
}

/** Classify one hand's pose into a control-mode gesture. */
export function detectGesture(landmarks: Landmark[] | null | undefined): HandGesture {
  if (!landmarks || landmarks.length < 21) return 'none'
  const [index, middle, ring, pinky] = fingersExtended(landmarks)
  const extendedCount = [index, middle, ring, pinky].filter(Boolean).length
  // Peace/"V" sign: index + middle up, ring + pinky down -> recenter.
  if (index && middle && !ring && !pinky) return 'recenter'
  // Fist: nothing (or almost nothing) extended -> hold/freeze.
  if (extendedCount === 0) return 'hold'
  return 'control'
}

// --- One-Euro filter (2026-07-23) -------------------------------------------
// Replaces the plain fixed-alpha EMA for de-jittering the raw hand signal. The
// One-Euro filter (Casiez, Roussel & Vogel, 2012 - the de-facto standard for
// interactive hand/pointer input) adapts its smoothing to hand SPEED: it
// smooths hard when the hand is nearly still (killing sensor jitter) but barely
// at all when the hand moves fast (killing lag). That "still = steady, moving =
// responsive" behavior is exactly what a plain EMA can't do with one constant.

export interface OneEuroParams {
  // Baseline cutoff frequency (Hz) at zero speed - lower = smoother-but-laggier
  // when still.
  minCutoff: number
  // How much the cutoff opens up with speed - higher = less lag when moving.
  beta: number
  // Cutoff for the internal speed (derivative) estimate.
  dCutoff: number
}

export const DEFAULT_ONE_EURO_PARAMS: OneEuroParams = { minCutoff: 1.5, beta: 0.03, dCutoff: 1.0 }

export interface OneEuroState {
  xPrev: number
  dxPrev: number
  tPrev: number
  started: boolean
}

export function createOneEuroState(): OneEuroState {
  return { xPrev: 0, dxPrev: 0, tPrev: 0, started: false }
}

// Smoothing factor for a first-order low-pass at cutoff `fc` over timestep `dt`.
function oneEuroAlpha(fc: number, dt: number): number {
  const tau = 1 / (2 * Math.PI * fc)
  return 1 / (1 + tau / dt)
}

/** Advance a One-Euro filter by one sample. `t` is a timestamp in SECONDS.
 * Mutates and returns the filtered value. The first sample seeds the state and
 * passes through unchanged. */
export function oneEuroStep(
  state: OneEuroState,
  x: number,
  t: number,
  params: OneEuroParams = DEFAULT_ONE_EURO_PARAMS,
): number {
  if (!state.started) {
    state.started = true
    state.xPrev = x
    state.dxPrev = 0
    state.tPrev = t
    return x
  }
  let dt = t - state.tPrev
  if (dt <= 0) dt = 1e-3
  const dx = (x - state.xPrev) / dt
  const dxHat = state.dxPrev + oneEuroAlpha(params.dCutoff, dt) * (dx - state.dxPrev)
  const cutoff = params.minCutoff + params.beta * Math.abs(dxHat)
  const xHat = state.xPrev + oneEuroAlpha(cutoff, dt) * (x - state.xPrev)
  state.xPrev = xHat
  state.dxPrev = dxHat
  state.tPrev = t
  return xHat
}

/** A One-Euro filter over a whole HandSignal (one channel each). */
export interface HandSignalFilter {
  azimuth: OneEuroState
  polar: OneEuroState
  zoom: OneEuroState
}

export function createHandSignalFilter(): HandSignalFilter {
  return { azimuth: createOneEuroState(), polar: createOneEuroState(), zoom: createOneEuroState() }
}

export function filterHandSignal(
  filter: HandSignalFilter,
  signal: HandSignal,
  t: number,
  params: OneEuroParams = DEFAULT_ONE_EURO_PARAMS,
): HandSignal {
  return {
    azimuthNorm: oneEuroStep(filter.azimuth, signal.azimuthNorm, t, params),
    polarNorm: oneEuroStep(filter.polar, signal.polarNorm, t, params),
    zoomNorm: oneEuroStep(filter.zoom, signal.zoomNorm, t, params),
  }
}
