import { useEffect, useMemo, useState } from 'react'
import { IrradianceMapView } from '../components/IrradianceMapView'
import { useIrradianceMap } from '../lib/queries'
import { buildAtIso, minutesToHhMm, todayIso } from '../lib/timeScrub'
import './IrradianceMapPage.css'

const AUTO_PLAY_STEP_MINUTES = 15
const AUTO_PLAY_INTERVAL_MS = 400

export function IrradianceMapPage() {
  const [date, setDate] = useState(todayIso())
  const [timeOfDayMinutes, setTimeOfDayMinutes] = useState(12 * 60)
  const [isPlaying, setIsPlaying] = useState(false)
  const [showIrradiance, setShowIrradiance] = useState(true)
  const [showZones, setShowZones] = useState(true)

  const atIso = useMemo(() => buildAtIso(date, timeOfDayMinutes), [date, timeOfDayMinutes])
  const map = useIrradianceMap(atIso)

  useEffect(() => {
    if (!isPlaying) return
    const id = window.setInterval(() => {
      setTimeOfDayMinutes((prev) => (prev + AUTO_PLAY_STEP_MINUTES) % (24 * 60))
    }, AUTO_PLAY_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [isPlaying])

  return (
    <div className="irradiance-map-page">
      <div className="irradiance-map-sweep-controls">
        <label htmlFor="irradiance-map-date">Date</label>
        <input id="irradiance-map-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <label htmlFor="irradiance-map-time">Time (UTC)</label>
        <input
          id="irradiance-map-time"
          type="range"
          min={0}
          max={24 * 60 - 1}
          step={AUTO_PLAY_STEP_MINUTES}
          value={timeOfDayMinutes}
          onChange={(e) => setTimeOfDayMinutes(Number(e.target.value))}
        />
        <span className="irradiance-map-time-readout">{minutesToHhMm(timeOfDayMinutes)}</span>
        <button type="button" onClick={() => setIsPlaying((p) => !p)} aria-pressed={isPlaying}>
          {isPlaying ? 'Pause' : 'Play'}
        </button>
      </div>

      <div className="irradiance-map-layer-toggles" role="group" aria-label="Map layers">
        <label>
          <input
            type="checkbox"
            checked={showIrradiance}
            onChange={(e) => setShowIrradiance(e.target.checked)}
          />
          Irradiance overlay
        </label>
        <label>
          <input type="checkbox" checked={showZones} onChange={(e) => setShowZones(e.target.checked)} />
          Zone pins
        </label>
      </div>

      <div className="irradiance-map-readouts">
        {map.data && (
          <span className="irradiance-map-clearsky-readout">
            Clear-sky GHI: <strong>{map.data.clearsky_ghi_w_m2.toFixed(0)} W/m²</strong>
          </span>
        )}
        {map.data && map.data.sun.elevation_deg <= 0 && (
          <span className="irradiance-map-night-badge">Night - no irradiance</span>
        )}
      </div>

      <div className="irradiance-map-wrapper">
        {map.isLoading && <p className="forecast-status">Loading irradiance map…</p>}
        {map.data && (
          <IrradianceMapView
            grid={map.data.grid}
            zones={map.data.zones}
            showIrradiance={showIrradiance}
            showZones={showZones}
          />
        )}
      </div>

      <div className="irradiance-map-legend" aria-label="Irradiance color scale">
        <span>0 W/m²</span>
        <div className="irradiance-map-legend-bar" />
        <span>1000 W/m²</span>
      </div>
    </div>
  )
}
