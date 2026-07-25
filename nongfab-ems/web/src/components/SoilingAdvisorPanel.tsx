// Soiling & Cleaning Advisor (2026-07-25) - the operational read the static
// soiling derate could never give: how dirty this array is right now, how fast
// it's getting dirtier, when rain last washed it, what the dirt is costing, and
// roughly when a wash is worth scheduling.
//
// Everything shown comes from GET /soiling/{zone}, which runs this site's own
// measured PM10/dust + salt-spray index + rainfall through a Kimber/Coello-style
// accumulate-and-wash model (see features/soiling_dynamics.py). Two honesty
// rules the UI keeps:
//   1. `available: false` renders the server's own reason, never a zero.
//   2. The badge says whether the system-wide loss model is now using this
//      MEASURED figure or is still on its literature default.
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useSoiling } from '../lib/queries'

export interface SoilingAdvisorPanelProps {
  zone: string
}

const MEASURED_SOURCE = 'measured-airquality-rainfall'

function formatThb(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)} ล้านบาท`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)} พันบาท`
  return `${value.toFixed(0)} บาท`
}

/** The headline recommendation, in plain Thai. Ordered by urgency so the reader
 * gets the action first and the reasoning after. */
function recommendation(currentPct: number, triggerPct: number, daysUntil: number | null, daysSinceRain: number | null): string {
  if (currentPct >= triggerPct) {
    return `ควรล้างแผงเร็วๆ นี้ — คราบสกปรกถึงระดับ ${triggerPct.toFixed(1)}% แล้ว`
  }
  if (daysUntil != null && daysUntil <= 7) {
    return `เตรียมแผนล้างแผงในอีกประมาณ ${daysUntil} วัน (ถ้าไม่มีฝนมาช่วยล้างก่อน)`
  }
  if (daysSinceRain != null && daysSinceRain <= 2) {
    return 'ฝนเพิ่งล้างแผงให้ ยังไม่ต้องล้าง'
  }
  if (daysUntil != null) {
    return `ยังไม่ต้องล้าง — ประมาณอีก ${daysUntil} วันจึงจะถึงระดับที่ควรล้าง (ถ้าฝนไม่ตก)`
  }
  return 'ยังไม่ต้องล้าง'
}

export function SoilingAdvisorPanel({ zone }: SoilingAdvisorPanelProps) {
  const soiling = useSoiling(zone)
  const data = soiling.data

  if (soiling.isLoading) {
    return (
      <section className="ems-panel" aria-label="Soiling advisor">
        <h3 className="ems-panel-title">🧽 คราบสกปรกและการล้างแผง (Soiling Advisor)</h3>
        <p className="forecast-status">กำลังประเมินคราบสกปรก…</p>
      </section>
    )
  }

  if (!data || !data.available) {
    return (
      <section className="ems-panel" aria-label="Soiling advisor">
        <h3 className="ems-panel-title">🧽 คราบสกปรกและการล้างแผง (Soiling Advisor)</h3>
        <p className="forecast-status forecast-status-caption">
          {data?.reason ?? 'ยังประเมินคราบสกปรกไม่ได้ — ต้องมีข้อมูลคุณภาพอากาศและฝนย้อนหลังก่อน'}
        </p>
        <p className="forecast-status forecast-status-caption">
          ระหว่างนี้ตัวเลข soiling ในตาราง Losses ยังใช้ค่าอ้างอิงจากงานวิจัย (literature default)
        </p>
      </section>
    )
  }

  const chartData = data.series_days.map((day, i) => ({ day, loss: data.series_loss_pct[i] }))
  const measured = data.loss_model_soiling_source === MEASURED_SOURCE

  return (
    <section className="ems-panel" aria-label="Soiling advisor">
      <h3 className="ems-panel-title">🧽 คราบสกปรกและการล้างแผง (Soiling Advisor)</h3>

      <p className={`soiling-recommendation ${data.current_loss_pct >= data.cleaning_trigger_pct ? 'soiling-recommendation-urgent' : ''}`}>
        {recommendation(data.current_loss_pct, data.cleaning_trigger_pct, data.days_until_trigger, data.days_since_cleaning_rain)}
      </p>

      <div className="ems-kpi-grid">
        <div className="ems-kpi">
          <span className="ems-kpi-label">คราบสกปรกตอนนี้</span>
          <span className="ems-kpi-value">{data.current_loss_pct.toFixed(2)}%</span>
          <span className="ems-kpi-hint">สูญเสียกำลังผลิตจากฝุ่น/เกลือเกาะแผง</span>
        </div>
        <div className="ems-kpi">
          <span className="ems-kpi-label">อัตราสะสมต่อวัน</span>
          <span className="ems-kpi-value">{data.current_daily_rate_pct.toFixed(3)}%/วัน</span>
          <span className="ems-kpi-hint">จาก PM10/ฝุ่น/ละอองเกลือวันนี้</span>
        </div>
        <div className="ems-kpi">
          <span className="ems-kpi-label">ฝนล้างแผงครั้งล่าสุด</span>
          <span className="ems-kpi-value">
            {data.days_since_cleaning_rain == null ? '—' : data.days_since_cleaning_rain === 0 ? 'วันนี้' : `${data.days_since_cleaning_rain} วันก่อน`}
          </span>
          <span className="ems-kpi-hint">
            {data.days_since_cleaning_rain == null
              ? `ไม่พบฝนที่ล้างแผงในช่วง ${data.days_assessed} วันที่ประเมิน`
              : `ในช่วง ${data.days_assessed} วัน มีฝนล้างแผง ${data.cleaning_events} ครั้ง`}
          </span>
        </div>
        <div className="ems-kpi">
          <span className="ems-kpi-label">ค่าเสียโอกาสถ้าปล่อยไว้</span>
          <span className="ems-kpi-value">
            {data.annual_cost_lost_thb == null ? '—' : formatThb(data.annual_cost_lost_thb)}
          </span>
          <span className="ems-kpi-hint">
            {data.annual_energy_lost_kwh == null
              ? 'ยังคำนวณไม่ได้'
              : `${data.annual_energy_lost_kwh.toFixed(0)} kWh/ปี ที่ระดับความสกปรกปัจจุบัน`}
          </span>
        </div>
      </div>

      <div className="soiling-chart" style={{ width: '100%', height: 200 }}>
        <ResponsiveContainer>
          <AreaChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="day" tick={{ fontSize: 11 }} minTickGap={28} />
            <YAxis unit="%" tick={{ fontSize: 11 }} width={46} />
            <Tooltip formatter={(value) => [typeof value === 'number' ? `${value.toFixed(2)}%` : String(value), 'คราบสกปรก']} />
            <ReferenceLine
              y={data.cleaning_trigger_pct}
              stroke="var(--chart-salt)"
              strokeDasharray="5 4"
              label={{ value: `ระดับที่ควรล้าง ${data.cleaning_trigger_pct}%`, position: 'insideTopLeft', fontSize: 11 }}
            />
            <Area type="monotone" dataKey="loss" stroke="var(--chart-dust)" fill="var(--chart-dust)" fillOpacity={0.25} strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <p className="ems-caption">
        เส้นกราฟคือคราบสกปรกที่สะสมขึ้นทุกวันแล้วถูก<b>ฝนจริง</b>ล้างลง ({data.days_assessed} วันย้อนหลัง) — ยิ่งฟันเลื่อยถี่
        แปลว่าฝนช่วยล้างบ่อย
      </p>
      <p className="ems-caption">
        {measured ? (
          <>
            ✅ ตัวเลข soiling ในตาราง Losses / Financial <b>ใช้ค่าที่คำนวณจากข้อมูลจริงของไซต์นี้แล้ว</b> (เฉลี่ย{' '}
            {(data.loss_model_soiling_pct ?? data.average_loss_pct).toFixed(2)}% ต่อปี) แทนค่าคงที่จากงานวิจัย
          </>
        ) : (
          <>ตาราง Losses ยังใช้ค่าอ้างอิงจากงานวิจัยอยู่ — จะเปลี่ยนเป็นค่าจากข้อมูลจริงเมื่อระบบเก็บข้อมูลครบรอบถัดไป</>
        )}
      </p>
      <p className="ems-caption">
        วิธีคำนวณ: แบบจำลอง Kimber (2007) + Coello &amp; Boyle (2019) ที่ให้อัตราสะสมแปรผันตาม PM10 จริง บวกพจน์ละอองเกลือ
        ทะเลของไซต์ และล้างออกด้วยปริมาณฝนจริง — <b>ค่าสัมประสิทธิ์มาจากงานวิจัย</b> (ยังไม่มีการวัดคราบสกปรกจริงที่หนองแฟบ)
        ส่วนข้อมูลที่ป้อนเข้าเป็นค่าที่วัดได้จริงทั้งหมด
      </p>
    </section>
  )
}
