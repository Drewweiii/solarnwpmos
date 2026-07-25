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
  // At or below this pinch ratio the thumb and index read as TOUCHING, which is
  // what selects the zoom mode (see detectGesture).
  pinchEngageRatio: number
  // Multiplies the hand's offset-from-centre before it becomes a rate, so a
  // comfortable half-reach already commands full speed (see mapSignalToRates).
  rateGain: number
  // Whether the incoming x is already selfie-mirrored (MediaPipe on a mirrored
  // <video> gives x that grows to the right as the user moves their hand right).
  mirrored: boolean
}

export const DEFAULT_HAND_CONTROL_CONFIG: HandControlConfig = {
  deadzone: 0.06,
  pinchNearRatio: 0.25,
  pinchFarRatio: 1.3,
  pinchEngageRatio: 0.42,
  rateGain: 2.2,
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

// --- Hand gestures / control modes (2026-07-23, "godlike" round; reworked
// 2026-07-25 after the user reported zoom and left/right were hard to use) ---
// A few discrete POSES pick which AXIS the hand drives, so each gesture does one
// thing well instead of every axis moving at once:
//   - 'control'   : open hand - orbit (left/right = spin, up/down = height).
//   - 'zoom'      : a pinch (thumb + index touching) - move the pinched hand
//                   up/down to zoom in/out. Nothing else moves.
//   - 'pan'       : three fingers - slide the view target left/right/up/down.
//   - 'hold'      : a closed fist - freeze the camera where it is (rest your
//                   hand without the view drifting).
//   - 'recenter'  : a two-finger "V"/peace sign - ease the camera back to a
//                   neutral home pose.
//   - 'toggleRun' : 👍 thumbs-up - start/stop the 3D view's own time animation
//                   (edge-triggered via stepGestureLatch, so holding it up
//                   fires exactly once, not once per frame).
// 'none' means no usable hand this frame.
export type HandGesture = 'control' | 'zoom' | 'pan' | 'hold' | 'recenter' | 'toggleRun' | 'none'

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

// MediaPipe thumb chain: 1 CMC, 2 MCP, 3 IP, 4 TIP.
const THUMB_IP = 3

/** Whether the thumb is sticking out (as in 👍) rather than tucked across the
 * palm. Two conditions, both scale-invariant: the tip reaches farther from the
 * wrist than its IP joint, AND the tip sits well away from the index knuckle -
 * the second one is what separates a thumbs-up from a fist, where the thumb lies
 * folded right against the index finger. */
export function thumbExtended(landmarks: Landmark[]): boolean {
  const wrist = landmarks[WRIST]
  const ip = landmarks[THUMB_IP]
  const tip = landmarks[THUMB_TIP]
  const indexMcp = landmarks[INDEX_MCP]
  const middleMcp = landmarks[MIDDLE_MCP]
  if (!wrist || !ip || !tip || !indexMcp || !middleMcp) return false
  const handScale = dist(wrist, middleMcp)
  if (handScale <= 1e-6) return false
  const reachesOut = dist(tip, wrist) > dist(ip, wrist) * 1.05
  const clearOfPalm = dist(tip, indexMcp) / handScale > 0.55
  return reachesOut && clearOfPalm
}

/** Classify one hand's pose into a control-mode gesture. Order matters: the
 * poses that a looser test would also match (a fist's thumb is near the index
 * tip, so it reads as a "pinch") are checked first. */
export function detectGesture(
  landmarks: Landmark[] | null | undefined,
  config: HandControlConfig = DEFAULT_HAND_CONTROL_CONFIG,
): HandGesture {
  if (!landmarks || landmarks.length < 21) return 'none'
  const [index, middle, ring, pinky] = fingersExtended(landmarks)
  const extendedCount = [index, middle, ring, pinky].filter(Boolean).length
  // 👍 Thumbs-up: thumb clear of the palm with every finger curled -> play/pause.
  if (extendedCount === 0 && thumbExtended(landmarks)) return 'toggleRun'
  // ✊ Fist: nothing extended -> hold/freeze. Checked before the pinch because a
  // fist also brings the thumb and index tips together.
  if (extendedCount === 0) return 'hold'
  // 🤏 Pinch: the index has curled in to meet the thumb while at least one other
  // finger stays out -> zoom.
  if (!index && extendedCount > 0 && pinchRatio(landmarks) <= config.pinchEngageRatio) return 'zoom'
  // 🤟 Three fingers (index + middle + ring, pinky down) -> pan.
  if (index && middle && ring && !pinky) return 'pan'
  // ✌️ Peace/"V" sign: index + middle up, ring + pinky down -> recenter.
  if (index && middle && !ring && !pinky) return 'recenter'
  return 'control'
}

// --- Rate ("velocity") control (2026-07-25) ---------------------------------
// The original mapping was ABSOLUTE: hand position *was* camera position, so the
// reachable range was whatever your arm could span, every axis moved at once,
// and holding a zoom meant holding one exact finger aperture. That is what made
// zoom and left/right hard to use. These functions instead read the hand's
// offset from the frame centre as a RATE the caller integrates over time:
// push your hand right and the view keeps turning right for as long as you hold
// it (so any angle is reachable), bring it back to centre and motion stops.

export interface HandRates {
  azimuthRate: number // -1..1, + = spin one way
  polarRate: number // -1..1, + = camera moves down toward the horizon
  zoomRate: number // -1..1, + = zoom in (closer)
  panXRate: number // -1..1, + = slide the target right
  panYRate: number // -1..1, + = slide the target up
}

export const ZERO_RATES: HandRates = { azimuthRate: 0, polarRate: 0, zoomRate: 0, panXRate: 0, panYRate: 0 }

/** The hand's vertical offset from the frame centre as -1..1 (+ = hand HIGH),
 * recovered from the already-smoothed `polarNorm`. Pulled out of the signal
 * rather than the raw landmarks so it inherits the One-Euro de-jitter. */
export function verticalOffset(signal: HandSignal): number {
  return clampSym((0.5 - clamp01(signal.polarNorm)) * 2)
}

/** Turn one smoothed signal + the active gesture into per-axis rates. Exactly
 * one axis group is ever non-zero, which is the point: a gesture does one job.
 * `gain` amplifies the offset so a comfortable half-reach already commands full
 * speed (no need to stretch to the edge of frame). */
export function mapSignalToRates(
  signal: HandSignal | null | undefined,
  gesture: HandGesture,
  config: HandControlConfig = DEFAULT_HAND_CONTROL_CONFIG,
): HandRates {
  if (!signal) return ZERO_RATES
  const g = config.rateGain
  const horizontal = clampSym(signal.azimuthNorm * g) // already deadzoned + mirrored
  const vertical = clampSym(applyDeadzone(verticalOffset(signal), config.deadzone) * g)
  switch (gesture) {
    case 'control':
      // Hand high -> camera rises, i.e. polar (measured down from +Y) shrinks.
      // `|| 0` only normalizes the -0 that negating a zero produces.
      return { ...ZERO_RATES, azimuthRate: horizontal, polarRate: -vertical || 0 }
    case 'zoom':
      // Pinch and lift to move in, lower to pull back.
      return { ...ZERO_RATES, zoomRate: vertical }
    case 'pan':
      return { ...ZERO_RATES, panXRate: horizontal, panYRate: vertical }
    default:
      // 'hold' / 'recenter' / 'toggleRun' / 'none' command no continuous motion.
      return ZERO_RATES
  }
}

export interface HandCameraState {
  azimuth: number // radians
  polar: number // radians, from +Y down
  distance: number // scene units (meters)
}

export interface HandCameraLimits {
  azimuthSpeed: number // rad/s at full rate
  polarSpeed: number // rad/s at full rate
  // Zoom is MULTIPLICATIVE (fraction of the current distance per second), so it
  // feels equally responsive close up and far away - a fixed m/s would crawl
  // when zoomed out and overshoot when zoomed in.
  zoomSpeed: number
  minDistance: number
  maxDistance: number
  // Polar clamps keep the camera from going under the ground or straight down.
  minPolar: number
  maxPolar: number
}

/** Integrate one frame of rates into the spherical camera state, clamped. Pure:
 * returns a new state, never mutates. Azimuth is deliberately unclamped (it
 * wraps, so you can keep spinning all the way round). */
export function integrateHandCamera(state: HandCameraState, rates: HandRates, dt: number, limits: HandCameraLimits): HandCameraState {
  if (dt <= 0) return state
  const polar = state.polar + rates.polarRate * limits.polarSpeed * dt
  const distance = state.distance * Math.exp(-rates.zoomRate * limits.zoomSpeed * dt)
  return {
    azimuth: wrapAngle(state.azimuth + rates.azimuthRate * limits.azimuthSpeed * dt),
    polar: Math.max(limits.minPolar, Math.min(limits.maxPolar, polar)),
    distance: Math.max(limits.minDistance, Math.min(limits.maxDistance, distance)),
  }
}

// --- Edge-triggered gesture latch (2026-07-25) ------------------------------
// A pose is present on EVERY frame it's held, but "start/stop the animation"
// must fire once per gesture, not 60 times a second. The latch requires the pose
// to be held briefly (so a hand passing through the shape mid-transition doesn't
// trigger it), fires exactly once, then stays armed-off until the pose is
// released.

export interface GestureLatch {
  heldSeconds: number
  fired: boolean
}

export const DEFAULT_LATCH_HOLD_SECONDS = 0.35

export function createGestureLatch(): GestureLatch {
  return { heldSeconds: 0, fired: false }
}

/** Advance the latch by `dt` with the pose present or not. Returns true on the
 * single frame the gesture commits. Mutates `latch`. */
export function stepGestureLatch(
  latch: GestureLatch,
  present: boolean,
  dt: number,
  holdSeconds: number = DEFAULT_LATCH_HOLD_SECONDS,
): boolean {
  if (!present) {
    latch.heldSeconds = 0
    latch.fired = false
    return false
  }
  latch.heldSeconds += Math.max(0, dt)
  if (!latch.fired && latch.heldSeconds >= holdSeconds) {
    latch.fired = true
    return true
  }
  return false
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
