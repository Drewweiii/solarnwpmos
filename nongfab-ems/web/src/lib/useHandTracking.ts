// Webcam hand tracking for the 3D View's optional "🖐️ ควบคุมด้วยมือ" control
// (2026-07-23, Phase 1). ALL processing is on-device: the webcam frames go
// straight into MediaPipe's HandLandmarker in the browser and are never
// uploaded anywhere - only the derived normalized HandSignal (see
// lib/handControl.ts) leaves this hook, into a ref the 3D scene reads. Off by
// default; the camera is requested only when the user turns it on.
//
// The MediaPipe model + wasm load from a CDN, so like the satellite ground this
// cannot be visually confirmed in the egress-blocked dev sandbox (it surfaces a
// clear error state there) - it comes alive on a real deploy. Self-hosting the
// two files under web/public is the documented follow-up to drop the CDN.
import { useEffect, useRef, useState } from 'react'
import {
  DEFAULT_HAND_CONTROL_CONFIG,
  NEUTRAL_SIGNAL,
  mapHandToSignal,
  smoothSignal,
  type HandSignal,
} from './handControl'

const MEDIAPIPE_VERSION = '0.10.14'
const WASM_BASE = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MEDIAPIPE_VERSION}/wasm`
const HAND_MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'

// How fast the raw hand signal is pre-smoothed each detection frame. Kept LIGHT
// in Phase 2 (was 0.18) because the heavy, frame-rate-independent easing now
// lives on the RENDER side (Solar3DScene's HandCameraDriver dampens toward this
// target every render frame). Over-smoothing here would just add lag on top.
const SMOOTHING_FACTOR = 0.5

// Ask the camera for 60fps at a modest resolution: hand landmarking doesn't
// need full-res frames, and a smaller frame keeps per-frame inference fast
// enough to actually hit 60fps detection on mid-range mobile GPUs.
const VIDEO_CONSTRAINTS: MediaTrackConstraints = {
  facingMode: 'user',
  frameRate: { ideal: 60 },
  width: { ideal: 640 },
  height: { ideal: 480 },
}

// A <video> that also exposes requestVideoFrameCallback (not yet in TS's lib).
type VideoWithRVFC = HTMLVideoElement & {
  requestVideoFrameCallback?: (cb: (now: number) => void) => number
  cancelVideoFrameCallback?: (handle: number) => void
}

export type HandTrackingStatus =
  | 'idle'
  | 'requesting-camera'
  | 'loading-model'
  | 'tracking'
  | 'no-hand'
  | 'error'

export interface UseHandTrackingResult {
  status: HandTrackingStatus
  error: string | null
  // The scene reads this every frame (in useFrame) - a ref so hand motion never
  // triggers React re-renders. Holds the smoothed signal, or null when idle.
  signalRef: React.MutableRefObject<HandSignal | null>
  // Attach to a (hidden) <video> element the webcam stream feeds.
  videoRef: React.RefObject<HTMLVideoElement | null>
}

export function useHandTracking(enabled: boolean): UseHandTrackingResult {
  const [status, setStatus] = useState<HandTrackingStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const signalRef = useRef<HandSignal | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)

  useEffect(() => {
    if (!enabled) {
      signalRef.current = null
      setStatus('idle')
      setError(null)
      return
    }

    let cancelled = false
    let stream: MediaStream | null = null
    let usedVideo: VideoWithRVFC | null = null
    let landmarker: { detectForVideo: (v: HTMLVideoElement, t: number) => { landmarks?: unknown[][] }; close: () => void } | null = null
    let raf = 0
    let rvfc = 0
    let lastDetectTs = -1
    let smoothed: HandSignal = NEUTRAL_SIGNAL

    async function start() {
      try {
        setError(null)
        setStatus('requesting-camera')
        stream = await navigator.mediaDevices.getUserMedia({ video: VIDEO_CONSTRAINTS })
        if (cancelled) return
        const video = videoRef.current as VideoWithRVFC | null
        if (!video) throw new Error('no video element')
        usedVideo = video
        video.srcObject = stream
        await video.play()

        setStatus('loading-model')
        const vision = await import('@mediapipe/tasks-vision')
        const fileset = await vision.FilesetResolver.forVisionTasks(WASM_BASE)
        if (cancelled) return
        // Try the GPU delegate first (fast), fall back to CPU - some mobile
        // GPUs (older Android, certain iOS WebGL contexts) reject the GPU path.
        const build = (delegate: 'GPU' | 'CPU') =>
          vision.HandLandmarker.createFromOptions(fileset, {
            baseOptions: { modelAssetPath: HAND_MODEL_URL, delegate },
            runningMode: 'VIDEO',
            numHands: 1,
          })
        try {
          landmarker = (await build('GPU')) as unknown as typeof landmarker
        } catch {
          landmarker = (await build('CPU')) as unknown as typeof landmarker
        }
        if (cancelled) return
        setStatus('no-hand')

        // Run detection once per available frame. Driven by
        // requestVideoFrameCallback when the browser supports it (fires exactly
        // when a NEW camera frame is ready - up to the camera's 60fps, and never
        // wastefully re-running MediaPipe on a frame it already saw), falling
        // back to requestAnimationFrame elsewhere (iOS Safari lacked rVFC until
        // recently). `readyState >= 2` (HAVE_CURRENT_DATA) guards against
        // detecting on an un-decoded frame.
        const detectOnce = (tsMs: number) => {
          if (cancelled || !landmarker) return
          const v = videoRef.current as VideoWithRVFC | null
          if (!v || v.readyState < 2) return
          // MediaPipe rejects two detects with the same timestamp; nudge if equal.
          const ts = tsMs <= lastDetectTs ? lastDetectTs + 1 : tsMs
          lastDetectTs = ts
          let hands: unknown[][] | undefined
          try {
            hands = landmarker.detectForVideo(v, ts).landmarks
          } catch {
            // A transient detect error shouldn't kill the loop.
          }
          if (hands && hands.length > 0) {
            const target = mapHandToSignal(hands[0] as { x: number; y: number }[], DEFAULT_HAND_CONTROL_CONFIG)
            smoothed = smoothSignal(smoothed, target, SMOOTHING_FACTOR)
            signalRef.current = smoothed
            setStatus((s) => (s === 'tracking' ? s : 'tracking'))
          } else {
            signalRef.current = null
            setStatus((s) => (s === 'no-hand' ? s : 'no-hand'))
          }
        }

        const detectVideo = videoRef.current as VideoWithRVFC | null
        if (detectVideo && typeof detectVideo.requestVideoFrameCallback === 'function') {
          const rvfcLoop = (now: number) => {
            if (cancelled) return
            detectOnce(now)
            const v = videoRef.current as VideoWithRVFC | null
            if (!cancelled && v?.requestVideoFrameCallback) {
              rvfc = v.requestVideoFrameCallback(rvfcLoop)
            }
          }
          rvfc = detectVideo.requestVideoFrameCallback(rvfcLoop)
        } else {
          const rafLoop = () => {
            if (cancelled) return
            detectOnce(performance.now())
            raf = requestAnimationFrame(rafLoop)
          }
          raf = requestAnimationFrame(rafLoop)
        }
      } catch (e) {
        if (cancelled) return
        signalRef.current = null
        setStatus('error')
        setError(errorMessage(e))
      }
    }

    void start()

    return () => {
      cancelled = true
      if (raf) cancelAnimationFrame(raf)
      if (rvfc && usedVideo?.cancelVideoFrameCallback) {
        try {
          usedVideo.cancelVideoFrameCallback(rvfc)
        } catch {
          // ignore
        }
      }
      if (landmarker) {
        try {
          landmarker.close()
        } catch {
          // ignore
        }
      }
      if (stream) stream.getTracks().forEach((t) => t.stop())
      if (usedVideo) usedVideo.srcObject = null
      signalRef.current = null
    }
  }, [enabled])

  return { status, error, signalRef, videoRef }
}

function errorMessage(e: unknown): string {
  if (e instanceof DOMException && (e.name === 'NotAllowedError' || e.name === 'SecurityError')) {
    return 'ไม่ได้รับอนุญาตให้ใช้กล้อง - กดอนุญาตกล้องในเบราว์เซอร์แล้วลองใหม่'
  }
  if (e instanceof DOMException && e.name === 'NotFoundError') {
    return 'ไม่พบกล้องบนอุปกรณ์นี้'
  }
  // MediaPipe/wasm load failures often surface as a bare Event (no useful
  // message) - don't dump "[object Event]" at the user; only append a detail
  // when it's a real Error string.
  const detail = e instanceof Error && e.message ? ` (${e.message})` : ''
  return `เปิดการติดตามมือไม่สำเร็จ${detail} - โมเดลโหลดจากอินเทอร์เน็ต ต้องมีการเชื่อมต่อ`
}
