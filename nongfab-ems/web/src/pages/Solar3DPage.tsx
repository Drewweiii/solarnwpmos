import { useEffect, useMemo, useRef, useState } from 'react'
import { Compass } from '../components/Compass'
import { SolarAccessGauge } from '../components/SolarAccessGauge'
import type { Solar3DSceneHandle } from '../components/Solar3DScene'
import { Solar3DScene } from '../components/Solar3DScene'
import { Solar3DIconRail } from '../components/Solar3DIconRail'
import { ZoneSelector } from '../components/ZoneSelector'
import { nearestToTimestamp } from '../lib/chartData'
import { useForecast, useGeometry, usePerformance, useSunPath, useZones } from '../lib/queries'
import { esriWorldImageryTileUrl } from '../lib/satelliteTile'
import { buildAtIso, minutesToHhMm, todayIso } from '../lib/timeScrub'
import './Solar3DPage.css'

const REAL_ZONE_IDS = ['GIS', 'ISB', 'Jetty'] as const
const AUTO_PLAY_STEP_MINUTES = 15
const AUTO_PLAY_INTERVAL_MS = 400

export function Solar3DPage() {
  const [zone, setZone] = useState<string>(REAL_ZONE_IDS[0])
  const [viewMode, setViewMode] = useState<'access' | 'string'>('access')
  const [groundStyle, setGroundStyle] = useState<'grid' | 'satellite'>('grid')
  const [date, setDate] = useState(todayIso())
  // Default to ~local noon (Asia/Bangkok, UTC+7) instead of 12:00 UTC
  // (=19:00 ICT, nighttime) - the slider is UTC-indexed and correctly
  // labeled as such, but a Thailand plant's first-open view showing a dark
  // scene with every panel red was a bad first impression (see
  // web/README.md's "Known gaps", now resolved here 2026-07-16).
  const [timeOfDayMinutes, setTimeOfDayMinutes] = useState(5 * 60)
  const [isPlaying, setIsPlaying] = useState(false)
  const sceneRef = useRef<Solar3DSceneHandle>(null)

  const atIso = useMemo(() => buildAtIso(date, timeOfDayMinutes), [date, timeOfDayMinutes])

  const geometry = useGeometry(zone, atIso)
  const sunPath = useSunPath(zone, date)
  const zones = useZones()
  // The zone's own real surveyed centroid (config/assets.yaml via
  // /assets), not the plant's one shared nominal center /geometry uses for
  // solar position - see lib/satelliteTile.ts's own docstring for the
  // "never confirmed to load from this sandbox" caveat on the fetch itself.
  const satelliteTileUrl = useMemo(() => {
    const zoneObj = zones.data?.zones.find((z) => z.id === zone)
    return zoneObj ? esriWorldImageryTileUrl(zoneObj.centroid.lat, zoneObj.centroid.lon) : undefined
  }, [zones.data, zone])
  // Feature C <-> Feature A: as the sun-path scrub moves, look up the
  // nearest day-ahead forecast point and the nearest actual/generated
  // point to that same scrubbed instant, so the 3D view can show
  // actual-vs-forecast alongside the sun position - not just a standalone
  // 3D scene disconnected from Feature A's own forecast data.
  const forecast = useForecast(zone, 'day')
  const performance = usePerformance(zone)
  const forecastAtScrub = useMemo(() => nearestToTimestamp(forecast.data?.points ?? [], atIso), [forecast.data, atIso])
  const actualAtScrub = useMemo(() => nearestToTimestamp(performance.data?.hourly ?? [], atIso), [performance.data, atIso])
  // Drives panel-color-by-real-output in 'access' view mode (see
  // Solar3DSceneProps' own `zoneOutputRatio` docstring) - approved
  // 2026-07-16 over keeping the coloring pure-shading-based. No real
  // per-panel telemetry exists, so this is the zone's one aggregate
  // current output ratio applied uniformly, not a true per-panel reading.
  const zoneCapacityKw = zones.data?.zones.find((z) => z.id === zone)?.ac_capacity_kw ?? 0
  const zoneOutputRatio =
    zoneCapacityKw > 0 ? Math.max(0, Math.min(1, (actualAtScrub?.ac_kw ?? 0) / zoneCapacityKw)) : 1

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
        {geometry.data && <SolarAccessGauge pct={geometry.data.average_solar_access_pct} />}
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
      </div>

      <div className="solar3d-readouts">
        {geometry.data && <Compass azimuthDeg={geometry.data.sun.azimuth_deg} elevationDeg={geometry.data.sun.elevation_deg} />}
        {geometry.data?.simulated_zone && (
          <span className="solar3d-simulated-badge">Simulated zone - no panels installed yet</span>
        )}
      </div>

      <div className="solar3d-forecast-readout" aria-label="Forecast vs actual comparison">
        <span className="solar3d-forecast-item">
          Forecast:{' '}
          {forecastAtScrub ? (
            <strong>{forecastAtScrub.pred.toFixed(1)} kW</strong>
          ) : forecast.error ? (
            <span className="solar3d-forecast-unavailable">no model trained yet</span>
          ) : (
            <span className="solar3d-forecast-unavailable">—</span>
          )}
        </span>
        <span className="solar3d-forecast-item">
          Actual: <strong>{actualAtScrub ? `${actualAtScrub.ac_kw.toFixed(1)} kW` : '—'}</strong>
        </span>
      </div>

      {geometry.data && geometry.data.string_balance.some((b) => b.exceeds_limit) && (
        <div className="solar3d-string-balance-warning" role="alert">
          ⚠ String power imbalance exceeds design limit:{' '}
          {geometry.data.string_balance
            .filter((b) => b.exceeds_limit)
            .map((b) => `${b.block_id} (${b.imbalance_kw.toFixed(2)} kW > ${b.max_allowed_kw?.toFixed(1)} kW)`)
            .join(', ')}
        </div>
      )}

      <div className="solar3d-canvas-wrapper">
        {geometry.isLoading && <p className="forecast-status">Loading geometry…</p>}
        {geometry.data && (
          <>
            <Solar3DIconRail
              viewMode={viewMode}
              onViewModeChange={setViewMode}
              isPlaying={isPlaying}
              onPlayToggle={() => setIsPlaying((p) => !p)}
              onResetCamera={() => sceneRef.current?.resetCamera()}
              groundStyle={groundStyle}
              onGroundStyleChange={setGroundStyle}
            />
            <Solar3DScene
              ref={sceneRef}
              panels={geometry.data.panels}
              tiltDeg={geometry.data.tilt_deg}
              azimuthDeg={geometry.data.azimuth_deg}
              sunAzimuthDeg={geometry.data.sun.azimuth_deg}
              sunElevationDeg={geometry.data.sun.elevation_deg}
              sunPathPoints={sunPath.data?.points ?? []}
              viewMode={viewMode}
              zone={zone}
              groundStyle={groundStyle}
              satelliteTileUrl={satelliteTileUrl}
              zoneOutputRatio={zoneOutputRatio}
            />
          </>
        )}
      </div>
    </div>
  )
}
