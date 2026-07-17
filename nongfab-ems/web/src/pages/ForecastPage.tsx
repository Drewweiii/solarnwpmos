import { useEffect, useMemo, useState } from 'react'
import type { DotItemDotProps } from 'recharts'
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ZoneSelector } from '../components/ZoneSelector'
import {
  exactTimeKey,
  mergeGeneratedAndForecast,
  nearestToNow,
  pickHoursOfDay,
  sumForecastAcrossZones,
  sumHourlyAcrossZones,
  truncateGeneratedToNow,
  WEATHER_ICON_GLYPH,
  weatherIconFor,
} from '../lib/chartData'
import { ALL_ZONES_ID, useAllZonesForecast, useAllZonesPerformance, useForecast, usePerformance, useZones } from '../lib/queries'
import { formatDateHourIct, formatHourIct as formatHour } from '../lib/timeScrub'
import type { ForecastHorizon, ForecastPoint, HourlyPoint } from '../lib/types'
import './ForecastPage.css'

type HorizonToggle = 'day' | 'hour'

// UTC hours matched via pickHoursOfDay's getUTCHours() - chosen so they land
// on Thai local (ICT = UTC+7) 07:00/10:00/13:00/16:00, squarely inside the
// real daylight window simulation/dev_data.py's synthetic generator produces
// (UTC 0-10 = ICT 07:00-17:00, peaking at UTC 5 = ICT noon). The previous
// [6, 9, 12, 15] was itself UTC, so two of its four slots (12, 15 UTC =
// 19:00/22:00 ICT) were Thai *nighttime* - correctly showing 0 W/m² and a
// moon icon, but mislabeled with a bare "12:00"/"15:00" that read as
// afternoon, causing "why is it 25°C at noon" confusion (found live
// 2026-07-17). [23, 2, 5, 8] would map to a rounder 06:00/09:00/12:00/15:00
// ICT, but hour 23 wraps to the *previous* UTC calendar day - hourly's own
// 24-point array only covers today's UTC hours, so that lookup would
// silently grab tomorrow morning instead; [0, 3, 6, 9] avoids that
// day-boundary trap entirely while keeping the same "four checkpoints
// spanning the Thai work day" intent.
const WEATHER_HOURS = [0, 3, 6, 9]

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

  // Minute-ahead (CNN-LSTM) is a fixed near-real-time horizon, not part of
  // the Day-ahead/Intra-day toggle above - shown in its own always-visible
  // panel (see MinuteAheadPanel below) rather than merged onto the main
  // chart's hourly-bucketed x-axis, since 10-min-resolution points would
  // distort that axis's spacing.
  const singleMinuteForecast = useForecast(zoneId, 'minute')
  const allMinuteForecast = useAllZonesForecast('minute')

  const isAllZones = zoneId === ALL_ZONES_ID

  const hourly: HourlyPoint[] = useMemo(() => {
    if (isAllZones) return sumHourlyAcrossZones(allPerformance.map((q) => q.data?.hourly ?? []))
    return singlePerformance.data?.hourly ?? []
  }, [isAllZones, allPerformance, singlePerformance.data])

  const forecastPoints: ForecastPoint[] = useMemo(() => {
    if (isAllZones) return sumForecastAcrossZones(allForecast.map((q) => q.data?.points ?? []))
    return singleForecast.data?.points ?? []
  }, [isAllZones, allForecast, singleForecast.data])

  const chartRows = useMemo(
    () => truncateGeneratedToNow(mergeGeneratedAndForecast(hourly, forecastPoints)),
    [hourly, forecastPoints],
  )
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

  const minutePoints: ForecastPoint[] = useMemo(() => {
    // exactTimeKey, not the default hourKey - minute-ahead's 10-minute-
    // resolution points routinely share an hour, which hourKey would wrongly
    // collapse (see chartData.ts's own docstring on this bug, found live 2026-07-17).
    if (isAllZones) return sumForecastAcrossZones(allMinuteForecast.map((q) => q.data?.points ?? []), exactTimeKey)
    return singleMinuteForecast.data?.points ?? []
  }, [isAllZones, allMinuteForecast, singleMinuteForecast.data])

  const minuteLoading = isAllZones
    ? allMinuteForecast.some((q) => q.isLoading)
    : singleMinuteForecast.isLoading
  const minuteError = isAllZones ? allMinuteForecast.find((q) => q.error) : singleMinuteForecast.error ? singleMinuteForecast : undefined
  const minuteIsPhysicsBaseline = isAllZones
    ? allMinuteForecast.some((q) => q.data?.model_type === 'physics_baseline')
    : singleMinuteForecast.data?.model_type === 'physics_baseline'

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
              <td>ล่วงหน้า 10-60 นาที</td>
              <td>พยากรณ์ระยะสั้นมากแบบเกือบเรียลไทม์</td>
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
                <Bar dataKey="generated" name="Generated power" fill="var(--accent)" fillOpacity={0.55} barSize={18} />
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
                  <Line
                    dataKey="error"
                    name="Model error (RMSE)"
                    stroke="var(--chart-error)"
                    strokeWidth={1.5}
                    strokeDasharray="4 4"
                    dot={false}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
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
              | เส้นประ "Model error (RMSE)" คือค่าความคลาดเคลื่อนของโมเดลที่ชนะ วัดจากชุดข้อมูล validation จริง ไม่ใช่ค่าประมาณ
            </p>
          )}
        </section>
        <LiveClock />
      </div>

      <MinuteAheadPanel
        points={minutePoints}
        isLoading={minuteLoading}
        hasError={Boolean(minuteError)}
        isPhysicsBaseline={minuteIsPhysicsBaseline}
      />

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
            <strong>แท่งสีม่วง "Generated power":</strong> ไฟฟ้าที่ผลิตได้จริงแล้วเท่านั้น - แสดงเฉพาะช่วงเวลาที่ผ่านไปแล้ว
            ไม่แสดงล่วงหน้า เพื่อไม่ให้สับสนกับเส้นพยากรณ์
          </li>
          <li>
            <strong>เส้นสีน้ำเงิน "Forecast":</strong> ค่าพยากรณ์กำลังการผลิตไฟฟ้า
          </li>
          <li>
            <strong>แถบสีเขียวโปร่งใส "Prediction interval":</strong> ช่วงความไม่แน่นอนของค่าพยากรณ์ - ค่าจริงมีโอกาสสูงที่จะอยู่ในช่วงนี้
            ยิ่งแถบกว้าง ยิ่งไม่แน่นอน
          </li>
          <li>
            <strong>เส้นประสีเทา "Model error (RMSE)" (เฉพาะ Intra-day):</strong> ความคลาดเคลื่อนของโมเดลที่ชนะการแข่งขันในชั่วโมงนั้น
            วัดจากข้อมูลจริง ไม่ใช่ค่าประมาณ
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
  isLoading: boolean
  hasError: boolean
  isPhysicsBaseline: boolean
}

// Minute-ahead (CNN-LSTM, 10-min steps out to 60 min) always shown - unlike
// Day-ahead/Intra-day, it isn't a toggle option on the main chart, since its
// timescale is too fine to share that chart's hourly-bucketed x-axis without
// squashing every other hour. A dedicated small red-line chart instead, per
// the user's 2026-07-16 request to see it directly on the dashboard rather
// than only mentioned in the model-info panel.
function MinuteAheadPanel({ points, isLoading, hasError, isPhysicsBaseline }: MinuteAheadPanelProps) {
  return (
    <section className="forecast-minute-panel" aria-label="Minute-ahead power forecast chart">
      <h3 className="forecast-minute-title">Minute-ahead forecast (CNN-LSTM, next 60 min)</h3>
      {isLoading && <p className="forecast-status">Loading…</p>}
      {!isLoading && hasError && (
        <p className="forecast-status forecast-status-warn">No minute-ahead forecast model has been trained for this zone yet.</p>
      )}
      {!isLoading && !hasError && points.length === 0 && <p className="forecast-status">No data yet.</p>}
      {points.length > 0 && (
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis dataKey="timestamp" tickFormatter={formatHour} minTickGap={30} />
            <YAxis unit=" kW" width={80} />
            <Tooltip
              labelFormatter={(label) => (typeof label === 'string' ? formatHour(label) : String(label))}
              formatter={(value) => (typeof value === 'number' ? value.toFixed(1) : String(value))}
            />
            <Line dataKey="pred" name="Minute-ahead forecast" stroke="var(--chart-minute)" strokeWidth={2} dot={{ r: 2 }} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      )}
      {!isLoading && !hasError && isPhysicsBaseline && points.length > 0 && (
        <p className="forecast-status forecast-status-caption">Physics-baseline fallback shown (no trained CNN-LSTM model yet).</p>
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
