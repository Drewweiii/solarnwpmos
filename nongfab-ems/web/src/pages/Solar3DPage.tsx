import { useEffect, useMemo, useState } from 'react'
import { Compass } from '../components/Compass'
import { Solar3DScene } from '../components/Solar3DScene'
import { ZoneSelector } from '../components/ZoneSelector'
import { useGeometry, useSunPath } from '../lib/queries'
import { buildAtIso, minutesToHhMm, todayIso } from '../lib/timeScrub'
import './Solar3DPage.css'

const REAL_ZONE_IDS = ['GIS', 'ISB', 'Jetty'] as const
const AUTO_PLAY_STEP_MINUTES = 15
const AUTO_PLAY_INTERVAL_MS = 400

export function Solar3DPage() {
  const [zone, setZone] = useState<string>(REAL_ZONE_IDS[0])
  const [viewMode, setViewMode] = useState<'access' | 'string'>('access')
  const [date, setDate] = useState(todayIso())
  const [timeOfDayMinutes, setTimeOfDayMinutes] = useState(12 * 60)
  const [isPlaying, setIsPlaying] = useState(false)

  const atIso = useMemo(() => buildAtIso(date, timeOfDayMinutes), [date, timeOfDayMinutes])

  const geometry = useGeometry(zone, atIso)
  const sunPath = useSunPath(zone, date)

  useEffect(() => {
    if (!isPlaying) return
    const id = window.setInterval(() => {
      setTimeOfDayMinutes((prev) => (prev + AUTO_PLAY_STEP_MINUTES) % (24 * 60))
    }, AUTO_PLAY_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [isPlaying])

  return (
    <div className="solar3d-page">
      <div className="solar3d-controls">
        <ZoneSelector value={zone} onChange={setZone} includeAll={false} />
        <div className="view-mode-toggle" role="tablist" aria-label="Panel color mode">
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'access'}
            className={viewMode === 'access' ? 'view-mode-tab active' : 'view-mode-tab'}
            onClick={() => setViewMode('access')}
          >
            Solar access
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'string'}
            className={viewMode === 'string' ? 'view-mode-tab active' : 'view-mode-tab'}
            onClick={() => setViewMode('string')}
          >
            String view
          </button>
        </div>
      </div>

      <div className="solar3d-sweep-controls">
        <label htmlFor="solar3d-date">Date</label>
        <input
          id="solar3d-date"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <label htmlFor="solar3d-time">Time (UTC)</label>
        <input
          id="solar3d-time"
          type="range"
          min={0}
          max={24 * 60 - 1}
          step={AUTO_PLAY_STEP_MINUTES}
          value={timeOfDayMinutes}
          onChange={(e) => setTimeOfDayMinutes(Number(e.target.value))}
        />
        <span className="solar3d-time-readout">{minutesToHhMm(timeOfDayMinutes)}</span>
        <button type="button" onClick={() => setIsPlaying((p) => !p)} aria-pressed={isPlaying}>
          {isPlaying ? 'Pause' : 'Play'}
        </button>
      </div>

      <div className="solar3d-readouts">
        {geometry.data && <Compass azimuthDeg={geometry.data.sun.azimuth_deg} elevationDeg={geometry.data.sun.elevation_deg} />}
        {geometry.data && (
          <div className="solar-access-readout">
            <span className="solar-access-value">{Math.round(geometry.data.average_solar_access_pct)}%</span>
            <span className="solar-access-label">avg solar access</span>
          </div>
        )}
        {geometry.data?.simulated_zone && (
          <span className="solar3d-simulated-badge">Simulated zone - no panels installed yet</span>
        )}
      </div>

      <div className="solar3d-canvas-wrapper">
        {geometry.isLoading && <p className="forecast-status">Loading geometry…</p>}
        {geometry.data && (
          <Solar3DScene
            panels={geometry.data.panels}
            tiltDeg={geometry.data.tilt_deg}
            azimuthDeg={geometry.data.azimuth_deg}
            sunAzimuthDeg={geometry.data.sun.azimuth_deg}
            sunElevationDeg={geometry.data.sun.elevation_deg}
            sunPathPoints={sunPath.data?.points ?? []}
            viewMode={viewMode}
          />
        )}
      </div>
    </div>
  )
}
