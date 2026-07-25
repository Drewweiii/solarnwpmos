// Live "is the hand connected?" indicator for the 3D View's webcam hand control
// (2026-07-23, Phase 2 follow-up - the user asked for an explicit on/off mode
// and a sync readout that shows the hand is actually locked on, not just that
// the camera turned on). It maps the tracking status to a color-coded pill and,
// once a hand is being tracked, reads the live HandSignal ref in its OWN small
// requestAnimationFrame loop (throttled) so the "connected" state and the live
// movement bars update without ever re-rendering the heavy 3D scene above it.
import { useEffect, useRef, useState } from 'react'
import type { HandGesture, HandSignal } from '../lib/handControl'
import type { HandTrackingStatus } from '../lib/useHandTracking'

export interface HandSyncIndicatorProps {
  enabled: boolean
  status: HandTrackingStatus
  signalRef: React.MutableRefObject<HandSignal | null>
  gestureRef?: React.MutableRefObject<HandGesture>
}

// A short Thai label + emoji per control-mode gesture, shown as a live badge
// while a hand is tracked so the user sees which mode their pose selected.
const GESTURE_BADGE: Record<HandGesture, string> = {
  control: '✋ หมุนมุมกล้อง',
  zoom: '🤏 ซูมเข้า-ออก (ยกมือขึ้น/ลง)',
  pan: '🤟 เลื่อนภาพ (ซ้าย-ขวา-ขึ้น-ลง)',
  hold: '✊ หยุดค้าง',
  recenter: '✌️ รีเซ็ตมุมกล้อง',
  toggleRun: '👍 เริ่ม/หยุดการรัน 3D',
  none: '',
}

// One connection "phase" per status, with the Thai copy + the class the CSS
// colors on. `sync: true` is the terminal, green, "hand is locked on" state.
interface Phase {
  key: string
  label: string
  sync: boolean
}

function phaseFor(enabled: boolean, status: HandTrackingStatus): Phase {
  if (!enabled) return { key: 'off', label: 'โหมดควบคุมด้วยมือ: ปิดอยู่', sync: false }
  switch (status) {
    case 'requesting-camera':
      return { key: 'connecting', label: 'กำลังเชื่อมต่อกล้อง…', sync: false }
    case 'loading-model':
      return { key: 'connecting', label: 'กำลังโหลดโมเดลตรวจจับมือ…', sync: false }
    case 'no-hand':
      return { key: 'waiting', label: 'ยังไม่เจอมือ — ยกมือขึ้นให้กล้องเห็น', sync: false }
    case 'tracking':
      return { key: 'synced', label: '✅ เชื่อมต่อมือติดแล้ว (Hand connected)', sync: true }
    case 'error':
      return { key: 'error', label: 'เชื่อมต่อไม่สำเร็จ', sync: false }
    default:
      return { key: 'idle', label: 'กำลังเริ่มต้น…', sync: false }
  }
}

// Refresh the live bars ~15x/sec while synced - smooth enough to read as "live",
// cheap enough to not matter (only this tiny component re-renders).
const LIVE_REFRESH_MS = 66

export function HandSyncIndicator({ enabled, status, signalRef, gestureRef }: HandSyncIndicatorProps) {
  const phase = phaseFor(enabled, status)
  const synced = phase.sync
  const [live, setLive] = useState<HandSignal | null>(null)
  const [gesture, setGesture] = useState<HandGesture>('none')
  const rafRef = useRef(0)
  const lastRef = useRef(0)

  useEffect(() => {
    if (!synced) {
      setLive(null)
      setGesture('none')
      return
    }
    const tick = (t: number) => {
      if (t - lastRef.current >= LIVE_REFRESH_MS) {
        lastRef.current = t
        setLive(signalRef.current)
        setGesture(gestureRef?.current ?? 'control')
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [synced, signalRef, gestureRef])

  // azimuthNorm is -1..1 (0 centered); map to a 0..100% bar centered at 50%.
  const azimuthPct = live ? (live.azimuthNorm * 0.5 + 0.5) * 100 : 50
  const zoomPct = live ? live.zoomNorm * 100 : 0

  return (
    <div className={`solar3d-hand-sync solar3d-hand-sync-${phase.key}`} role="status" aria-live="polite">
      <span className="solar3d-hand-sync-dot" aria-hidden="true" />
      <span className="solar3d-hand-sync-label">{phase.label}</span>
      {synced && GESTURE_BADGE[gesture] && (
        <span className={`solar3d-hand-sync-gesture solar3d-hand-sync-gesture-${gesture}`}>{GESTURE_BADGE[gesture]}</span>
      )}
      {synced && (
        <span className="solar3d-hand-sync-bars" aria-hidden="true">
          <span className="solar3d-hand-sync-bar" title="ตำแหน่งมือ (หมุน)">
            <span className="solar3d-hand-sync-bar-fill solar3d-hand-sync-bar-azimuth" style={{ left: `${azimuthPct}%` }} />
          </span>
          <span className="solar3d-hand-sync-bar" title="ระยะซูม (หนีบนิ้ว)">
            <span className="solar3d-hand-sync-bar-fill solar3d-hand-sync-bar-zoom" style={{ width: `${zoomPct}%` }} />
          </span>
        </span>
      )}
    </div>
  )
}
