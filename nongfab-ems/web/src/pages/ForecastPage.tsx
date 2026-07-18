import { useEffect, useMemo, useState } from 'react'
import type { DotItemDotProps } from 'recharts'
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ZoneSelector } from '../components/ZoneSelector'
import { WeatherStrip } from '../components/WeatherStrip'
import {
  buildCompetitionRows,
  exactTimeKey,
  filterToRecentPast,
  mergeGeneratedAndForecast,
  nearestToNow,
  sumForecastAcrossZones,
  sumGeneratedPowerHistoryAcrossZones,
  sumHourlyAcrossZones,
  truncateGeneratedToNow,
} from '../lib/chartData'
import type { ChartRow, CompetitionRow } from '../lib/chartData'
import {
  ALL_ZONES_ID,
  useAllZonesForecast,
  useAllZonesPerformance,
  useForecast,
  usePerformance,
  useWeatherStrip,
  useZones,
} from '../lib/queries'
import { useForecastHistory } from '../lib/forecastHistory'
import { formatDateHourIct, formatHourIct as formatHour } from '../lib/timeScrub'
import type { ForecastHorizon, ForecastPoint, GeneratedPowerPoint, HourlyPoint } from '../lib/types'
import './ForecastPage.css'

type HorizonToggle = 'day' | 'hour'

// Intra-day's k-step forecast auto-selects LightGBM vs Random Forest vs
// Sum-k LSTM independently per lead hour (see forecast/hour_ahead.py's
// HourAheadKStepModel) - coloring each point's dot by which one actually won
// is what makes that adaptive selection visible instead of just claimed in
// the model-info panel text.
const ALGORITHM_DOT_COLOR: Record<string, string> = {
  lightgbm: 'var(--chart-lgbm)',
  random_forest: 'var(--chart-rf)',
  sum_k_lstm: 'var(--chart-sumk)',
}

const ALGORITHM_LABEL: Record<string, string> = {
  lightgbm: 'LightGBM',
  random_forest: 'Random Forest',
  sum_k_lstm: 'Sum-k LSTM',
}

function forecastDot(props: DotItemDotProps) {
  const { cx, cy, payload, index } = props
  if (cx == null || cy == null) return null
  const color = (payload?.algorithm && ALGORITHM_DOT_COLOR[payload.algorithm]) || 'var(--chart-forecast)'
  return <circle key={`forecast-dot-${index}`} cx={cx} cy={cy} r={3} fill={color} stroke={color} />
}

export function ForecastPage() {
  const [zoneId, setZoneId] = useState(ALL_ZONES_ID)
  const [horizonToggle, setHorizonToggle] = useState<HorizonToggle>('day')
  const horizon: ForecastHorizon = horizonToggle

  const { data: registry } = useZones()

  const singleForecast = useForecast(zoneId, horizon)
  const singlePerformance = usePerformance(zoneId)
  const allPerformance = useAllZonesPerformance()
  const allForecast = useAllZonesForecast(horizon)
  const weatherStrip = useWeatherStrip()

  // Minute-ahead (CNN-LSTM) is a fixed near-real-time horizon, not part of
  // the Day-ahead/Intra-day toggle above - shown in its own always-visible
  // panel (see MinuteAheadPanel below) rather than merged onto the main
  // chart's hourly-bucketed x-axis, since 10-min-resolution points would
  // distort that axis's spacing.
  const singleMinuteForecast = useForecast(zoneId, 'minute')
  const allMinuteForecast = useAllZonesForecast('minute')

  // The Model Competition panel (below) always shows the hour-ahead 3-way
  // race regardless of which Day-ahead/Intra-day tab is active - same
  // "always-visible, not gated by the main toggle" pattern as Minute-ahead
  // above. Shares the exact same react-query cache key ['forecast', zone,
  // 'hour'] as `singleForecast`/`allForecast` above when horizonToggle is
  // already 'hour', so this is a no-op extra network request in that case,
  // not a duplicate poll.
  const singleHourForecast = useForecast(zoneId, 'hour')
  const allHourForecast = useAllZonesForecast('hour')

  const isAllZones = zoneId === ALL_ZONES_ID

  const hourly: HourlyPoint[] = useMemo(() => {
    if (isAllZones) return sumHourlyAcrossZones(allPerformance.map((q) => q.data?.hourly ?? []))
    return singlePerformance.data?.hourly ?? []
  }, [isAllZones, allPerformance, singlePerformance.data])

  // Persisted actual/generated power for *previous* days (2026-07-18) -
  // `hourly` above is always "today" only, see /performance's own docstring.
  // Same isAllZones aggregation pattern as `hourly` just above.
  const generatedHistory: GeneratedPowerPoint[] = useMemo(() => {
    if (isAllZones) return sumGeneratedPowerHistoryAcrossZones(allPerformance.map((q) => q.data?.history ?? []))
    return singlePerformance.data?.history ?? []
  }, [isAllZones, allPerformance, singlePerformance.data])

  const latestForecastPoints: ForecastPoint[] = useMemo(() => {
    if (isAllZones) return sumForecastAcrossZones(allForecast.map((q) => q.data?.points ?? []))
    return singleForecast.data?.points ?? []
  }, [isAllZones, allForecast, singleForecast.data])

  // Accumulates every forecast point ever fetched this session instead of
  // only the latest poll's forward-looking window, so the Forecast line and
  // Prediction interval band don't vanish for an hour just because it's now
  // in the past - see forecastHistory.ts's own docstring (2026-07-18).
  const forecastPoints = useForecastHistory(latestForecastPoints, `${zoneId}:${horizon}`)

  const chartRows = useMemo(
    () => truncateGeneratedToNow(mergeGeneratedAndForecast(hourly, forecastPoints, generatedHistory)),
    [hourly, forecastPoints, generatedHistory],
  )
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

  // Whether the currently-shown forecast (and its prediction-interval band)
  // came from the physics-only fallback rather than a trained ML model - see
  // types.ts's ForecastResponse.model_type docstring. Drives the honest
  // caption below the chart rather than letting the fixed +/-20% band look
  // like a real quantile model's output.
  const isPhysicsBaseline = isAllZones
    ? allForecast.some((q) => q.data?.model_type === 'physics_baseline')
    : singleForecast.data?.model_type === 'physics_baseline'

  // Whether the Intra-day chart currently on screen has any real per-lead-hour
  // algorithm attribution to show (hour-ahead only, and only once a real
  // model has trained - the physics fallback has no algorithm at all). Drives
  // the green/orange dot legend caption.
  const showsAlgorithmDots = horizonToggle === 'hour' && chartRows.some((r) => r.algorithm != null)

  const latestMinutePoints: ForecastPoint[] = useMemo(() => {
    // exactTimeKey, not the default hourKey - minute-ahead's 10-minute-
    // resolution points routinely share an hour, which hourKey would wrongly
    // collapse (see chartData.ts's own docstring on this bug, found live 2026-07-17).
    if (isAllZones) return sumForecastAcrossZones(allMinuteForecast.map((q) => q.data?.points ?? []), exactTimeKey)
    return singleMinuteForecast.data?.points ?? []
  }, [isAllZones, allMinuteForecast, singleMinuteForecast.data])

  // Client-side accumulation (same hook as the main Day-ahead/Intra-day
  // chart, see forecastHistory.ts's own docstring) so the Minute-ahead
  // panel can also show its own forecast line looking ~30 min backward, not
  // just forward - minute-ahead has no server-side persistence (see
  // forecast/serving.py's FORECAST_HISTORY_LOOKBACK_HOURS, which excludes
  // "minute" on purpose), so this client-side accumulator is the only
  // source for that - per the user's own 2026-07-18 request.
  const accumulatedMinutePoints = useForecastHistory(latestMinutePoints, `minute:${zoneId}`)
  const minutePoints = useMemo(
    () => filterToRecentPast(accumulatedMinutePoints, new Date().toISOString(), 30),
    [accumulatedMinutePoints],
  )

  // Actual/generated power to overlay on the Minute-ahead panel too (the
  // user's own request) - reuses the exact same hourly-resolution 3-tier
  // rows already computed for the main chart (`chartRows`), just narrowed
  // to a window around "now" wide enough to always include the current and
  // previous hour's reading even though the Minute-ahead panel's own x-axis
  // only spans ~90 minutes. There is no minute-resolution actual-power data
  // source anywhere in this system (see forecast/README.md's "Actual/
  // generated power history" entry) - hourly is the finest granularity
  // available, so a handful of sparse points is the honest result here, not
  // a smoothed-over approximation.
  const minuteWindowActualRows = useMemo(() => {
    const nowMs = Date.now()
    // 90 min either side - roughly matches the Minute-ahead panel's own
    // visible span (30 min back, 60 min forward), wide enough to reliably
    // catch at least one hourly actual-power reading without stretching the
    // shared x-axis much further than the panel's own forecast points do.
    const windowMs = 90 * 60 * 1000
    return chartRows.filter((r) => Math.abs(new Date(r.timestamp).getTime() - nowMs) <= windowMs)
  }, [chartRows])

  const minuteLoading = isAllZones
    ? allMinuteForecast.some((q) => q.isLoading)
    : singleMinuteForecast.isLoading
  const minuteError = isAllZones ? allMinuteForecast.find((q) => q.error) : singleMinuteForecast.error ? singleMinuteForecast : undefined
  const minuteIsPhysicsBaseline = isAllZones
    ? allMinuteForecast.some((q) => q.data?.model_type === 'physics_baseline')
    : singleMinuteForecast.data?.model_type === 'physics_baseline'

  const hourAheadPoints: ForecastPoint[] = useMemo(() => {
    if (isAllZones) return sumForecastAcrossZones(allHourForecast.map((q) => q.data?.points ?? []))
    return singleHourForecast.data?.points ?? []
  }, [isAllZones, allHourForecast, singleHourForecast.data])

  const competitionRows = useMemo(() => buildCompetitionRows(hourAheadPoints), [hourAheadPoints])

  const competitionLoading = isAllZones ? allHourForecast.some((q) => q.isLoading) : singleHourForecast.isLoading
  const competitionError = isAllZones
    ? allHourForecast.find((q) => q.error)
    : singleHourForecast.error
      ? singleHourForecast
      : undefined

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

      <ViewerGuidePanel />

      <details className="model-info-panel">
        <summary>ℹ️ โมเดลพยากรณ์ที่ใช้ในหน้านี้ / Forecast models used here</summary>
        <table className="model-info-table">
          <thead>
            <tr>
              <th>โหมด (Horizon)</th>
              <th>โมเดล (Model)</th>
              <th>ช่วงเวลา (Range)</th>
              <th>ใช้เพื่อ (Purpose)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <strong>Day-ahead</strong>
                <br />
                พยากรณ์รายวัน
              </td>
              <td>NeuralProphet</td>
              <td>ล่วงหน้าสูงสุด 72 ชม. (3 วัน)</td>
              <td>ดูแนวโน้มการผลิตไฟฟ้าล่วงหน้าหลายวัน สำหรับวางแผนระยะกลาง</td>
            </tr>
            <tr>
              <td>
                <strong>Intra-day</strong>
                <br />
                พยากรณ์ภายในวัน
              </td>
              <td>LightGBM / Random Forest / Sum-k LSTM (ระบบเลือกตัวที่แม่นยำกว่าอัตโนมัติในแต่ละชั่วโมง)</td>
              <td>ล่วงหน้า 1-6 ชม.</td>
              <td>ดูแนวโน้มระยะสั้นภายในวันเดียวกัน</td>
            </tr>
            <tr>
              <td>
                <strong>Minute-ahead</strong>
                <br />
                <span className="model-info-note">(เส้นสีแดงด้านล่างกราฟหลัก)</span>
              </td>
              <td>CNN-LSTM</td>
              <td>ล่วงหน้า 10-60 นาที (และย้อนหลังได้ราว 30 นาที)</td>
              <td>พยากรณ์ระยะสั้นมากแบบเกือบเรียลไทม์ พร้อมเทียบกับกำลังไฟฟ้าที่ผลิตได้จริง</td>
            </tr>
          </tbody>
        </table>
        <p className="model-info-note">
          ทุกโมเดลใช้ข้อมูลอากาศจริง (NWP/ดาวเทียมเมฆ) เมื่อสะสมเพียงพอ - ถ้ายังไม่พอ ระบบจะสำรองด้วยแบบจำลองฟิสิกส์ (physics
          baseline) แทน ไม่ได้ทำนายมั่วๆ แต่ก็ยังไม่ใช่ ML ที่ train จากข้อมูลจริง (ดู caption ใต้กราฟเมื่อกำลังใช้โหมดสำรอง)
        </p>
      </details>

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
                <XAxis dataKey="timestamp" tickFormatter={formatDateHourIct} minTickGap={60} />
                <YAxis unit=" kW" width={80} />
                <Tooltip
                  labelFormatter={(label) => (typeof label === 'string' ? formatDateHourIct(label) : String(label))}
                  formatter={(value) => (typeof value === 'number' ? value.toFixed(1) : String(value))}
                />
                <Legend />
                <Line
                  dataKey="actualPast"
                  name="Actual power (before today)"
                  stroke="var(--chart-actual-past)"
                  strokeWidth={2}
                  dot={{ r: 2 }}
                  connectNulls
                />
                <Line
                  dataKey="actualToday"
                  name="Actual power (earlier today)"
                  stroke="var(--chart-actual-today)"
                  strokeWidth={2}
                  dot={{ r: 2 }}
                  connectNulls
                />
                <Line
                  dataKey="actualNow"
                  name="Actual power (now)"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  connectNulls
                />
                <Area dataKey="lower" name="lower" stackId="pi" stroke="none" fill="transparent" legendType="none" />
                <Area
                  dataKey="band"
                  name="Prediction interval"
                  stackId="pi"
                  stroke="none"
                  fill="var(--chart-pi)"
                  fillOpacity={0.25}
                />
                <Line
                  dataKey="pred"
                  name="Forecast"
                  stroke="var(--chart-forecast)"
                  strokeWidth={2}
                  dot={horizonToggle === 'hour' ? forecastDot : { r: 2 }}
                  connectNulls
                />
                {horizonToggle === 'hour' && (
                  <>
                    <Line
                      dataKey="errorLightgbm"
                      name="Error - LightGBM (RMSE)"
                      stroke="var(--chart-lgbm)"
                      strokeWidth={1.5}
                      strokeDasharray="4 4"
                      dot={false}
                      connectNulls
                    />
                    <Line
                      dataKey="errorRandomForest"
                      name="Error - Random Forest (RMSE)"
                      stroke="var(--chart-rf)"
                      strokeWidth={1.5}
                      strokeDasharray="4 4"
                      dot={false}
                      connectNulls
                    />
                    <Line
                      dataKey="errorSumKLstm"
                      name="Error - Sum-k LSTM (RMSE)"
                      stroke="var(--chart-sumk)"
                      strokeWidth={1.5}
                      strokeDasharray="4 4"
                      dot={false}
                      connectNulls
                    />
                  </>
                )}
              </ComposedChart>
            </ResponsiveContainer>
          )}
          {!isLoading && !forecastError && chartRows.some((r) => r.actualPast != null || r.actualToday != null || r.actualNow != null) && (
            <p className="forecast-status forecast-status-caption">
              🟣 กำลังไฟฟ้าที่ผลิตได้จริง (ล่าสุด/ปัจจุบัน) &nbsp; 🩷 วันนี้ (ช่วงที่ผ่านไปแล้ว) &nbsp; 🟦 ก่อนวันนี้ — แยกสีตามความใหม่ของข้อมูล
              เพื่อให้เทียบกับเส้น Forecast สีน้ำเงินได้ง่ายขึ้น
            </p>
          )}
          {!isLoading && !forecastError && isPhysicsBaseline && chartRows.some((r) => r.band != null) && (
            <p className="forecast-status forecast-status-caption">
              Prediction interval shown is an approximate ±20% band (no trained ML model yet, see day-ahead pipeline) - not a
              measured confidence interval.
            </p>
          )}
          {!isLoading && !forecastError && showsAlgorithmDots && (
            <p className="forecast-status forecast-status-caption">
              🟢 LightGBM &nbsp; 🟠 Random Forest &nbsp; 🔵 Sum-k LSTM — ระบบเลือกโมเดลที่แม่นยำกว่าโดยอัตโนมัติในแต่ละชั่วโมง (ดูสีจุดบนกราฟ)
              | เส้นประสีเดียวกันคือค่าความคลาดเคลื่อน (RMSE) ของโมเดลแต่ละตัว เทียบกับค่าจริงจากชุดข้อมูล validation — ไม่ใช่แค่โมเดลที่ชนะ
              เท่านั้น ดูรายละเอียดเพิ่มเติมได้ที่แถบ "การแข่งขันของโมเดล" ด้านล่าง
            </p>
          )}
        </section>
        <LiveClock />
      </div>

      <MinuteAheadPanel
        points={minutePoints}
        actualRows={minuteWindowActualRows}
        isLoading={minuteLoading}
        hasError={Boolean(minuteError)}
        isPhysicsBaseline={minuteIsPhysicsBaseline}
      />

      <ModelCompetitionPanel rows={competitionRows} isLoading={competitionLoading} hasError={Boolean(competitionError)} />

      <WeatherStrip
        points={weatherStrip.data?.points ?? []}
        dataSource={weatherStrip.data?.data_source}
        isLoading={weatherStrip.isLoading}
      />
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

// Plain-language onboarding guide for non-engineer viewers (the user's own
// framing: "คนบ้านๆ ธรรมดาทั่วไป" - regular people, not engineers), separate
// from the technical `.model-info-panel` table above (which stays as a quick
// engineer-facing reference). Starts collapsed (<details>, same open/close
// pattern as that table) since it's supplementary, not mandatory reading.
//
// MAINTENANCE INSTRUCTION FOR FUTURE CLAUDE SESSIONS: every model this page
// can show MUST have an entry in the "โมเดลที่ใช้ทั้งหมด" list below (full
// name, plain-language principle, why it was chosen). If a new forecast
// model is ever added to the pipeline - a replacement, a new competing
// candidate, a new horizon - add its entry here in the same pass, not as a
// follow-up. A viewer reading this guide should never see the app using a
// model this panel doesn't mention.
function ViewerGuidePanel() {
  return (
    <details className="viewer-guide-panel">
      <summary>📖 คำแนะนำการอ่านหน้านี้ (สำหรับผู้ใช้ทั่วไป) / How to read this page</summary>

      <section className="viewer-guide-section">
        <h4>หน้านี้มีไว้ทำอะไร</h4>
        <p>
          หน้า "Forecast" นี้แสดงการคาดการณ์ปริมาณไฟฟ้าที่ระบบโซลาร์ของโรงงานหนองฟาบจะผลิตได้ล่วงหน้า
          เทียบกับปริมาณไฟฟ้าที่ผลิตได้จริง ใช้ดูแนวโน้มเพื่อวางแผนการใช้ไฟ และตรวจสอบว่าระบบทำงานสมเหตุสมผลหรือไม่
        </p>
      </section>

      <section className="viewer-guide-section">
        <h4>วิธีอ่านกราฟ - แกนและเส้นต่าง ๆ</h4>
        <ul>
          <li>
            <strong>แกนนอน (X):</strong> เวลา แสดงเป็นเวลาไทย (ICT)
          </li>
          <li>
            <strong>แกนตั้ง (Y):</strong> กำลังไฟฟ้า หน่วยกิโลวัตต์ (kW) - ยิ่งสูงยิ่งผลิตไฟได้มาก
          </li>
          <li>
            <strong>เส้น "กำลังไฟฟ้าที่ผลิตได้จริง" (Actual power) 3 สี:</strong> ไฟฟ้าที่ผลิตได้จริงแล้วเท่านั้น (ไม่แสดงล่วงหน้า
            เพื่อไม่ให้สับสนกับเส้นพยากรณ์) แยกสีตามความใหม่ของข้อมูลเพื่อให้ดูง่ายขึ้นเมื่อเทียบกับเส้น Forecast สีน้ำเงิน (เดิมเป็นแท่งสีม่วง
            อันเดียว ผู้ใช้แจ้งว่าเทียบกับเส้นพยากรณ์ยาก - ปรับเป็นเส้น 3 สีแทน 2026-07-18):
            <ul>
              <li>🟣 <strong>สีม่วง (เดิม):</strong> ค่าล่าสุด/ปัจจุบัน - จุดที่ใหม่ที่สุดที่มีข้อมูลจริงแล้ว</li>
              <li>🩷 <strong>สีชมพู:</strong> วันนี้ แต่เป็นช่วงเวลาที่ผ่านไปแล้ว (ไม่ใช่ค่าล่าสุด)</li>
              <li>🟦 <strong>สีน้ำเงินเข้ม (indigo):</strong> ก่อนวันนี้ (วันก่อน ๆ ย้อนหลัง)</li>
            </ul>
          </li>
          <li>
            <strong>เส้นสีน้ำเงิน "Forecast":</strong> ค่าพยากรณ์กำลังการผลิตไฟฟ้า - ยังคงแสดงไว้แม้เวลานั้นจะผ่านไปแล้ว
            เพื่อให้เทียบกับเส้นกำลังไฟฟ้าที่ผลิตได้จริง (3 สีด้านบน) ที่เกิดขึ้นในชั่วโมงเดียวกันได้
          </li>
          <li>
            <strong>แถบสีเขียวโปร่งใส "Prediction interval":</strong> ช่วงความไม่แน่นอนของค่าพยากรณ์ - ค่าจริงมีโอกาสสูงที่จะอยู่ในช่วงนี้
            ยิ่งแถบกว้าง ยิ่งไม่แน่นอน (แสดงค้างไว้เหมือนเส้น Forecast เช่นกัน)
          </li>
          <li>
            <strong>เส้นประ 3 สี "Error - LightGBM / Random Forest / Sum-k LSTM" (เฉพาะ Intra-day):</strong>{' '}
            ค่าความคลาดเคลื่อน (RMSE) ของโมเดลทั้ง 3 ตัวในชั่วโมงล่วงหน้านั้น ๆ แยกสีตามโมเดล (เขียว = LightGBM, ส้ม = Random Forest, ฟ้า
            = Sum-k LSTM) ไม่ใช่แค่โมเดลที่ชนะเท่านั้น - ดูคำอธิบายเต็มในหัวข้อ "ค่าความคลาดเคลื่อน (RMSE) คืออะไร" ด้านล่าง
          </li>
          <li>
            <strong>เอาเมาส์ไปชี้บนเส้นหรือแท่งกราฟ:</strong> จะมีป้ายกำกับ (tooltip) เด้งขึ้นมาบอกตัวเลขที่จุดนั้นแบบละเอียด
          </li>
        </ul>
      </section>

      <section className="viewer-guide-section">
        <h4>Day-ahead กับ Intra-day ต่างกันอย่างไร</h4>
        <ul>
          <li>
            <strong>Day-ahead (พยากรณ์รายวัน):</strong> พยากรณ์ล่วงหน้าได้ไกลสุด 72 ชั่วโมง (3 วัน) เหมาะกับการวางแผนล่วงหน้าหลายวัน
            แต่แม่นยำน้อยกว่าเพราะมองไกล
          </li>
          <li>
            <strong>Intra-day (พยากรณ์ภายในวัน):</strong> พยากรณ์ล่วงหน้าแค่ 1-6 ชั่วโมง แม่นยำกว่าเพราะใกล้เวลาจริงมากกว่า
            เหมาะกับการตัดสินใจระยะสั้น
          </li>
        </ul>
      </section>

      <section className="viewer-guide-section">
        <h4>ค่าความคลาดเคลื่อน (RMSE) คืออะไร และทำไมถึงสำคัญ</h4>
        <ul>
          <li>
            <strong>RMSE คืออะไร:</strong> ย่อมาจาก Root Mean Squared Error - นำผลต่างระหว่างค่าที่โมเดลทำนายกับค่าจริงในแต่ละจุด
            มายกกำลังสอง แล้วเฉลี่ย แล้วถอดรากที่สอง ผลลัพธ์มีหน่วยเดียวกับกำลังไฟฟ้า (kW) จึงอ่านตรงตัวได้ว่า
            "โดยเฉลี่ยโมเดลนี้ทำนายคลาดเคลื่อนไปกี่ kW" ยิ่งตัวเลขต่ำ ยิ่งแม่นยำ
          </li>
          <li>
            <strong>ทำไมถึงสำคัญ:</strong> เป็นเกณฑ์ที่ระบบใช้ตัดสิน "ใครชนะ" ในการแข่งขันของ 3 โมเดลในแต่ละชั่วโมงล่วงหน้า (ดูแถบ
            "การแข่งขันของโมเดล" ด้านล่างกราฟ) - โมเดลที่มี RMSE ต่ำที่สุดในชั่วโมงนั้นจะถูกเลือกมาใช้ทำนายจริง เพราะการยกกำลังสองก่อนเฉลี่ยทำให้
            RMSE ลงโทษ "ความผิดพลาดครั้งใหญ่" (เช่น ตอนเมฆเปลี่ยนเร็วผิดปกติ) หนักกว่าความผิดพลาดเล็กน้อยที่กระจายทั่วไป
            ซึ่งตรงกับสิ่งที่เราต้องการหลีกเลี่ยงจริง ๆ ในการพยากรณ์พลังงาน
          </li>
          <li>
            <strong>ระบบนี้ใช้ RMSE แบบไหน:</strong> เป็น "held-out validation RMSE" คือวัดจากชุดข้อมูลที่โมเดลไม่เคยเห็นตอนฝึก (ไม่ใช่
            ข้อมูลที่ใช้ฝึกโมเดลเอง) เพื่อให้ตัวเลขสะท้อนความแม่นยำที่แท้จริงเมื่อเจอสถานการณ์ใหม่ ไม่ใช่แค่ "จำ" ข้อมูลเก่าได้แม่น -
            เป็นค่าที่วัดจริงจากการฝึกแต่ละครั้ง ไม่ใช่ค่าประมาณหรือสมมติขึ้น
          </li>
          <li>
            <strong>ทำไมเลือกใช้ RMSE ไม่ใช่ตัวชี้วัดอื่น:</strong> RMSE เป็นมาตรฐานที่งานวิจัยด้าน solar forecasting ใช้เปรียบเทียบโมเดล
            (เช่นงานอ้างอิงที่ระบบนี้ยึดหลักการมา ซึ่งเทียบ RF/SVR/MARS/ANN ด้วย RMSE เช่นกัน) และเหมาะกับบริบทนี้เพราะลงโทษความผิดพลาด
            ก้อนใหญ่มากกว่า MAE (Mean Absolute Error) - เหมาะกับการเลือกโมเดลที่ไม่พลาดหนักในบางชั่วโมงมากกว่าการดูค่าเฉลี่ยเฉย ๆ
          </li>
          <li>
            <strong>เส้น 3 สีในกราฟหลัก vs. แถบการแข่งขันด้านล่าง:</strong> เส้นประ 3 สีบนกราฟหลักโชว์ RMSE ของแต่ละโมเดลตามแกนเวลา
            (เทียบง่ายว่าคลาดเคลื่อนมากขึ้น/น้อยลงตามชั่วโมงล่วงหน้าอย่างไร) ส่วนแถบ "การแข่งขันของโมเดล" ด้านล่างกราฟโชว์ RMSE ของทั้ง 3
            โมเดลเทียบกันแบบแท่งกราฟในแต่ละชั่วโมงล่วงหน้า พร้อมไฮไลต์ว่าใครชนะ - ดูข้อมูลชุดเดียวกัน แค่คนละมุมมอง
          </li>
          <li>
            <strong>"ส่วนต่างระหว่างโมเดล" (spread) ในแถบการแข่งขัน:</strong> ผลต่างระหว่าง RMSE สูงสุดกับต่ำสุดของทั้ง 3 โมเดลในชั่วโมงนั้น
            (เอาเมาส์ชี้แท่งกราฟเพื่อดู) - เป็นการเปรียบเทียบ "ระหว่างโมเดลกันเอง" อีกแบบหนึ่ง นอกเหนือจาก RMSE เทียบค่าจริง: ค่ามาก แปลว่า
            โมเดลที่ชนะแม่นยำกว่าตัวอื่นชัดเจน ค่าน้อย แปลว่าทั้ง 3 โมเดลให้ผลใกล้เคียงกันมาก การเลือกผู้ชนะแทบไม่กระทบผลลัพธ์
            ข้อควรทราบ: นี่คำนวณจากผลการ validation ตอนฝึกโมเดล (ค่าคงที่จนกว่าจะฝึกใหม่) ไม่ใช่ความไม่ลงรอยกันของค่าพยากรณ์สดแบบเรียลไทม์ -
            แบบหลังจะต้องเก็บโมเดลที่แพ้การแข่งขันทั้งหมดไว้ทำนายคู่ขนานตลอดเวลา ซึ่งเป็นการเปลี่ยนแปลงระบบหลังบ้านที่ใหญ่กว่านี้
            จึงยังไม่ได้ทำในตอนนี้
          </li>
        </ul>
      </section>

      <section className="viewer-guide-section">
        <h4>โมเดลที่ใช้ทั้งหมด (ชื่อเต็ม, หลักการ, เหตุผลที่เลือกใช้)</h4>
        <ul>
          <li>
            <strong>NeuralProphet</strong> (ใช้กับ Day-ahead) - โมเดลพยากรณ์อนุกรมเวลาที่แยกวิเคราะห์แนวโน้มระยะยาวและรูปแบบตามรอบวัน/ฤดูกาลออกจากกัน
            แล้วรวมกันทำนาย เลือกใช้เพราะเหมาะกับการมองไกลหลายวันที่มีรูปแบบกลางวัน-กลางคืนชัดเจน และฝึกโมเดลได้เร็วแม้ข้อมูลยังสะสมไม่มาก
          </li>
          <li>
            <strong>LightGBM</strong> (Light Gradient Boosting Machine, ใช้กับ Intra-day - 1 ใน 3 ตัวที่แข่งกัน) -
            โมเดล Machine Learning แบบต้นไม้ตัดสินใจหลายต้นที่เรียนรู้ต่อเนื่องกันเพื่อแก้ข้อผิดพลาดของต้นก่อนหน้า (gradient boosting)
            แม่นยำสูงและฝึกเร็ว เลือกใช้เพราะเหมาะกับข้อมูลที่มีหลายปัจจัย (สภาพอากาศ เมฆ เวลา) แม้ข้อมูลจะยังไม่เยอะมาก
          </li>
          <li>
            <strong>Random Forest</strong> (ใช้กับ Intra-day - 1 ใน 3 ตัวที่แข่งกัน) - โมเดลที่รวมผลจากต้นไม้ตัดสินใจหลายต้นที่สร้างแบบสุ่ม
            แล้วเฉลี่ยผลลัพธ์ ทนทานต่อข้อมูลรบกวน (noise) ได้ดี เลือกใช้เป็นคู่แข่งของ LightGBM
            เพื่อให้ระบบเทียบผลแล้วเลือกตัวที่แม่นยำกว่าโดยอัตโนมัติในแต่ละชั่วโมง
          </li>
          <li>
            <strong>Sum-k LSTM</strong> (ใช้กับ Intra-day - 1 ใน 3 ตัวที่แข่งกัน) - โครงข่ายประสาทเทียมแบบ LSTM
            ที่มีส่วนเรียนรู้ร่วม (shared backbone) ประมวลผลข้อมูลย้อนหลังร่วมกัน แล้วแยกเป็นหัวคำนวณเฉพาะของแต่ละชั่วโมงล่วงหน้า (1-6 ชม.)
            พร้อมประเมินช่วงความไม่แน่นอนในตัวเอง ออกแบบตามแนวทางงานวิจัยด้าน probabilistic forecasting
            เลือกใช้เป็นคู่แข่งตัวที่ 3 เพื่อเพิ่มมุมมองแบบ deep learning ให้การแข่งขัน
          </li>
          <li>
            <strong>CNN-LSTM</strong> (ใช้กับ Minute-ahead) - ผสมโครงข่าย Convolutional ที่จับรูปแบบการเคลื่อนที่ของเมฆ
            เข้ากับ LSTM ที่จับรูปแบบการเปลี่ยนแปลงตามเวลา เลือกใช้กับการพยากรณ์ระยะสั้นมาก (10-60 นาที)
            เพราะตอบสนองต่อการเปลี่ยนแปลงของเมฆที่กำลังเคลื่อนที่ได้เร็ว เหมาะกับการพยากรณ์แบบเกือบเรียลไทม์
          </li>
        </ul>
        <p className="viewer-guide-note">
          หมายเหตุ: ถ้ายังไม่มีข้อมูลสะสมพอที่จะฝึกโมเดล ML จริง ระบบจะใช้แบบจำลองฟิสิกส์ (physics baseline) สำรองไปก่อน
          ไม่ได้ทำนายมั่วๆ แต่ก็ยังไม่ใช่ ML ที่เรียนรู้จากข้อมูลจริง (จะมีข้อความเตือนใต้กราฟเมื่อกำลังใช้โหมดสำรองนี้)
        </p>
      </section>
    </details>
  )
}

interface MinuteAheadPanelProps {
  points: ForecastPoint[]
  // Actual/generated power to overlay, hourly resolution (see
  // ForecastPage's own minuteWindowActualRows docstring for why this is
  // ChartRow[] - the same 3-tier rows the main chart uses - rather than a
  // dedicated minute-resolution source, which doesn't exist).
  actualRows: ChartRow[]
  isLoading: boolean
  hasError: boolean
  isPhysicsBaseline: boolean
}

// Minute-ahead (CNN-LSTM, 10-min steps out to 60 min) always shown - unlike
// Day-ahead/Intra-day, it isn't a toggle option on the main chart, since its
// timescale is too fine to share that chart's hourly-bucketed x-axis without
// squashing every other hour. A dedicated small red-line chart instead, per
// the user's 2026-07-16 request to see it directly on the dashboard rather
// than only mentioned in the model-info panel. Also shows ~30 min of its own
// backward history (client-side accumulated, see ForecastPage's own
// `minutePoints`) and an hourly-resolution actual-power overlay
// (`actualRows`), both added 2026-07-18 per the user's request.
function MinuteAheadPanel({ points, actualRows, isLoading, hasError, isPhysicsBaseline }: MinuteAheadPanelProps) {
  return (
    <section className="forecast-minute-panel" aria-label="Minute-ahead power forecast chart">
      <h3 className="forecast-minute-title">Minute-ahead forecast (CNN-LSTM, ~30 min back to 60 min ahead)</h3>
      {isLoading && <p className="forecast-status">Loading…</p>}
      {!isLoading && hasError && (
        <p className="forecast-status forecast-status-warn">No minute-ahead forecast model has been trained for this zone yet.</p>
      )}
      {!isLoading && !hasError && points.length === 0 && <p className="forecast-status">No data yet.</p>}
      {points.length > 0 && (
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis dataKey="timestamp" tickFormatter={formatHour} minTickGap={30} allowDuplicatedCategory={false} />
            <YAxis unit=" kW" width={80} />
            <Tooltip
              labelFormatter={(label) => (typeof label === 'string' ? formatHour(label) : String(label))}
              formatter={(value) => (typeof value === 'number' ? value.toFixed(1) : String(value))}
            />
            <Line dataKey="pred" name="Minute-ahead forecast" stroke="var(--chart-minute)" strokeWidth={2} dot={{ r: 2 }} connectNulls />
            <Line
              data={actualRows}
              dataKey="actualPast"
              name="Actual power (before today)"
              stroke="var(--chart-actual-past)"
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls
            />
            <Line
              data={actualRows}
              dataKey="actualToday"
              name="Actual power (earlier today)"
              stroke="var(--chart-actual-today)"
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls
            />
            <Line
              data={actualRows}
              dataKey="actualNow"
              name="Actual power (now)"
              stroke="var(--accent)"
              strokeWidth={2}
              dot={{ r: 4 }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      )}
      {!isLoading && !hasError && isPhysicsBaseline && points.length > 0 && (
        <p className="forecast-status forecast-status-caption">Physics-baseline fallback shown (no trained CNN-LSTM model yet).</p>
      )}
    </section>
  )
}

interface ModelCompetitionPanelProps {
  rows: CompetitionRow[]
  isLoading: boolean
  hasError: boolean
}

// A dedicated panel for "which model is winning" - separate from the main
// chart's per-model error *lines* (which show error over time), this shows
// one grouped-bar comparison of all three candidates' RMSE per lead hour
// (+1h..+6h) side by side, with the actual winner's bar highlighted (full
// opacity; the two losing candidates are dimmed) - added 2026-07-18 per the
// user's explicit request for "a new dashboard section for the competition,
// separate [from the main chart]" (แถบ dashboard เพิ่มเรื่องการแข่งขัน...แยกออกมาใหม่).
// Always shows the live hour-ahead race regardless of which Day-ahead/
// Intra-day tab is active on the main chart above - same pattern as
// MinuteAheadPanel.
function ModelCompetitionPanel({ rows, isLoading, hasError }: ModelCompetitionPanelProps) {
  return (
    <section className="forecast-competition-panel" aria-label="Model competition panel">
      <h3 className="forecast-competition-title">การแข่งขันของโมเดล (Model Competition) — Intra-day, +1h ถึง +6h</h3>
      <p className="forecast-competition-subtitle">
        เปรียบเทียบค่าความคลาดเคลื่อน (RMSE) ของทั้ง 3 โมเดลในแต่ละชั่วโมงล่วงหน้า — แท่งทึบคือโมเดลที่ชนะและถูกเลือกใช้จริงในชั่วโมงนั้น
        แท่งจางคือโมเดลที่แพ้การแข่งขัน (ยิ่ง RMSE ต่ำยิ่งแม่นยำ)
      </p>
      {isLoading && <p className="forecast-status">Loading…</p>}
      {!isLoading && hasError && (
        <p className="forecast-status forecast-status-warn">No intra-day forecast model has been trained for this zone yet.</p>
      )}
      {!isLoading && !hasError && rows.length === 0 && <p className="forecast-status">No data yet.</p>}
      {rows.length > 0 && (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={rows} margin={{ top: 20, right: 16, left: 0, bottom: 28 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            {/* Absolute reference time, not relative "+1h".."+6h" labels - the
                lead-hour offset is still shown (in the tooltip, via `row.leadLabel`)
                but the axis itself now reads the same way as every other chart on
                this page, per the user's own 2026-07-18 request. Angled so the
                longer "17 Jul 14:00"-style ticks don't overlap at this panel's
                width. */}
            <XAxis
              dataKey="timestamp"
              tickFormatter={(v) => formatDateHourIct(String(v))}
              angle={-30}
              textAnchor="end"
              height={50}
              tickMargin={8}
            />
            <YAxis unit=" kW" width={80} label={{ value: 'RMSE (kW)', angle: -90, position: 'insideLeft' }} />
            <Tooltip
              formatter={(value, name) => [typeof value === 'number' ? `${value.toFixed(2)} kW` : String(value), name]}
              labelFormatter={(label, payload) => {
                const row = payload?.[0]?.payload as CompetitionRow | undefined
                const winnerLabel = row?.winner ? (ALGORITHM_LABEL[row.winner] ?? row.winner) : 'ไม่ทราบ'
                const spreadLabel = row?.spread != null ? ` | ส่วนต่างระหว่างโมเดล: ${row.spread.toFixed(2)} kW` : ''
                const timeLabel = typeof label === 'string' ? formatDateHourIct(label) : String(label)
                const leadLabel = row?.leadLabel ? ` (${row.leadLabel})` : ''
                return `${timeLabel}${leadLabel} — ผู้ชนะ: ${winnerLabel}${spreadLabel}`
              }}
            />
            <Legend />
            <Bar dataKey="lightgbm" name="LightGBM" fill="var(--chart-lgbm)">
              {rows.map((row) => (
                <Cell key={`lgbm-${row.key}`} fillOpacity={row.winner === 'lightgbm' ? 1 : 0.3} />
              ))}
              <LabelList dataKey="lightgbm" position="top" fontSize={10} formatter={(v: unknown) => (typeof v === 'number' ? v.toFixed(1) : '')} />
            </Bar>
            <Bar dataKey="randomForest" name="Random Forest" fill="var(--chart-rf)">
              {rows.map((row) => (
                <Cell key={`rf-${row.key}`} fillOpacity={row.winner === 'random_forest' ? 1 : 0.3} />
              ))}
              <LabelList
                dataKey="randomForest"
                position="top"
                fontSize={10}
                formatter={(v: unknown) => (typeof v === 'number' ? v.toFixed(1) : '')}
              />
            </Bar>
            <Bar dataKey="sumKLstm" name="Sum-k LSTM" fill="var(--chart-sumk)">
              {rows.map((row) => (
                <Cell key={`sumk-${row.key}`} fillOpacity={row.winner === 'sum_k_lstm' ? 1 : 0.3} />
              ))}
              <LabelList dataKey="sumKLstm" position="top" fontSize={10} formatter={(v: unknown) => (typeof v === 'number' ? v.toFixed(1) : '')} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
      {rows.length > 0 && (
        <p className="forecast-status forecast-status-caption">
          เอาเมาส์ไปชี้แท่งกราฟเพื่อดู "ส่วนต่างระหว่างโมเดล" (spread) ของชั่วโมงนั้น — ยิ่งค่านี้น้อย ยิ่งแปลว่าทั้ง 3 โมเดลให้ผลใกล้เคียงกัน
          (การเลือกผู้ชนะแทบไม่ต่างผล) ยิ่งค่านี้มาก ยิ่งแปลว่าโมเดลที่ชนะแม่นยำกว่าตัวอื่นอย่างมีนัยสำคัญ — นี่คือค่าที่คำนวณจากผลการ
          validation ของแต่ละโมเดล ไม่ใช่ค่าความไม่ลงรอยกันของค่าพยากรณ์สดแบบเรียลไทม์ (ดูรายละเอียดในคำแนะนำการอ่านหน้านี้ด้านบน)
        </p>
      )}
    </section>
  )
}

// Shows both Thai local time and UTC side by side - every chart/display on
// this page uses Thai local time (ICT) as of 2026-07-17 (see
// web/README.md's dated entry), matching this widget's own primary
// display; UTC is kept as a small secondary reference (useful for matching
// server logs/API timestamps), not because anything on this page still
// shows UTC unlabeled - this whole app has a history of "why don't the
// numbers match what time it really is in Thailand" confusion (see
// web/README.md's 2026-07-16 dated entries) that this widget already heads
// off by naming both zones explicitly.
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
        <span className="forecast-clock-hint">(แกนเวลาในกราฟใช้เวลาไทยแล้ว - UTC แสดงไว้เทียบเฉย ๆ)</span>
      </div>
    </aside>
  )
}
