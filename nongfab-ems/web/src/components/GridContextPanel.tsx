import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useGridToday } from '../lib/queries'
import type { GridPoint } from '../lib/types'

/** Nong Fab against the whole Thai power system, from EGAT's public SysGen feed
 * (2026-07-25). Every other panel on this site describes 429 kWp on its own;
 * this one puts it next to the ~26,000 MW the country is actually running on,
 * and makes visible the thing that decides whether PV can help at the moment of
 * greatest need: Thailand's system peak happens in the EVENING, after sunset.
 *
 * All timestamps arrive as ICT from EGAT (see api/egat_grid.py) - so unlike the
 * UTC-sourced panels elsewhere, these are rendered as-is with no conversion.
 * Formatting therefore reads the clock fields off the ISO string rather than
 * going through the browser's local timezone, which would be wrong for any
 * viewer outside Thailand.
 */

/** `2026-07-25T20:50:00+07:00` -> `20:50`, without letting the viewer's own
 * timezone rewrite a time that is already Thai. */
function ictClock(iso: string | null): string {
  if (!iso) return '—'
  const match = /T(\d{2}):(\d{2})/.exec(iso)
  return match ? `${match[1]}:${match[2]}` : '—'
}

function ictDate(iso: string | null): string {
  if (!iso) return ''
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!match) return ''
  const [, y, m, d] = match
  const months = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
  return `${Number(d)} ${months[Number(m) - 1]} ${Number(y) + 543}`
}

const nf0 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 1 })

interface ChartRow {
  minutes: number
  clock: string
  actual: number | null
  plan: number | null
}

/** Actual and plan onto one minute-of-day axis. Exported for tests: the two
 * series arrive as separate lists at different resolutions (EGAT plans the
 * whole day but has only published actuals up to now), and lining them up
 * without inventing actual values for the future is the whole job. */
export function buildChartRows(actual: GridPoint[], plan: GridPoint[]): ChartRow[] {
  const byMinute = new Map<number, ChartRow>()
  const minuteOf = (iso: string): number | null => {
    const match = /T(\d{2}):(\d{2})/.exec(iso)
    return match ? Number(match[1]) * 60 + Number(match[2]) : null
  }
  const put = (points: GridPoint[], key: 'actual' | 'plan') => {
    for (const point of points) {
      const minutes = minuteOf(point.at)
      if (minutes === null) continue
      const row = byMinute.get(minutes) ?? {
        minutes,
        clock: `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`,
        actual: null,
        plan: null,
      }
      row[key] = point.mw
      byMinute.set(minutes, row)
    }
  }
  put(plan, 'plan')
  put(actual, 'actual')
  return Array.from(byMinute.values()).sort((a, b) => a.minutes - b.minutes)
}

function minuteOfDay(iso: string | null): number | null {
  if (!iso) return null
  const match = /T(\d{2}):(\d{2})/.exec(iso)
  return match ? Number(match[1]) * 60 + Number(match[2]) : null
}

export function GridContextPanel() {
  const grid = useGridToday()

  if (grid.isLoading) {
    return (
      <section className="verify-panel" aria-label="National grid context">
        <h3>🇹🇭 ระบบไฟฟ้าทั้งประเทศ (กฟผ.)</h3>
        <p className="forecast-status">กำลังดึงข้อมูลระบบไฟฟ้าของประเทศ…</p>
      </section>
    )
  }

  if (grid.error || !grid.data || !grid.data.available) {
    return (
      <section className="verify-panel" aria-label="National grid context">
        <h3>🇹🇭 ระบบไฟฟ้าทั้งประเทศ (กฟผ.)</h3>
        <p className="forecast-status forecast-status-warn">
          {grid.data?.reason ?? 'ยังดึงข้อมูลระบบไฟฟ้าของประเทศจาก กฟผ. ไม่ได้ในขณะนี้'}
        </p>
      </section>
    )
  }

  const d = grid.data
  const rows = buildChartRows(d.actual, d.plan)
  const sunStart = minuteOfDay(d.solar_window_start)
  const sunEnd = minuteOfDay(d.solar_window_end)
  const annualPeak = d.peaks.find((p) => p.label === 'สูงสุดปีนี้')

  return (
    <section className="verify-panel" aria-label="National grid context">
      <h3>🇹🇭 ระบบไฟฟ้าทั้งประเทศ (กฟผ.) เทียบกับหนองแฟบ</h3>

      <div className="grid-context-stats">
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">กำลังผลิตของระบบตอนนี้</span>
          <strong>{nf0.format(d.latest_mw ?? 0)} MW</strong>
          <span className="grid-context-stat-sub">
            {ictClock(d.latest_at)} น.
            {d.latest_ambient_c != null && ` · ${nf1.format(d.latest_ambient_c)}°C`}
          </span>
        </div>
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">ต่างจากแผนที่ กฟผ. วางไว้</span>
          <strong className={(d.plan_deviation_mw ?? 0) >= 0 ? 'grid-context-over' : 'grid-context-under'}>
            {d.plan_deviation_mw == null ? '—' : `${d.plan_deviation_mw >= 0 ? '+' : ''}${nf0.format(d.plan_deviation_mw)} MW`}
          </strong>
          <span className="grid-context-stat-sub">
            {(d.plan_deviation_mw ?? 0) >= 0 ? 'ใช้ไฟมากกว่าแผน' : 'ใช้ไฟน้อยกว่าแผน'}
          </span>
        </div>
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">สัดส่วนของหนองแฟบ</span>
          <strong>{d.site_share_of_system_pct == null ? '—' : `${d.site_share_of_system_pct.toFixed(4)}%`}</strong>
          <span className="grid-context-stat-sub">{nf1.format(d.site_dc_capacity_kwp ?? 0)} kWp ต่อทั้งระบบ</span>
        </div>
      </div>

      {d.annual_peak_after_sunset && annualPeak && (
        <p className="grid-context-finding">
          ⚠️ <strong>ความต้องการไฟสูงสุดของประเทศเกิดตอนกลางคืน</strong> — ปีนี้ทำสถิติ{' '}
          <strong>{nf0.format(annualPeak.mw)} MW</strong> เมื่อ {ictDate(annualPeak.at)} เวลา{' '}
          <strong>{ictClock(annualPeak.at)} น.</strong> ขณะที่แสงแดดที่หนองแฟบวันนี้หมดตั้งแต่{' '}
          <strong>{ictClock(d.solar_window_end)} น.</strong> แปลว่าโซลาร์ที่ไม่มีแบตเตอรี่{' '}
          <strong>ช่วยลด peak ของระบบไม่ได้</strong> — ประโยชน์ของมันคือลดค่าไฟช่วงกลางวันของไซต์เอง ไม่ใช่การเสริมความมั่นคงของระบบตอนหัวค่ำ
        </p>
      )}

      <div className="grid-context-chart">
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            {sunStart != null && sunEnd != null && (
              <ReferenceArea x1={sunStart} x2={sunEnd} fill="#fde68a" fillOpacity={0.35} ifOverflow="extendDomain" />
            )}
            <XAxis
              dataKey="minutes"
              type="number"
              domain={[0, 1440]}
              ticks={[0, 240, 480, 720, 960, 1200, 1440]}
              tickFormatter={(m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:00`}
              tick={{ fontSize: 11 }}
            />
            <YAxis
              tick={{ fontSize: 11 }}
              width={54}
              tickFormatter={(v: number) => nf0.format(v / 1000)}
              label={{ value: 'GW', angle: -90, position: 'insideLeft', fontSize: 11 }}
            />
            <Tooltip
              // recharts types these callbacks with widened value/label types, so
              // annotating them as number does not compile - narrow at runtime.
              formatter={(value, name) => [
                typeof value === 'number' ? `${nf0.format(value)} MW` : String(value),
                name,
              ]}
              labelFormatter={(label) =>
                typeof label === 'number'
                  ? `${String(Math.floor(label / 60)).padStart(2, '0')}:${String(label % 60).padStart(2, '0')} น.`
                  : String(label)
              }
            />
            <Area type="monotone" dataKey="actual" name="ผลิตจริง" stroke="#2563eb" fill="#bfdbfe" fillOpacity={0.5} connectNulls={false} dot={false} />
            <Line type="monotone" dataKey="plan" name="แผนของ กฟผ." stroke="#9333ea" strokeDasharray="5 4" dot={false} strokeWidth={1.5} />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="grid-context-legend">
          <span className="grid-context-swatch grid-context-swatch-sun" /> ช่วงที่หนองแฟบมีแดด ({ictClock(d.solar_window_start)}–
          {ictClock(d.solar_window_end)} น.) · <span className="grid-context-swatch grid-context-swatch-actual" /> ผลิตจริง ·{' '}
          <span className="grid-context-swatch grid-context-swatch-plan" /> แผนของ กฟผ.
        </p>
      </div>

      {/* Own scroll container: the peak rows are nowrap, and on a phone they
          must scroll inside the panel rather than widening the whole page. */}
      <div className="grid-context-peaks-scroll">
        <table className="grid-context-peaks">
        <thead>
          <tr>
            <th>สถิติความต้องการไฟสูงสุด</th>
            <th>กำลังผลิต</th>
            <th>วันเวลา</th>
            <th>อุณหภูมิ</th>
          </tr>
        </thead>
        <tbody>
          {d.peaks.map((p) => (
            <tr key={p.label}>
              <td>{p.label}</td>
              <td>
                <strong>{nf0.format(p.mw)} MW</strong>
              </td>
              <td>
                {ictDate(p.at)} {ictClock(p.at)} น.
              </td>
              <td>{p.ambient_c == null ? '—' : `${nf1.format(p.ambient_c)}°C`}</td>
            </tr>
          ))}
        </tbody>
        </table>
      </div>

      <p className="grid-context-note">{d.source_note}</p>
      <p className="grid-context-note">{d.comparison_note}</p>
    </section>
  )
}
