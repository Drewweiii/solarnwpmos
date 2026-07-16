import { useEffect, useMemo, useState } from 'react'
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ZoneSelector } from '../components/ZoneSelector'
import {
  mergeGeneratedAndForecast,
  nearestToNow,
  pickHoursOfDay,
  sumForecastAcrossZones,
  sumHourlyAcrossZones,
  WEATHER_ICON_GLYPH,
  weatherIconFor,
} from '../lib/chartData'
import { ALL_ZONES_ID, useAllZonesForecast, useAllZonesPerformance, useForecast, usePerformance, useZones } from '../lib/queries'
import { formatHourUtc as formatHour } from '../lib/timeScrub'
import type { ForecastHorizon, ForecastPoint, HourlyPoint } from '../lib/types'
import './ForecastPage.css'

type HorizonToggle = 'day' | 'hour'

const WEATHER_HOURS = [6, 9, 12, 15]

export function ForecastPage() {
  const [zoneId, setZoneId] = useState(ALL_ZONES_ID)
  const [horizonToggle, setHorizonToggle] = useState<HorizonToggle>('day')
  const horizon: ForecastHorizon = horizonToggle

  const { data: registry } = useZones()

  const singleForecast = useForecast(zoneId, horizon)
  const singlePerformance = usePerformance(zoneId)
  const allPerformance = useAllZonesPerformance()
  const allForecast = useAllZonesForecast(horizon)

  const isAllZones = zoneId === ALL_ZONES_ID

  const hourly: HourlyPoint[] = useMemo(() => {
    if (isAllZones) return sumHourlyAcrossZones(allPerformance.map((q) => q.data?.hourly ?? []))
    return singlePerformance.data?.hourly ?? []
  }, [isAllZones, allPerformance, singlePerformance.data])

  const forecastPoints: ForecastPoint[] = useMemo(() => {
    if (isAllZones) return sumForecastAcrossZones(allForecast.map((q) => q.data?.points ?? []))
    return singleForecast.data?.points ?? []
  }, [isAllZones, allForecast, singleForecast.data])

  const chartRows = useMemo(() => mergeGeneratedAndForecast(hourly, forecastPoints), [hourly, forecastPoints])
  const weatherPoints = useMemo(() => pickHoursOfDay(hourly, WEATHER_HOURS), [hourly])
  const current = useMemo(() => nearestToNow(hourly), [hourly])

  const capacityKw = isAllZones
    ? (registry?.zones.reduce((sum, z) => sum + z.ac_capacity_kw, 0) ?? 0)
    : (registry?.zones.find((z) => z.id === zoneId)?.ac_capacity_kw ?? 0)

  const dailyEnergyKwh = isAllZones
    ? allPerformance.reduce((sum, q) => sum + (q.data?.ac_energy_kwh_today ?? 0), 0)
    : (singlePerformance.data?.ac_energy_kwh_today ?? 0)

  const plantFactor = capacityKw > 0 ? dailyEnergyKwh / (capacityKw * 24) : 0

  const isLoading = isAllZones
    ? allPerformance.some((q) => q.isLoading) || allForecast.some((q) => q.isLoading)
    : singlePerformance.isLoading || singleForecast.isLoading

  const forecastError = isAllZones ? allForecast.find((q) => q.error) : singleForecast.error ? singleForecast : undefined

  return (
    <div className="forecast-page">
      <div className="forecast-page-controls">
        <ZoneSelector value={zoneId} onChange={setZoneId} />
        <div className="horizon-toggle" role="tablist" aria-label="Forecast horizon">
          <button
            type="button"
            role="tab"
            aria-selected={horizonToggle === 'day'}
            className={horizonToggle === 'day' ? 'horizon-tab active' : 'horizon-tab'}
            onClick={() => setHorizonToggle('day')}
          >
            Day-ahead
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={horizonToggle === 'hour'}
            className={horizonToggle === 'hour' ? 'horizon-tab active' : 'horizon-tab'}
            onClick={() => setHorizonToggle('hour')}
          >
            Intra-day
          </button>
        </div>
      </div>

      <div className="kpi-row">
        <KpiCard label="Capacity" value={capacityKw.toFixed(1)} unit="kW" />
        <KpiCard label="Daily cumulative energy" value={dailyEnergyKwh.toFixed(1)} unit="kWh" />
        <KpiCard label="Power" value={(current?.ac_kw ?? 0).toFixed(1)} unit="kW" />
        <KpiCard label="Solar plant factor" value={plantFactor.toFixed(2)} unit="" />
      </div>

      {/* Per-zone info panel - inherently single-point (lat/lon), so only
          shown for one real zone, not the "All" (รวม) aggregate. */}
      {!isAllZones && singlePerformance.data && (
        <section className="zone-info-panel" aria-label="Zone info">
          <ZoneInfoItem label="Latitude" value={singlePerformance.data.latitude.toFixed(5)} />
          <ZoneInfoItem label="Longitude" value={singlePerformance.data.longitude.toFixed(5)} />
          <ZoneInfoItem label="Installed" value={`${capacityKw.toFixed(1)} kW`} />
          <ZoneInfoItem label="Estimated" value={`${dailyEnergyKwh.toFixed(1)} kWh`} />
          <ZoneInfoItem label="Plant factor" value={plantFactor.toFixed(2)} />
          <ZoneInfoItem label="Est. irradiance" value={`${(current?.ssrd_w_m2 ?? 0).toFixed(0)} W/m²`} />
          <ZoneInfoItem label="Cloud factor" value={`${(singlePerformance.data.cloud_factor * 100).toFixed(0)}%`} />
        </section>
      )}

      <div className="forecast-chart-row">
        <section className="forecast-chart-section" aria-label="Power forecast chart">
          {isLoading && <p className="forecast-status">Loading…</p>}
          {!isLoading && forecastError && (
            <p className="forecast-status forecast-status-warn">
              No {horizonToggle === 'day' ? 'day-ahead' : 'intra-day'} forecast model has been trained for this zone yet -
              showing generated power only.
            </p>
          )}
          {!isLoading && chartRows.length === 0 && <p className="forecast-status">No data yet.</p>}
          {chartRows.length > 0 && (
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={chartRows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="timestamp" tickFormatter={formatHour} minTickGap={24} />
                <YAxis unit=" kW" width={80} />
                <Tooltip
                  labelFormatter={(label) => (typeof label === 'string' ? formatHour(label) : String(label))}
                  formatter={(value) => (typeof value === 'number' ? value.toFixed(1) : String(value))}
                />
                <Legend />
                <Bar dataKey="generated" name="Generated power" fill="var(--accent)" fillOpacity={0.55} barSize={18} />
                <Area dataKey="lower" name="lower" stackId="pi" stroke="none" fill="transparent" legendType="none" />
                <Area
                  dataKey="band"
                  name="Prediction interval"
                  stackId="pi"
                  stroke="none"
                  fill="var(--chart-forecast)"
                  fillOpacity={0.2}
                />
                <Line
                  dataKey="pred"
                  name="Forecast"
                  stroke="var(--chart-forecast)"
                  strokeWidth={2}
                  dot={{ r: 2 }}
                  connectNulls
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </section>
        <LiveClock />
      </div>

      <section className="weather-strip" aria-label="Weather forecast">
        {weatherPoints.map((point) => (
          <div key={point.timestamp} className="weather-strip-item">
            <span className="weather-strip-hour">{formatHour(point.timestamp)}</span>
            <span className="weather-strip-icon" aria-hidden="true">
              {WEATHER_ICON_GLYPH[weatherIconFor(point.ssrd_w_m2)]}
            </span>
            <span className="weather-strip-temp">{point.temp_c.toFixed(1)}°C</span>
          </div>
        ))}
      </section>
    </div>
  )
}

interface KpiCardProps {
  label: string
  value: string
  unit: string
}

function KpiCard({ label, value, unit }: KpiCardProps) {
  return (
    <div className="kpi-card">
      <span className="kpi-card-label">{label}</span>
      <span className="kpi-card-value">
        {value}
        {unit && <span className="kpi-card-unit"> {unit}</span>}
      </span>
    </div>
  )
}

interface ZoneInfoItemProps {
  label: string
  value: string
}

function ZoneInfoItem({ label, value }: ZoneInfoItemProps) {
  return (
    <div className="zone-info-item">
      <span className="zone-info-label">{label}</span>
      <span className="zone-info-value">{value}</span>
    </div>
  )
}

// Shows both Thai local time and UTC side by side - the chart's own x-axis
// is UTC-labeled (formatHourUtc), and this whole app has a history of "why
// don't the numbers match what time it really is in Thailand" confusion
// (see web/README.md's 2026-07-16 dated entries) - a visible live clock
// naming both zones directly next to the chart heads that off rather than
// making the user do the +7h math themselves.
function LiveClock() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])

  const thaiDate = now.toLocaleDateString('th-TH', { timeZone: 'Asia/Bangkok', day: 'numeric', month: 'long', year: 'numeric' })
  const thaiTime = now.toLocaleTimeString('th-TH', {
    timeZone: 'Asia/Bangkok',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
  const utcTime = now.toLocaleTimeString('en-GB', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })

  return (
    <aside className="forecast-clock-block" aria-label="Current date and time">
      <span className="forecast-clock-time">{thaiTime}</span>
      <span className="forecast-clock-tz">เวลาไทย (ICT)</span>
      <span className="forecast-clock-date">{thaiDate}</span>
      <div className="forecast-clock-utc-row">
        <span className="forecast-clock-utc">{utcTime} UTC</span>
        <span className="forecast-clock-hint">(แกนเวลาในกราฟใช้ UTC)</span>
      </div>
    </aside>
  )
}
