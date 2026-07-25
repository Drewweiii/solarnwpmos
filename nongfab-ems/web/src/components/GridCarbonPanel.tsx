import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useGridCarbon } from '../lib/queries'
import type { GridCarbonHour } from '../lib/types'

/** What the Thai grid's carbon intensity does across the day, and which factor
 * this array actually earns (2026-07-25).
 *
 * The Energy Report prices every avoided kWh at one flat annual factor. This
 * panel asks the sharper question: solar here only produces in the middle of
 * the day, so does it displace the clean part of the grid or the dirty part?
 *
 * The honesty of this panel is the point, so the labels are not decoration:
 * the load curve is measured (EGAT), the per-fuel factors are IPCC AR5, the
 * fuel split is EPPO's real 2566 national figures but an ANNUAL average rather
 * than the month being shown, and the whole curve is calibrated so its average
 * is exactly the published GEF. See api/grid_carbon.py for the full breakdown.
 */

const nf0 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 0 })
const nf3 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 3 })
const nf1 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 1 })

interface CarbonRow extends GridCarbonHour {
  clock: string
}

/** Hours to chart rows. Exported for tests: the only real work is labelling the
 * hour and keeping hours the site does not produce in, so the "solar produces
 * here" bars stay visibly confined to daylight instead of being dropped. */
export function buildCarbonRows(hours: GridCarbonHour[]): CarbonRow[] {
  return hours.map((hour) => ({ ...hour, clock: `${String(hour.hour).padStart(2, '0')}:00` }))
}

export function GridCarbonPanel() {
  const { data, isLoading, isError } = useGridCarbon()

  if (isLoading) {
    return (
      <section className="forecast-panel">
        <h3>คาร์บอนของกริดรายชั่วโมง</h3>
        <p className="grid-context-stat-sub">กำลังคำนวณลำดับการเดินเครื่องจากเส้นโหลดของ กฟผ. …</p>
      </section>
    )
  }

  if (isError || !data || !data.available) {
    return (
      <section className="forecast-panel">
        <h3>คาร์บอนของกริดรายชั่วโมง</h3>
        <p className="grid-context-stat-sub">{data?.reason ?? 'ยังดึงข้อมูลระบบไฟฟ้าของประเทศไม่ได้ในขณะนี้'}</p>
      </section>
    )
  }

  const rows = buildCarbonRows(data.hours)
  const published = data.published_ef_kg_per_kwh
  const earned = data.solar_weighted_marginal_kg_per_kwh
  const uplift = data.marginal_uplift_pct
  // The fuel our solar actually displaces most, i.e. the marginal fuel in the
  // hour this array generates the most - NOT the middle row. EGAT publishes the
  // day so far, so the middle of the array is wherever "now" happens to be
  // (mid-morning at 13:00), which is not midday and not when we produce most.
  const peakSolarHour = rows.reduce<CarbonRow | null>(
    (best, row) => (best === null || row.site_generation_kwh > best.site_generation_kwh ? row : best),
    null,
  )
  const dominant = peakSolarHour && peakSolarHour.site_generation_kwh > 0 ? peakSolarHour.marginal_fuel_label : null
  const isAnnualAverage = data.mix_origin === 'annual'
  // The marginal line is near-flat under Thailand's mix (gas is marginal almost
  // all day), so any visible step comes from a different fuel taking the very
  // top of the peak. That step is real but over-attributed - an ANNUAL oil share
  // applied to a SINGLE day implies oil runs a sliver every day, when it really
  // runs on a handful of peak days a year. Name it rather than leaving a
  // conspicuous spike unexplained.
  const otherFuels = [...new Set(rows.map((r) => r.marginal_fuel_label))].filter((label) => label !== dominant)

  return (
    <section className="forecast-panel">
      <h3>คาร์บอนของกริดรายชั่วโมง — โซลาร์ของเราไปแทนที่เชื้อเพลิงอะไร</h3>

      <div className="grid-context-stats">
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">ค่าที่ใช้รายงานอยู่ (คงที่ทั้งปี)</span>
          <strong>{published === null ? '—' : nf3.format(published)}</strong>
          <span className="grid-context-stat-sub">kgCO₂/kWh · GEF ของ กกพ.</span>
        </div>
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">ค่าที่โซลาร์ของเรา "ได้จริง" ตามเวลาที่ผลิต</span>
          <strong>{earned === null ? '—' : nf3.format(earned)}</strong>
          <span className="grid-context-stat-sub">kgCO₂/kWh · ค่า marginal ถ่วงน้ำหนักด้วยรูปการผลิต</span>
        </div>
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">ต่างจากค่าคงที่</span>
          <strong className={uplift !== null && uplift >= 0 ? 'grid-context-over' : 'grid-context-under'}>
            {uplift === null ? '—' : `${uplift >= 0 ? '+' : ''}${nf1.format(uplift)}%`}
          </strong>
          <span className="grid-context-stat-sub">
            {uplift !== null && uplift >= 0 ? 'ค่าคงที่ประเมินไซต์นี้ "ต่ำกว่า" ความจริง' : 'ค่าคงที่ประเมินไซต์นี้สูงกว่าความจริง'}
          </span>
        </div>
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">เชื้อเพลิงชายขอบช่วงกลางวัน</span>
          <strong style={{ fontSize: '1.05rem' }}>{dominant ?? '—'}</strong>
          <span className="grid-context-stat-sub">โรงที่จะลดกำลังลงถ้าเราผลิตเพิ่ม 1 kWh</span>
        </div>
      </div>

      <div style={{ width: '100%', height: 300 }}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="clock" tick={{ fontSize: 11 }} interval={2} />
            <YAxis
              yAxisId="ef"
              tick={{ fontSize: 11 }}
              width={58}
              domain={['auto', 'auto']}
              label={{ value: 'kgCO₂/kWh', angle: -90, position: 'insideLeft', fontSize: 11 }}
            />
            <YAxis yAxisId="kwh" orientation="right" tick={{ fontSize: 11 }} width={54} />
            <Tooltip
              // recharts widens these callback parameters, so narrowing has to
              // happen in the body rather than in an annotation (see the
              // 2026-07-25 CI note in web/README.md).
              formatter={(value, name) => [
                typeof value === 'number' ? (name === 'โซลาร์ของเราผลิต' ? `${nf0.format(value)} kWh` : nf3.format(value)) : String(value),
                name,
              ]}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar
              yAxisId="kwh"
              dataKey="site_generation_kwh"
              name="โซลาร์ของเราผลิต"
              fill="#fde68a"
              stroke="#f59e0b"
              barSize={14}
            />
            <Line
              yAxisId="ef"
              type="monotone"
              dataKey="marginal_kg_per_kwh"
              name="คาร์บอนของโรงชายขอบ (marginal)"
              stroke="#dc2626"
              strokeWidth={2}
              dot={false}
            />
            <Line
              yAxisId="ef"
              type="monotone"
              dataKey="average_kg_per_kwh"
              name="คาร์บอนเฉลี่ยของระบบ (average)"
              stroke="#2563eb"
              strokeDasharray="5 4"
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <p className="grid-context-stat-sub" style={{ marginTop: 8 }}>
        <strong>สัดส่วนเชื้อเพลิงที่ใช้จำลอง:</strong>{' '}
        {data.mix.map((share) => `${share.label} ${nf1.format(share.share_pct)}%`).join(' · ')}
      </p>

      {isAnnualAverage && (
        <p className="grid-context-stat-sub" style={{ color: '#b45309' }}>
          ℹ️ {data.mix_note}
        </p>
      )}

      {dominant !== null && otherFuels.length > 0 && (
        <p className="grid-context-stat-sub" style={{ color: '#b45309' }}>
          ℹ️ เส้น marginal มีจุดกระโดดช่วงพีค เพราะแบบจำลองให้ {otherFuels.join(' / ')} ขึ้นมาเป็นโรงชายขอบที่ยอดสุด ·
          เป็นผลจากการเอาสัดส่วนเชื้อเพลิง <strong>รายปี</strong> มาใช้กับ <strong>วันเดียว</strong> ของจริงโรงพีคเดินไม่กี่วันต่อปี
          จุดนี้จึงเกินจริงไปบ้าง (กระทบค่าเฉลี่ยน้อยมาก) — ถ้ากรอกสัดส่วนรายเดือนจะแม่นขึ้น
        </p>
      )}

      <details>
        <summary style={{ cursor: 'pointer', fontSize: '0.85rem' }}>อ่านก่อนนำตัวเลขไปใช้ — อะไรวัดจริง อะไรเป็นแบบจำลอง</summary>
        <p className="grid-context-stat-sub">{data.method_note}</p>
        <p className="grid-context-stat-sub">{data.calibration_note}</p>
        <p className="grid-context-stat-sub">{data.marginal_note}</p>
        <p className="grid-context-stat-sub">{data.profile_note}</p>
      </details>
    </section>
  )
}
