import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Compass } from '../components/Compass'
import { SolarAccessGauge } from '../components/SolarAccessGauge'
import type { Solar3DSceneHandle } from '../components/Solar3DScene'
import { Solar3DScene } from '../components/Solar3DScene'
import { Solar3DIconRail } from '../components/Solar3DIconRail'
import { Solar3DAssistants } from '../components/Solar3DAssistants'
import { ZoneSelector } from '../components/ZoneSelector'
import { nearestToTimestamp } from '../lib/chartData'
import { zenithAngleDeg } from '../lib/solar3d'
import {
  useCloudConditions,
  useForecast,
  useGeometry,
  useIrradianceMap,
  useMoonPath,
  usePerformance,
  usePrecipitationConditions,
  useSunPath,
  useZones,
} from '../lib/queries'
import { esriWorldImageryTileUrl } from '../lib/satelliteTile'
import { buildAtIso, minutesToHhMm, todayIso, utcMinutesToIctHhMm } from '../lib/timeScrub'
import './Solar3DPage.css'

const REAL_ZONE_IDS = ['GIS', 'ISB', 'Jetty'] as const
// Manual-drag slider granularity - the sun's own *animation* (icon rail
// play button) no longer uses this at all, see Solar3DScene.tsx's
// SunMarker, which interpolates continuously off the sun-path arc rather
// than stepping through fetched snapshots (the "laggy" motion reported live
// 2026-07-18). This only controls how coarsely a manual drag jumps.
const SLIDER_STEP_MINUTES = 5
// A date this far (either direction) from today falls outside every other
// page's own real-data window (Forecast's day-ahead reaches ~72h forward,
// generated-power history keeps ~72h back - see forecast/serving.py's
// MAX_DAY_AHEAD_HOURS/GENERATED_POWER_BACKFILL_HOURS) - shown as an honest
// caption rather than blocking date selection outright, since the sun/
// shading simulation itself is pure astronomy (pvlib) and has no such
// limit - see the caption's own copy below for the full explanation.
const REAL_DATA_WINDOW_DAYS = 3

function utcMinutesOfDay(iso: string): number {
  const d = new Date(iso)
  return d.getUTCHours() * 60 + d.getUTCMinutes()
}

export function Solar3DPage() {
  const [zone, setZone] = useState<string>(REAL_ZONE_IDS[0])
  const [groundStyle, setGroundStyle] = useState<'grid' | 'satellite'>('grid')
  const [date, setDate] = useState(todayIso())
  // Seeded to local noon UTC-minutes as a harmless placeholder before the
  // sun-path response arrives - overwritten by the effect below (once per
  // `date`) to the day's real sunrise the moment it's known, per the user's
  // own 2026-07-18 request ("ตำแหน่งดวงอาทิตย์เริ่มต้นไม่ได้อยู่ที่เที่ยงตรง
  // ...ควรเลือกให้ตรงกับช่วงที่ดวงอาทิตย์ขึ้นจริงๆ"). The value itself stays
  // UTC minutes-of-day internally (buildAtIso stamps it "Z"); only the
  // *displayed* readout is converted to Thai local time - see
  // timeScrub.ts's utcMinutesToIctHhMm for why that's display-only.
  const [timeOfDayMinutes, setTimeOfDayMinutes] = useState(5 * 60)
  const [isPlaying, setIsPlaying] = useState(false)
  const sceneRef = useRef<Solar3DSceneHandle>(null)
  // Whether the irradiance grid renders as colored points directly on the 3D
  // ground plane - literal single-image merge (2026-07-18) of what used to
  // be a separate MapLibre "Irradiance Map" section below the canvas (an
  // earlier 2026-07-18 round already pulled it onto this same page; this
  // round, per the user's explicit follow-up asking whether the two could
  // become one picture, moves the overlay itself INTO the WebGL scene - see
  // Solar3DScene.tsx's IrradianceGroundOverlay). Reuses the same
  // `irradiance` query this page's own GHI readout card already fetches, no
  // new network request.
  const [showIrradianceOverlay, setShowIrradianceOverlay] = useState(true)

  const atIso = useMemo(() => buildAtIso(date, timeOfDayMinutes), [date, timeOfDayMinutes])

  const geometry = useGeometry(zone, atIso)
  const sunPath = useSunPath(zone, date)
  // Full 24h (unfiltered) lunar arc for the Moon marker - see MoonMarker's
  // own docstring for why this, unlike sunPath, is NOT daylight-filtered.
  const moonPath = useMoonPath(zone, date)
  const zones = useZones()
  const cloudConditions = useCloudConditions()
  const precipitationConditions = usePrecipitationConditions()
  const irradiance = useIrradianceMap(atIso)

  // Defaults `timeOfDayMinutes` to the day's actual sunrise once per `date`
  // (not on every sunPath refetch/poll) - `sunPath.data.points` is already
  // filtered to daylight only (elevation_deg > 0, see routes_solar3d.py's
  // own /sun-path docstring), so its first point *is* sunrise, at 15-minute
  // resolution.
  const sunriseDefaultedForDate = useRef<string | null>(null)
  useEffect(() => {
    if (!sunPath.data || sunPath.data.points.length === 0) return
    if (sunriseDefaultedForDate.current === date) return
    sunriseDefaultedForDate.current = date
    setTimeOfDayMinutes(utcMinutesOfDay(sunPath.data.points[0].time))
  }, [sunPath.data, date])

  // Bridges Solar3DScene's own smooth (react-three-fiber `useFrame`, no
  // React re-render per frame) sun animation back to this page's slider/
  // readouts/panel-color fetch - already throttled on the Scene side (see
  // SYNC_CALLBACK_INTERVAL_MS), so this just does the UTC-minutes-of-day
  // conversion buildAtIso needs.
  const handleAnimatedTimeChange = useCallback((animatedAtIso: string) => {
    setTimeOfDayMinutes(utcMinutesOfDay(animatedAtIso))
  }, [])

  // Starting a fresh Play from a `date` left over from an earlier session
  // (the tab was open across a midnight, or a past/future date was picked
  // manually) used to keep replaying that stale day's sun/moon arc forever,
  // never catching up to today - per the user's own 2026-07-19 request
  // ("เมื่อ sim ใหม่ก็ให้...วันในการ sim ให้อัปเดตเลือกอัตโนมัติตามวันเวลาจริงๆ"),
  // hitting Play now snaps back to today's real date first (the existing
  // sunrise-default effect above then re-seeds `timeOfDayMinutes` for that
  // date the same way a normal date-picker change already does) - only
  // Play does this, not every render, so a manually-picked past/future date
  // still holds while paused for inspection.
  const handlePlayToggle = useCallback(() => {
    setIsPlaying((playing) => {
      if (!playing && date !== todayIso()) {
        setDate(todayIso())
      }
      return !playing
    })
  }, [date])

  const zoneObj = zones.data?.zones.find((z) => z.id === zone)
  // The zone's own real surveyed centroid (config/assets.yaml via
  // /assets), not the plant's one shared nominal center /geometry uses for
  // solar position - see lib/satelliteTile.ts's own docstring for the
  // "never confirmed to load from this sandbox" caveat on the fetch itself.
  const satelliteTileUrl = useMemo(
    () => (zoneObj ? esriWorldImageryTileUrl(zoneObj.centroid.lat, zoneObj.centroid.lon) : undefined),
    [zoneObj],
  )
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
  // Solar3DSceneProps' own `zoneOutputRatio` docstring). Falls back to the
  // *forecast* reading whenever no actual reading exists for the scrubbed
  // instant (2026-07-18 fix: `performance.data.hourly` only ever covers
  // "today", so scrubbing to any other date - or a future hour today - used
  // to silently show every panel as 0% output even though a real forecast
  // number was already fetched and shown as text a few lines below). No
  // real per-panel telemetry exists either way, so this is still the zone's
  // one aggregate reading applied uniformly, not a true per-panel value.
  const zoneCapacityKw = zoneObj?.ac_capacity_kw ?? 0
  const referencePowerKw = actualAtScrub?.ac_kw ?? forecastAtScrub?.pred ?? 0
  const zoneOutputRatio = zoneCapacityKw > 0 ? Math.max(0, Math.min(1, referencePowerKw / zoneCapacityKw)) : 1

  const daysFromToday = Math.round((new Date(`${date}T00:00:00Z`).getTime() - new Date(`${todayIso()}T00:00:00Z`).getTime()) / 86_400_000)
  const outOfRealDataWindow = Math.abs(daysFromToday) > REAL_DATA_WINDOW_DAYS

  const simulatedThaiDate = new Date(atIso).toLocaleDateString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
  const simulatedThaiTime = new Date(atIso).toLocaleTimeString('th-TH', {
    timeZone: 'Asia/Bangkok',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

  return (
    <div className="solar3d-page">
      <Solar3DAssistants />
      <div className="solar3d-controls">
        <ZoneSelector value={zone} onChange={setZone} includeAll={false} />
        {geometry.data && <SolarAccessGauge pct={geometry.data.average_solar_access_pct} />}
      </div>

      {/* Which instant is being simulated, in the same Thai-local-time
          convention every other page on this dashboard already uses (see
          root CLAUDE.md's Thailand-first standing policy) - per the user's
          own 2026-07-18 request ("เพิ่มเวลากำกับหน่อยว่าเรา simmulation
          วันที่เท่าไหร่ ให้เหมือนtab forecast"). */}
      <div className="solar3d-sim-clock">
        <span className="solar3d-sim-clock-label">กำลังจำลอง (Simulating)</span>
        <span className="solar3d-sim-clock-value">
          {simulatedThaiDate} - {simulatedThaiTime} น. (ICT)
        </span>
      </div>

      <div className="solar3d-sweep-controls">
        <label htmlFor="solar3d-date">Date</label>
        <input
          id="solar3d-date"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <label htmlFor="solar3d-time">Time (เวลาไทย ICT)</label>
        <input
          id="solar3d-time"
          type="range"
          min={0}
          max={24 * 60 - 1}
          step={SLIDER_STEP_MINUTES}
          value={timeOfDayMinutes}
          onChange={(e) => setTimeOfDayMinutes(Number(e.target.value))}
        />
        <span className="solar3d-time-readout">{utcMinutesToIctHhMm(timeOfDayMinutes)}</span>
        <span className="solar3d-time-utc-hint">({minutesToHhMm(timeOfDayMinutes)} UTC)</span>
      </div>

      {/* Scope/boundary note - per the user's own 2026-07-18 request to
          "บอกขอบเขตหน่อยว่าเรา gen 3D view วันไหนบ้าง". Deliberately not a
          hard min/max on the date input above: the sun-path/shading
          simulation is pure astronomical calculation (pvlib, via
          nongfab_features.clearsky) and is valid for literally any
          calendar date, past or future - only the Forecast/Actual readouts
          below depend on real accumulated data with a real window. */}
      <p className="solar3d-scope-note">
        การจำลองตำแหน่งดวงอาทิตย์/เงาบังแผงใช้ได้ทุกวันที่ (คำนวณจากตำแหน่งดาราศาสตร์จริง ไม่มีข้อจำกัดวันที่) - แต่ตัวเลข
        Forecast/Actual ด้านล่างมีข้อมูลจริงเฉพาะช่วง ~{REAL_DATA_WINDOW_DAYS} วันย้อนหลังถึงล่วงหน้าเท่านั้น
        {outOfRealDataWindow && (
          <strong className="solar3d-scope-note-warn"> - วันที่เลือกอยู่นอกช่วงนี้ Forecast/Actual ด้านล่างจะไม่มีข้อมูลจริง</strong>
        )}
      </p>

      <div className="solar3d-readouts">
        {geometry.data && (
          <>
            <Compass azimuthDeg={geometry.data.sun.azimuth_deg} elevationDeg={geometry.data.sun.elevation_deg} />
            {/* Explicitly labeled azimuth/altitude/zenith readouts (2026-07-18
                user request - the Compass above already carries the same
                numbers, but only as a bare "288° W"/"Alt: -17°" without the
                word "Azimuth" anywhere, which read as "missing" to the
                user). Mirrors the in-scene angle-diagram protractor below
                (Solar3DScene's SunAngleDiagram) so the 2D text and the 3D
                visualization always agree. */}
            <div className="solar3d-zenith-readout">
              <span className="solar3d-zenith-label">Azimuth</span>
              <span className="solar3d-zenith-value">{Math.round(geometry.data.sun.azimuth_deg)}&deg;</span>
            </div>
            <div className="solar3d-zenith-readout">
              <span className="solar3d-zenith-label">Altitude</span>
              <span className="solar3d-zenith-value">{Math.round(geometry.data.sun.elevation_deg)}&deg;</span>
            </div>
            <div className="solar3d-zenith-readout">
              <span className="solar3d-zenith-label">Zenith</span>
              <span className="solar3d-zenith-value">{Math.round(zenithAngleDeg(geometry.data.sun.elevation_deg))}&deg;</span>
            </div>
          </>
        )}
        {zoneObj && (
          <div className="solar3d-latlon-readout">
            <span className="solar3d-latlon-label">
              {zone} ({zoneObj.name_full})
            </span>
            <span className="solar3d-latlon-value">
              {zoneObj.centroid.lat.toFixed(5)}, {zoneObj.centroid.lon.toFixed(5)}
            </span>
          </div>
        )}
        {geometry.data?.simulated_zone && (
          <span className="solar3d-simulated-badge">Simulated zone - no panels installed yet</span>
        )}
      </div>

      {/* Made prominent per the user's own 2026-07-18 request ("ไม่เห็นมีส่วน
          ของแถบ irradiance...ทำตรงส่วนนี้ให้เด่นขึ้นหน่อย") - same
          clear-sky GHI IrradianceMapPage already shows, at the same
          scrubbed instant, so the two pages agree. */}
      {irradiance.data && (
        <div className="solar3d-irradiance-card">
          <span className="solar3d-irradiance-label">Clear-sky irradiance (GHI)</span>
          <span className="solar3d-irradiance-value">{irradiance.data.clearsky_ghi_w_m2.toFixed(0)} W/m&sup2;</span>
          {irradiance.data.sun.elevation_deg <= 0 && <span className="solar3d-irradiance-night">Night - no irradiance</span>}
        </div>
      )}

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
              isPlaying={isPlaying}
              onPlayToggle={handlePlayToggle}
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
              moonAzimuthDeg={geometry.data.moon.azimuth_deg}
              moonElevationDeg={geometry.data.moon.elevation_deg}
              moonPathPoints={moonPath.data?.points ?? []}
              atIso={atIso}
              isPlaying={isPlaying}
              onAnimatedTimeChange={handleAnimatedTimeChange}
              cloudOpacityPct={cloudConditions.data?.available ? (cloudConditions.data.cloud_opacity_pct ?? null) : null}
              cloudMotionSpeedKmh={cloudConditions.data?.available ? (cloudConditions.data.motion_speed_kmh ?? null) : null}
              cloudMotionDirectionDeg={cloudConditions.data?.available ? (cloudConditions.data.motion_direction_deg ?? null) : null}
              precipMm={precipitationConditions.data?.available ? (precipitationConditions.data.precip_mm ?? null) : null}
              precipIntensity={precipitationConditions.data?.available ? (precipitationConditions.data.intensity ?? null) : null}
              zone={zone}
              groundStyle={groundStyle}
              satelliteTileUrl={satelliteTileUrl}
              zoneOutputRatio={zoneOutputRatio}
              irradianceGrid={irradiance.data?.grid ?? []}
              irradianceOriginLat={zoneObj?.centroid.lat ?? 0}
              irradianceOriginLon={zoneObj?.centroid.lon ?? 0}
              showIrradianceOverlay={showIrradianceOverlay}
            />
          </>
        )}
      </div>

      {/* Single toggle + legend for the ground-point overlay now rendered
          INSIDE the canvas above (Solar3DScene's IrradianceGroundOverlay) -
          replaces the separate MapLibre "Irradiance Map" section + its 3
          layer toggles a prior 2026-07-18 round had here, per the user's
          own explicit follow-up asking to merge the two into one picture
          rather than two side by side. Zone pins/boundary toggles were
          dropped along with that separate map - this page already shows
          the one selected zone's own centroid (see solar3d-latlon-readout
          above) and its panels already draw the array's real footprint, so
          a second boundary outline added nothing this view didn't already
          have. */}
      <div className="solar3d-irradiance-overlay-toggle">
        <label>
          <input type="checkbox" checked={showIrradianceOverlay} onChange={(e) => setShowIrradianceOverlay(e.target.checked)} />
          แสดง irradiance เป็นจุดสีบนพื้นดิน (Irradiance ground overlay)
        </label>
        {showIrradianceOverlay && (
          <div className="solar3d-irradiance-map-legend" aria-label="Irradiance color scale">
            <span>0 W/m²</span>
            <div className="solar3d-irradiance-map-legend-bar" />
            <span>1000 W/m²</span>
          </div>
        )}
      </div>
    </div>
  )
}
