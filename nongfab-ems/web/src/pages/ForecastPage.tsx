import { useEffect, useMemo, useRef, useState } from 'react'
import type { RefObject } from 'react'
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
  indexNearestToTimestamp,
  mergeGeneratedAndForecast,
  mergeMinuteAheadRows,
  nearestToNow,
  sumForecastAcrossZones,
  sumGeneratedPowerHistoryAcrossZones,
  sumHourlyAcrossZones,
  truncateGeneratedToNow,
} from '../lib/chartData'
import type { ChartRow, CompetitionRow, MinuteChartRow } from '../lib/chartData'
import {
  ALL_ZONES_ID,
  useAllZonesForecast,
  useAllZonesPerformance,
  useCurrentConditions,
  useForecast,
  usePerformance,
  useWeatherStrip,
  useZones,
} from '../lib/queries'
import { useForecastHistory } from '../lib/forecastHistory'
import { formatDateHourIct, formatHourIct as formatHour } from '../lib/timeScrub'
import type {
  CurrentConditionsResponse,
  ForecastDataSource,
  ForecastHorizon,
  ForecastPoint,
  GeneratedPowerPoint,
  HourlyPoint,
  WeatherStripPoint,
} from '../lib/types'
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

const ACTUAL_POWER_SERIES_NAMES = new Set(['Actual power (before today)', 'Actual power (earlier today)', 'Actual power (now)'])

// Appends "(estimated)" to one of the 3 actual-power series' tooltip name
// when the hovered row's own reading was a cold-start-backfilled physics
// estimate, not a genuinely live-polled one (`ChartRow.actualEstimated` -
// see that field's own docstring). Added 2026-07-18 after the user found a
// backfilled "actual" and a physics-baseline-fallback "forecast" showing
// the literal same number for the same hour with no indication either was
// anything but an independent live measurement - see forecast/serving.py's
// GENERATED_POWER_ESTIMATED_MARKER for the full root-cause story.
function actualPowerTooltipName(name: string, row: ChartRow | undefined): string {
  if (row?.actualEstimated && ACTUAL_POWER_SERIES_NAMES.has(name)) return `${name} (estimated)`
  return name
}

// Below this width a chart never needs to scroll - matches roughly what the
// old fixed-percentage-width charts already rendered at on a typical
// desktop viewport, so a short series (few points) still looks the same as
// before this change, no scrollbar appears until there's genuinely more
// than fits.
const CHART_MIN_WIDTH_PX = 600

// Drives each of the 3 charts' own horizontal-scroll width (2026-07-18 per
// the user's own request - "เลื่อนได้พอประมาณเพื่อไปดูอดีตที่ผ่านมา และอนาคต
// นิดหน่อยตามความสามารถโมเดลนั้นๆ", scroll enough to see past history and a
// bit of future per that model's own real range): rather than building
// separate windowing/pagination logic, each chart's already-fetched data
// (chartRows already carries `useForecastHistory`'s accumulated past plus
// the model's own forward window - see that hook's own docstring) is
// rendered at a real pixel width proportional to point count, inside a
// `overflow-x: auto` wrapper, so panning is just native horizontal scroll
// over content that's honestly there rather than a fabricated "infinite"
// range. `pxPerPoint` is deliberately different per chart (minute-ahead's
// 10-min-resolution points need much less width per point than the main
// chart's hourly/daily ones to stay legible without excessive scrolling).
function scrollableChartWidthPx(pointCount: number, pxPerPoint: number): number {
  return Math.max(CHART_MIN_WIDTH_PX, pointCount * pxPerPoint)
}

// Auto-centers a scrollable chart's default scroll position on "today"/"now"
// instead of leaving it at the far-left (oldest) edge (2026-07-18, per the
// user's explicit follow-up: the earlier scroll-to-pan implementation above
// technically worked, but always opened scrolled all the way left, so "now"
// - the whole reason to scroll - started off-screen and the scrollbar itself
// wasn't obviously discoverable. Centers ONCE per `resetKey` (zone+horizon
// combo) rather than on every poll refresh, so it doesn't fight a viewer who
// has since panned to look at something else - only a genuine dataset swap
// (switching zone or horizon tab) re-centers.
function useCenterChartOnce(pointIndex: number, pxPerPoint: number, resetKey: string) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const centeredForRef = useRef<string | null>(null)

  useEffect(() => {
    if (centeredForRef.current === resetKey) return
    const el = containerRef.current
    if (!el || pointIndex < 0) return
    const targetCenterPx = pointIndex * pxPerPoint
    const maxScrollLeft = Math.max(0, el.scrollWidth - el.clientWidth)
    el.scrollLeft = Math.max(0, Math.min(targetCenterPx - el.clientWidth / 2, maxScrollLeft))
    centeredForRef.current = resetKey
  }, [pointIndex, pxPerPoint, resetKey])

  return containerRef
}

// Shown above every horizontally-scrollable chart so the (native, and
// otherwise easy to miss - e.g. auto-hiding trackpad scrollbars) pan
// affordance is obvious without relying on a viewer noticing a thin
// scrollbar on its own (2026-07-18, per the user's repeated "ยังไม่ทำแถบเลื่อน"
// feedback on a feature that was technically already there).
function ScrollHint() {
  return <p className="forecast-chart-scroll-hint">↔ ลาก/เลื่อนซ้าย-ขวาเพื่อดูข้อมูลย้อนหลังและล่วงหน้าได้ (เริ่มต้นที่ตำแหน่งปัจจุบัน)</p>
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
  // The 9 Songsiri-reference forecasting input variables (site-wide, not
  // per-zone - same "weather is site-wide" reasoning /weather/strip already
  // documents) - powers the 3x3 live variable table + grouped graphs below
  // (2026-07-18, see SolarVariablesTable/SolarVariablesGraphs).
  const currentConditions = useCurrentConditions()

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

  // One shared, time-sorted array for the whole panel - see
  // mergeMinuteAheadRows's own docstring for why handing Recharts `points`
  // and `actualRows` as two separately-shaped arrays (the panel's old
  // approach) produced an out-of-order x-axis tick.
  const minuteChartRows = useMemo(() => mergeMinuteAheadRows(minutePoints, minuteWindowActualRows), [minutePoints, minuteWindowActualRows])

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

  // "Now" position within each scrollable chart's own row array, and a
  // default-centered scroll container ref for each - see useCenterChartOnce's
  // own docstring above. Recomputed whenever the underlying rows change, but
  // only actually scrolls once per zone+horizon (or zone, for Minute-ahead)
  // combo, so it doesn't undo a viewer's manual pan on every poll.
  const mainChartNowIndex = useMemo(() => indexNearestToTimestamp(chartRows, new Date().toISOString()), [chartRows])
  const mainChartScrollRef = useCenterChartOnce(mainChartNowIndex, 28, `${zoneId}:${horizonToggle}`)
  const minuteChartNowIndex = useMemo(() => indexNearestToTimestamp(minuteChartRows, new Date().toISOString()), [minuteChartRows])
  const minuteChartScrollRef = useCenterChartOnce(minuteChartNowIndex, 20, `${zoneId}:minute`)

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
        <div className="model-info-table-scroll">
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
        </div>
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
            <>
              <ScrollHint />
              <div className="forecast-chart-scroll" ref={mainChartScrollRef}>
              <div style={{ width: scrollableChartWidthPx(chartRows.length, 28), height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartRows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="timestamp" tickFormatter={formatDateHourIct} minTickGap={60} />
                <YAxis unit=" kW" width={80} />
                <Tooltip
                  labelFormatter={(label) => (typeof label === 'string' ? formatDateHourIct(label) : String(label))}
                  formatter={(value, name, item) => [
                    typeof value === 'number' ? value.toFixed(1) : String(value),
                    actualPowerTooltipName(String(name), item?.payload as ChartRow | undefined),
                  ]}
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
                  strokeDasharray="7 4"
                  dot={horizonToggle === 'hour' ? forecastDot : { r: 2 }}
                  connectNulls
                />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
              </div>
            </>
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
              | ค่าความคลาดเคลื่อน (RMSE) ของโมเดลแต่ละตัวเทียบกับค่าจริงจากชุดข้อมูล validation แยกไปเป็นกราฟของตัวเองด้านล่าง
              (ไม่รวมในกราฟนี้แล้ว เพื่อไม่ให้รก) ดูรายละเอียดเพิ่มเติมได้ที่แถบ "การแข่งขันของโมเดล" ด้านล่างด้วย
            </p>
          )}
        </section>
        <LiveClock />
      </div>

      <MinuteAheadPanel
        rows={minuteChartRows}
        isLoading={minuteLoading}
        hasError={Boolean(minuteError)}
        isPhysicsBaseline={minuteIsPhysicsBaseline}
        scrollRef={minuteChartScrollRef}
      />

      {horizonToggle === 'hour' && <ErrorChartPanel rows={chartRows} />}

      <ModelCompetitionPanel rows={competitionRows} isLoading={competitionLoading} hasError={Boolean(competitionError)} />

      <WeatherStrip
        points={weatherStrip.data?.points ?? []}
        dataSource={weatherStrip.data?.data_source}
        isLoading={weatherStrip.isLoading}
      />

      <SolarVariablesTable conditions={currentConditions.data} isLoading={currentConditions.isLoading} />

      <SolarVariablesGraphs
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
  // One shared, time-sorted array carrying both the forecast line and the
  // actual-power overlay's 3 tiers per row - see mergeMinuteAheadRows's own
  // docstring for why this replaced two separately-shaped arrays (a real
  // Recharts x-axis-ordering bug, not just a style choice).
  rows: MinuteChartRow[]
  isLoading: boolean
  hasError: boolean
  isPhysicsBaseline: boolean
  // Default-centers this chart's scroll position on "now" once per zone -
  // see useCenterChartOnce's own docstring in ForecastPage.tsx. Owned by the
  // parent (not a local ref here) because the hook's centering-once state
  // needs to live as long as the page, not remount with this panel.
  scrollRef: RefObject<HTMLDivElement | null>
}

// Minute-ahead (CNN-LSTM, 10-min steps out to 60 min) always shown - unlike
// Day-ahead/Intra-day, it isn't a toggle option on the main chart, since its
// timescale is too fine to share that chart's hourly-bucketed x-axis without
// squashing every other hour. A dedicated small red-line chart instead, per
// the user's 2026-07-16 request to see it directly on the dashboard rather
// than only mentioned in the model-info panel. Also shows ~30 min of its own
// backward history (client-side accumulated, see ForecastPage's own
// `minutePoints`) and an hourly-resolution actual-power overlay, both added
// 2026-07-18 per the user's request.
function MinuteAheadPanel({ rows, isLoading, hasError, isPhysicsBaseline, scrollRef }: MinuteAheadPanelProps) {
  return (
    <section className="forecast-minute-panel" aria-label="Minute-ahead power forecast chart">
      <h3 className="forecast-minute-title">Minute-ahead forecast (CNN-LSTM, ~30 min back to 60 min ahead)</h3>
      {isLoading && <p className="forecast-status">Loading…</p>}
      {!isLoading && hasError && (
        <p className="forecast-status forecast-status-warn">No minute-ahead forecast model has been trained for this zone yet.</p>
      )}
      {!isLoading && !hasError && rows.length === 0 && <p className="forecast-status">No data yet.</p>}
      {rows.length > 0 && (
        <>
          <ScrollHint />
          <div className="forecast-chart-scroll" ref={scrollRef}>
            <div style={{ width: scrollableChartWidthPx(rows.length, 20), height: 140 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis dataKey="timestamp" tickFormatter={formatHour} minTickGap={30} allowDuplicatedCategory={false} />
                  <YAxis unit=" kW" width={80} />
                  <Tooltip
                    labelFormatter={(label) => (typeof label === 'string' ? formatHour(label) : String(label))}
                    formatter={(value) => (typeof value === 'number' ? value.toFixed(1) : String(value))}
                  />
                  <Line
                    dataKey="pred"
                    name="Minute-ahead forecast"
                    stroke="var(--chart-minute)"
                    strokeWidth={2}
                    strokeDasharray="7 4"
                    dot={{ r: 2 }}
                    connectNulls
                  />
                  <Line
                    dataKey="actualPast"
                    name="Actual power (before today)"
                    stroke="var(--chart-actual-past)"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    connectNulls
                  />
                  <Line
                    dataKey="actualToday"
                    name="Actual power (earlier today)"
                    stroke="var(--chart-actual-today)"
                    strokeWidth={2}
                    dot={{ r: 3 }}
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
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
      {!isLoading && !hasError && isPhysicsBaseline && rows.length > 0 && (
        <p className="forecast-status forecast-status-caption">Physics-baseline fallback shown (no trained CNN-LSTM model yet).</p>
      )}
    </section>
  )
}

// Intra-day's 3 per-model RMSE-over-time lines used to overlay directly on
// the main power chart (dashed, same colors as the algorithm-dot legend) -
// split into this dedicated chart per the user's own 2026-07-18 request
// ("ทำเป็นกราฟรูปใหม่ ไม่เช่นนั้นจะรกเกิด" - make it a new chart, otherwise it
// clutters), which also removed the 3 dashed lines from the main chart
// entirely rather than duplicating them in both places. Shares `chartRows`
// with the main chart (same errorLightgbm/errorRandomForest/errorSumKLstm
// fields already computed there) - no new data plumbing needed, purely a
// presentation split. Only rendered for the Intra-day (hour) horizon, same
// as the lines it replaces.
function ErrorChartPanel({ rows }: { rows: ChartRow[] }) {
  const hasData = rows.some((r) => r.errorLightgbm != null || r.errorRandomForest != null || r.errorSumKLstm != null)
  return (
    <section className="forecast-error-panel" aria-label="Model error over time chart">
      <h3 className="forecast-error-title">ความคลาดเคลื่อนของโมเดล (Error) ตามเวลา — RMSE</h3>
      <p className="forecast-error-subtitle">
        ค่าความคลาดเคลื่อน (RMSE) ของแต่ละโมเดลเทียบกับค่าจริงจากชุดข้อมูล validation ในแต่ละช่วงเวลา — ยิ่งค่าต่ำยิ่งแม่นยำ
      </p>
      {!hasData && <p className="forecast-status">No data yet.</p>}
      {hasData && (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={rows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis dataKey="timestamp" tickFormatter={formatDateHourIct} minTickGap={60} />
            <YAxis unit=" kW" width={80} />
            <Tooltip
              labelFormatter={(label) => (typeof label === 'string' ? formatDateHourIct(label) : String(label))}
              formatter={(value) => (typeof value === 'number' ? value.toFixed(2) : String(value))}
            />
            <Legend />
            {/* 3 distinct dash patterns (not just 3 colors) so any two lines
                that happen to cross or run close together stay tellable apart
                - color alone wasn't enough per the user's 2026-07-18 report
                ("เส้นกราฟ...มีการซ้อนกัน แม้แยกสีแล้วก็จริง"). */}
            <Line
              dataKey="errorLightgbm"
              name="Error - LightGBM (RMSE)"
              stroke="var(--chart-lgbm)"
              strokeWidth={1.5}
              strokeDasharray="6 3"
              dot={false}
              connectNulls
            />
            <Line
              dataKey="errorRandomForest"
              name="Error - Random Forest (RMSE)"
              stroke="var(--chart-rf)"
              strokeWidth={1.5}
              strokeDasharray="1 3"
              strokeLinecap="round"
              dot={false}
              connectNulls
            />
            <Line
              dataKey="errorSumKLstm"
              name="Error - Sum-k LSTM (RMSE)"
              stroke="var(--chart-sumk)"
              strokeWidth={1.5}
              strokeDasharray="8 3 1 3"
              dot={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
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
        <div className="forecast-chart-scroll">
          <div style={{ width: scrollableChartWidthPx(rows.length, 100), height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
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
          </div>
        </div>
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

const VARIABLE_UNAVAILABLE = '—'

function formatVar(value: number | null | undefined, digits: number): string {
  return value == null ? VARIABLE_UNAVAILABLE : value.toFixed(digits)
}

interface SolarVariablesTableProps {
  conditions: CurrentConditionsResponse | undefined
  isLoading: boolean
}

// Live-updating 3x3 table of all 9 Jitkomut Songsiri reference-deck input
// variables (I, RH, T / UV, WS, I_clr / cosθ, k̂, I_wrf - reading order
// matches that reference image), per the user's own 2026-07-18 request,
// after confirming ("ทำครบ 9 ตัว ระบุ UV เป็นรายวัน") that all 9 should be
// shown even though UV is only ever daily-resolution. Backed by GET
// /weather/conditions (see routes_weather.py's own docstring for the full
// per-variable audit of which were already real model features vs.
// ingested-but-never-surfaced) and refetched on the same poll interval
// every other live readout on this page already uses - no bespoke
// "real-time" plumbing needed beyond that.
function SolarVariablesTable({ conditions, isLoading }: SolarVariablesTableProps) {
  if (isLoading) return <p className="forecast-status">Loading…</p>
  if (!conditions || !conditions.available) {
    return <p className="forecast-status">No live weather data available yet.</p>
  }

  return (
    <section className="solar-variables-table-section" aria-label="9 solar forecasting input variables">
      <h3 className="forecast-minute-title">ตัวแปรพยากรณ์พลังงานแสงอาทิตย์ทั้ง 9 ตัว (Songsiri reference)</h3>
      <p className="forecast-error-subtitle">ค่าล่าสุดของตัวแปรทั้ง 9 ตัวที่งานวิจัยอ้างอิงของระบบนี้ใช้ - อัปเดตข้อมูลอัตโนมัติเป็นระยะ</p>
      <div className="solar-variables-grid">
        <VariableCell symbol="I" label="Irradiance" value={formatVar(conditions.irradiance_w_m2, 0)} unit="W/m²" />
        <VariableCell symbol="RH" label="Relative humidity" value={formatVar(conditions.relative_humidity_pct, 0)} unit="%" />
        <VariableCell symbol="T" label="Temperature" value={formatVar(conditions.temp_c, 1)} unit="°C" />
        <VariableCell
          symbol="UV"
          label="UV index"
          value={formatVar(conditions.uv_index, 1)}
          unit="ดัชนี"
          caption={conditions.uv_observation_date ? `ข้อมูลรายวัน (${conditions.uv_observation_date})` : 'ไม่มีข้อมูล UV'}
        />
        <VariableCell symbol="WS" label="Wind speed" value={formatVar(conditions.wind_speed_ms, 1)} unit="m/s" />
        <VariableCell symbol="I_clr" label="Clear-sky GHI" value={formatVar(conditions.clearsky_ghi_w_m2, 0)} unit="W/m²" />
        <VariableCell
          symbol="cosθ"
          label="Cosine of zenith angle"
          value={formatVar(conditions.cos_zenith, 2)}
          unit=""
          caption={conditions.zenith_deg != null ? `zenith ${conditions.zenith_deg.toFixed(0)}°` : undefined}
        />
        <VariableCell
          symbol="k̂"
          label="Clear-sky index"
          value={formatVar(conditions.clear_sky_index, 2)}
          unit=""
          caption={conditions.clear_sky_index == null ? 'กลางคืน/ไม่มีข้อมูล' : undefined}
        />
        <VariableCell
          symbol="I_wrf"
          label="NWP forecast irradiance"
          value={formatVar(conditions.forecast_irradiance_w_m2, 0)}
          unit="W/m²"
          caption={
            conditions.forecast_valid_at ? `พยากรณ์ ณ ${formatDateHourIct(conditions.forecast_valid_at)}` : 'ไม่มีข้อมูลพยากรณ์ขณะนี้'
          }
        />
      </div>
      <p className="forecast-status forecast-status-caption">
        I_wrf ใช้ข้อมูลจาก GFS (โมเดล NWP เดียวกับที่ใช้คำนวณ I) ที่เวลาล่วงหน้าใกล้ที่สุด ไม่ใช่โมเดลอิสระตัวที่สอง - ไม่มีเซนเซอร์วัดจริงหน้างานแยกต่างหาก
      </p>
    </section>
  )
}

interface VariableCellProps {
  symbol: string
  label: string
  value: string
  unit: string
  caption?: string
}

function VariableCell({ symbol, label, value, unit, caption }: VariableCellProps) {
  return (
    <div className="solar-variable-cell">
      <span className="solar-variable-symbol">{symbol}</span>
      <span className="solar-variable-value">
        {value}
        {unit && value !== VARIABLE_UNAVAILABLE && <span className="solar-variable-unit"> {unit}</span>}
      </span>
      <span className="solar-variable-label">{label}</span>
      {caption && <span className="solar-variable-caption">{caption}</span>}
    </div>
  )
}

interface IrradianceRow {
  timestamp: string
  iActual: number | null
  iForecast: number | null
  iSynthetic: number | null
  iClr: number
}

// `isReal` (the WHOLE weatherStrip response's own `data_source`, not a
// per-point flag - GET /weather/strip is either real-covered or synthetic-
// fallback for its entire window, never a mix) decides which of the 3
// irradiance lines a given point can honestly feed:
//  - real: past/now points -> `iActual` (a genuine ingested GFS reading),
//    future points -> `iForecast` (the same GFS source's own forward-
//    looking value, i.e. I_wrf - see routes_weather.py's own I_wrf caveat).
//  - synthetic: every point -> `iSynthetic` (the physics-only fallback
//    curve, which is neither a real "actual" reading nor a real NWP
//    forecast) - kept in its own field specifically so it never gets
//    mislabeled as either, per the user's own explicit "don't fake a
//    forecast that doesn't exist" instruction.
// `iClr` (clear-sky GHI) is always populated either way - pure astronomy,
// no real/synthetic distinction applies to it.
function buildIrradianceRows(points: WeatherStripPoint[], isReal: boolean, nowMs: number): IrradianceRow[] {
  return points.map((p) => {
    const isFuture = new Date(p.timestamp).getTime() > nowMs
    return {
      timestamp: p.timestamp,
      iActual: isReal && !isFuture ? p.ssrd_w_m2 : null,
      iForecast: isReal && isFuture ? p.ssrd_w_m2 : null,
      iSynthetic: !isReal ? p.ssrd_w_m2 : null,
      iClr: p.clearsky_ghi_w_m2,
    }
  })
}

interface SolarVariablesGraphsProps {
  points: WeatherStripPoint[]
  dataSource: ForecastDataSource | undefined
  isLoading: boolean
}

const VARIABLE_CHART_TOOLTIP_FORMATTER = (value: unknown) => (typeof value === 'number' ? value.toFixed(2) : String(value))
const VARIABLE_CHART_LABEL_FORMATTER = (label: unknown) => (typeof label === 'string' ? formatDateHourIct(label) : String(label))

// Grouped time-series graphs for the same 9 Songsiri-reference variables the
// table above shows as a single live snapshot - per the user's own
// 2026-07-18 request/confirmed grouping ("เห็นด้วยตามที่เสนอ"): the
// irradiance trio (I/I_clr/I_wrf) share one chart, k̂+cosθ share one chart
// (both unitless, comparable 0-1-ish scale), and T/RH/WS each get their own
// chart. UV gets NO chart at all - it has no time series anywhere in this
// system (NASA POWER is daily-cadence only, not part of /weather/strip),
// and the user was explicit that a variable with no real forecast (or, in
// UV's case, no real time series at all) should never have one faked just
// to fill a chart slot - see the UV caption below instead.
//
// Data source: GET /weather/strip, the SAME already-time-series endpoint
// the WeatherStrip component above already renders (not a second,
// duplicate fetch) - reuses its existing real/synthetic honesty labeling
// (see buildIrradianceRows's own docstring for how that plays out for the
// irradiance chart specifically) rather than building a parallel windowed
// endpoint.
function SolarVariablesGraphs({ points, dataSource, isLoading }: SolarVariablesGraphsProps) {
  const isReal = dataSource === 'real'
  const irradianceRows = useMemo(() => buildIrradianceRows(points, isReal, Date.now()), [points, isReal])
  const hasRh = points.some((p) => p.relative_humidity_pct != null)
  const hasWind = points.some((p) => p.wind_speed_ms != null)

  return (
    <section className="solar-variables-graphs-section" aria-label="9 solar forecasting variable graphs">
      <div className="weather-strip-header">
        <span className="forecast-minute-title">กราฟตัวแปรพยากรณ์พลังงานแสงอาทิตย์</span>
        {!isLoading && dataSource && (
          <span
            className={
              dataSource === 'real' ? 'data-source-badge data-source-badge-real' : 'data-source-badge data-source-badge-synthetic'
            }
          >
            {dataSource === 'real' ? 'Real data' : 'Demo data'}
          </span>
        )}
      </div>
      {isLoading && <p className="forecast-status">Loading…</p>}
      {!isLoading && points.length === 0 && <p className="forecast-status">No data yet.</p>}
      {!isLoading && points.length > 0 && (
        <>
          <div className="solar-variable-chart">
            <h4 className="solar-variable-chart-title">I / I_clr / I_wrf - ความเข้มรังสีอาทิตย์</h4>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={irradianceRows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="timestamp" tickFormatter={formatDateHourIct} minTickGap={60} />
                <YAxis unit=" W/m²" width={70} />
                <Tooltip labelFormatter={VARIABLE_CHART_LABEL_FORMATTER} formatter={VARIABLE_CHART_TOOLTIP_FORMATTER} />
                <Legend />
                <Line dataKey="iClr" name="I_clr (clear-sky GHI)" stroke="var(--chart-clearsky)" strokeWidth={2} dot={false} connectNulls />
                <Line dataKey="iActual" name="I (irradiance, actual)" stroke="var(--chart-irradiance)" strokeWidth={2} dot={false} connectNulls />
                <Line
                  dataKey="iForecast"
                  name="I_wrf (NWP forecast)"
                  stroke="var(--chart-forecast)"
                  strokeWidth={2}
                  strokeDasharray="7 4"
                  dot={false}
                  connectNulls
                />
                <Line
                  dataKey="iSynthetic"
                  name="I (แบบจำลองฟิสิกส์สำรอง)"
                  stroke="var(--chart-irradiance)"
                  strokeWidth={2}
                  strokeDasharray="1 3"
                  dot={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
            {!isReal && (
              <p className="forecast-status forecast-status-caption">
                ยังไม่มีข้อมูลจริงครอบคลุมช่วงเวลานี้เพียงพอ - เส้น I ที่แสดงเป็นแบบจำลองฟิสิกส์สำรองเท่านั้น ไม่ใช่ค่าจริงหรือค่าพยากรณ์ I_wrf จริง
                (ไม่ฝืนแสดงค่าพยากรณ์ที่ไม่มีอยู่จริง)
              </p>
            )}
          </div>

          <div className="solar-variable-chart">
            <h4 className="solar-variable-chart-title">T - อุณหภูมิ</h4>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="timestamp" tickFormatter={formatDateHourIct} minTickGap={60} />
                <YAxis unit=" °C" width={60} />
                <Tooltip labelFormatter={VARIABLE_CHART_LABEL_FORMATTER} formatter={VARIABLE_CHART_TOOLTIP_FORMATTER} />
                <Line dataKey="temp_c" name="T (temperature)" stroke="var(--chart-temp)" strokeWidth={2} dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="solar-variable-chart">
            <h4 className="solar-variable-chart-title">k̂ / cosθ - ดัชนีท้องฟ้าใส และ cosine ของมุมเซนิท</h4>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="timestamp" tickFormatter={formatDateHourIct} minTickGap={60} />
                <YAxis width={50} />
                <Tooltip labelFormatter={VARIABLE_CHART_LABEL_FORMATTER} formatter={VARIABLE_CHART_TOOLTIP_FORMATTER} />
                <Legend />
                <Line dataKey="cos_zenith" name="cosθ" stroke="var(--chart-cosz)" strokeWidth={2} dot={false} />
                <Line
                  dataKey="clear_sky_index"
                  name="k̂ (clear-sky index)"
                  stroke="var(--chart-khat)"
                  strokeWidth={2}
                  strokeDasharray="4 2"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
            <p className="forecast-status forecast-status-caption">k̂ ไม่มีค่าตอนกลางคืน (clear-sky GHI ใกล้ 0 ทำให้อัตราส่วนไม่มีความหมาย)</p>
          </div>

          <div className="solar-variable-chart">
            <h4 className="solar-variable-chart-title">RH - ความชื้นสัมพัทธ์</h4>
            {hasRh ? (
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis dataKey="timestamp" tickFormatter={formatDateHourIct} minTickGap={60} />
                  <YAxis unit=" %" width={50} />
                  <Tooltip labelFormatter={VARIABLE_CHART_LABEL_FORMATTER} formatter={VARIABLE_CHART_TOOLTIP_FORMATTER} />
                  <Line dataKey="relative_humidity_pct" name="RH (relative humidity)" stroke="var(--chart-rh)" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="forecast-status forecast-status-caption">
                ไม่มีข้อมูลความชื้นสัมพัทธ์ในช่วงเวลานี้ (ระบบยังไม่มีข้อมูลจริงเพียงพอ ใช้แบบจำลองฟิสิกส์สำรองซึ่งไม่ได้จำลองความชื้นไว้) - ไม่แสดงกราฟเพื่อไม่ให้ดูเหมือนมีข้อมูลจริง
              </p>
            )}
          </div>

          <div className="solar-variable-chart">
            <h4 className="solar-variable-chart-title">WS - ความเร็วลม</h4>
            {hasWind ? (
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis dataKey="timestamp" tickFormatter={formatDateHourIct} minTickGap={60} />
                  <YAxis unit=" m/s" width={60} />
                  <Tooltip labelFormatter={VARIABLE_CHART_LABEL_FORMATTER} formatter={VARIABLE_CHART_TOOLTIP_FORMATTER} />
                  <Line dataKey="wind_speed_ms" name="WS (wind speed)" stroke="var(--chart-wind)" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="forecast-status forecast-status-caption">
                ไม่มีข้อมูลความเร็วลมในช่วงเวลานี้ (ระบบยังไม่มีข้อมูลจริงเพียงพอ ใช้แบบจำลองฟิสิกส์สำรองซึ่งไม่ได้จำลองลมไว้) - ไม่แสดงกราฟเพื่อไม่ให้ดูเหมือนมีข้อมูลจริง
              </p>
            )}
          </div>

          <div className="solar-variable-chart">
            <h4 className="solar-variable-chart-title">UV - ดัชนีรังสียูวี</h4>
            <p className="forecast-status forecast-status-caption">
              UV เป็นข้อมูลรายวันเท่านั้น (อัปเดตวันละครั้งจาก NASA POWER ดู forecast/README.md) ไม่มีข้อมูลรายชั่วโมงหรือค่าพยากรณ์ล่วงหน้าจริงให้แสดงเป็นกราฟตามช่วงเวลาได้
              - ดูค่าล่าสุดได้ในตารางด้านบน (ไม่ฝืนสุ่ม/ประมาณค่าเพื่อทำเป็นกราฟ)
            </p>
          </div>
        </>
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
