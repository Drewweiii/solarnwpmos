// Live webcam preview with the detected hand skeleton drawn on top (2026-07-23,
// "godlike" round). This is the "you can see exactly what the tracker sees"
// window: it draws the (mirrored) camera frame small, then overlays MediaPipe's
// 21 landmarks + bone connections so the user gets instant, tangible feedback
// that their hand is being read and how well. All of it stays on-device - it
// reads the same `videoRef`/`landmarksRef` the tracker already fills; nothing
// new leaves the browser. It runs its OWN requestAnimationFrame draw loop so it
// never re-renders React or touches the heavy 3D scene.
import { useEffect, useRef } from 'react'
import { HAND_CONNECTIONS, type HandGesture, type Landmark } from '../lib/handControl'

export interface HandPreviewProps {
  active: boolean
  videoRef: React.RefObject<HTMLVideoElement | null>
  landmarksRef: React.MutableRefObject<Landmark[] | null>
  gestureRef: React.MutableRefObject<HandGesture>
  width?: number
  height?: number
}

const GESTURE_COLOR: Record<HandGesture, string> = {
  control: '#22d3ee', // cyan - actively controlling
  hold: '#f59e0b', // amber - frozen
  recenter: '#a855f7', // purple - recentring
  none: '#64748b', // grey - no hand
}

export function HandPreview({ active, videoRef, landmarksRef, gestureRef, width = 176, height = 132 }: HandPreviewProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    if (!active) return
    let raf = 0
    const draw = () => {
      const canvas = canvasRef.current
      const video = videoRef.current
      const ctx = canvas?.getContext('2d')
      if (canvas && ctx) {
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        // Mirror horizontally so it reads like a selfie (moving right = right).
        ctx.save()
        ctx.translate(canvas.width, 0)
        ctx.scale(-1, 1)
        if (video && video.readyState >= 2) {
          try {
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
          } catch {
            // A not-yet-decodable frame - skip this draw, try next rAF.
          }
        } else {
          ctx.fillStyle = '#0b1220'
          ctx.fillRect(0, 0, canvas.width, canvas.height)
        }

        const landmarks = landmarksRef.current
        if (landmarks && landmarks.length >= 21) {
          const color = GESTURE_COLOR[gestureRef.current] ?? GESTURE_COLOR.control
          const px = (lm: Landmark) => lm.x * canvas.width
          const py = (lm: Landmark) => lm.y * canvas.height
          // Bones.
          ctx.strokeStyle = color
          ctx.lineWidth = 2
          ctx.beginPath()
          for (const [a, b] of HAND_CONNECTIONS) {
            const la = landmarks[a]
            const lb = landmarks[b]
            if (!la || !lb) continue
            ctx.moveTo(px(la), py(la))
            ctx.lineTo(px(lb), py(lb))
          }
          ctx.stroke()
          // Joints.
          ctx.fillStyle = '#ffffff'
          for (const lm of landmarks) {
            ctx.beginPath()
            ctx.arc(px(lm), py(lm), 2.5, 0, Math.PI * 2)
            ctx.fill()
          }
        }
        ctx.restore()
      }
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => {
      if (raf) cancelAnimationFrame(raf)
    }
  }, [active, videoRef, landmarksRef, gestureRef])

  if (!active) return null
  return (
    <div className="solar3d-hand-preview" aria-hidden="true">
      <canvas ref={canvasRef} width={width} height={height} data-testid="hand-preview-canvas" />
    </div>
  )
}
