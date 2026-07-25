// Forecast Verification & Skill Score (2026-07-25). Answers a question the
// dashboard could not answer before: not "how well did the model fit its
// training data" (which is what the RMSE lines and Model Competition panel show
// - those are TRAINING hold-out errors) but "how good have the forecasts this
// system actually issued turned out to be, once the hour arrived".
//
// The headline is the SKILL SCORE against persistence ("output in k hours will
// equal output now"), the reference solar-forecasting work is expected to beat:
// > 0 means the model genuinely adds information, 0 means it's no better than
// assuming nothing changes, < 0 means it's worse than doing nothing.
//
// Scope limit stated on screen: this site has no metered output (see
// forecast/README - the inverter portal is permanently closed), so the "actual"
// side is the physics model evaluated on the weather that actually verified. That
// makes this a measure of NWP forecast error propagated through physics, which is
// meaningful, but it is NOT accuracy against a meter.
//
// Honesty rules the panel keeps: `available: false` shows the server's reason;
// null metrics render as "—" and say why; the daylight-only figures are the
// headline with the all-hours figures shown beside them, since night hours are
// trivially correct and would otherwise flatter every number.
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useForecastVerification } from '../lib/queries'
import type { VerificationMetrics } from '../lib/types'

export interface ForecastVerificationPanelProps {
  zone: string
  days?: number
}

function skillVerdict(skill: number | null): { label: string; className: string } {
  if (skill == null) return { label: 'ยังคำนวณไม่ได้', className: '' }
  if (skill > 0.1) return { label: 'ดีกว่าการเดาแบบ "คงที่" อย่างชัดเจน', className: 'verify-skill-good' }
  if (skill > 0) return { label: 'ดีกว่าการเดาแบบ "คงที่" เล็กน้อย', className: 'verify-skill-ok' }
  if (skill === 0) return { label: 'เท่ากับการเดาแบบ "คงที่"', className: 'verify-skill-ok' }
  return { label: 'แย่กว่าการเดาแบบ "คงที่" — ต้องปรับโมเดล', className: 'verify-skill-bad' }
}

function MetricsRow({ label, metrics }: { label: string; metrics: VerificationMetrics }) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td>{metrics.n}</td>
      <td>{metrics.mae_kw.toFixed(2)}</td>
      <td>{metrics.rmse_kw.toFixed(2)}</td>
      <td>{metrics.nrmse_pct == null ? '—' : `${metrics.nrmse_pct.toFixed(2)}%`}</td>
      <td>
        {metrics.mbe_kw >= 0 ? '+' : ''}
        {metrics.mbe_kw.toFixed(2)}
      </td>
      <td>{metrics.skill_score == null ? '—' : metrics.skill_score.toFixed(3)}</td>
    </tr>
  )
}

export function ForecastVerificationPanel({ zone, days = 30 }: ForecastVerificationPanelProps) {
  const verification = useForecastVerification(zone, days)
  const data = verification.data

  if (verification.isLoading) {
    return (
      <section className="verify-panel" aria-label="Forecast verification">
        <h3 className="forecast-minute-title">🎯 ความแม่นยำจริงของ Forecast (Verification &amp; Skill Score)</h3>
        <p className="forecast-status">กำลังตรวจสอบความแม่นยำ…</p>
      </section>
    )
  }

  if (!data || !data.available || !data.daylight || !data.all_hours) {
    return (
      <section className="verify-panel" aria-label="Forecast verification">
        <h3 className="forecast-minute-title">🎯 ความแม่นยำจริงของ Forecast (Verification &amp; Skill Score)</h3>
        <p className="forecast-status forecast-status-caption">
          {data?.reason ?? 'ยังตรวจสอบความแม่นยำไม่ได้ — ต้องมีทั้งประวัติ forecast และค่ากำลังผลิตจริงในช่วงเดียวกัน'}
        </p>
      </section>
    )
  }

  const verdict = skillVerdict(data.daylight.skill_score)
  const leadChart = data.by_lead
    .filter((row) => row.metrics.n > 0)
    .map((row) => ({ lead: row.lead_bucket, rmse: Number(row.metrics.rmse_kw.toFixed(2)), n: row.metrics.n }))

  return (
    <section className="verify-panel" aria-label="Forecast verification">
      <h3 className="forecast-minute-title">🎯 ความแม่นยำจริงของ Forecast (Verification &amp; Skill Score)</h3>

      <div className={`verify-headline ${verdict.className}`}>
        <span className="verify-headline-value">
          {data.daylight.skill_score == null ? '—' : data.daylight.skill_score.toFixed(3)}
        </span>
        <span className="verify-headline-label">
          Skill score เทียบ persistence · {verdict.label}
        </span>
      </div>

      <div className="verify-table-scroll">
        <table className="verify-table">
          <caption>
            เทียบ forecast ที่ระบบออกจริงกับกำลังผลิตจริง ย้อนหลัง {data.window_days} วัน ({data.daylight.n} ชั่วโมงที่มีแดด)
          </caption>
          <thead>
            <tr>
              <th scope="col">ช่วงเวลา</th>
              <th scope="col">n (ชม.)</th>
              <th scope="col">MAE (kW)</th>
              <th scope="col">RMSE (kW)</th>
              <th scope="col">nRMSE (%กำลังติดตั้ง)</th>
              <th scope="col">อคติ MBE (kW)</th>
              <th scope="col">Skill</th>
            </tr>
          </thead>
          <tbody>
            <MetricsRow label="เฉพาะช่วงมีแดด" metrics={data.daylight} />
            <MetricsRow label="ทุกชั่วโมง (รวมกลางคืน)" metrics={data.all_hours} />
          </tbody>
        </table>
      </div>

      {leadChart.length > 0 && (
        <div className="verify-chart" style={{ width: '100%', height: 190 }}>
          <ResponsiveContainer>
            <BarChart data={leadChart} margin={{ top: 16, right: 12, left: 0, bottom: 4 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="lead" tick={{ fontSize: 12 }} />
              <YAxis unit=" kW" tick={{ fontSize: 11 }} width={58} />
              <Tooltip
                formatter={(value, name) => [typeof value === 'number' ? `${value.toFixed(2)} kW` : String(value), name]}
                labelFormatter={(label) => `lead ${label}`}
              />
              <Bar dataKey="rmse" name="RMSE" fill="var(--chart-aod)" radius={[4, 4, 0, 0]}>
                <LabelList dataKey="rmse" position="top" fontSize={11} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <p className="forecast-status forecast-status-caption">
        <b>อ่านอย่างไร:</b> MAE/RMSE ยิ่งต่ำยิ่งดี · MBE เป็นบวก = โมเดลทำนาย<b>สูงเกินจริง</b> เป็นลบ = ทำนายต่ำเกินจริง ·
        Skill score &gt; 0 = เก่งกว่าการเดาว่า "อีก k ชั่วโมงจะเท่ากับตอนนี้" ซึ่งเป็น baseline มาตรฐานของงานพยากรณ์แสงอาทิตย์
      </p>
      <p className="forecast-status forecast-status-caption">
        ตัวเลขชุดนี้<b>ไม่ใช่</b>ค่า error จากการเทรน (RMSE ในกราฟ Model Competition คือ hold-out ตอน fit โมเดล) — ชุดนี้คือการ
        ตรวจย้อนหลังว่า forecast ที่ออกไปแล้วตรงกับ<b>ค่าที่ประเมินได้ ณ เวลานั้นจริงๆ</b> แค่ไหน
      </p>
      <p className="forecast-status forecast-status-caption">
        <b>ข้อจำกัดที่ต้องรู้:</b> ไซต์นี้<b>ไม่มีมิเตอร์วัดกำลังผลิตจริง</b> (ดู forecast/README) ฝั่ง &ldquo;ค่าจริง&rdquo; ที่ใช้เทียบจึงเป็น
        ค่าที่คำนวณจากโมเดลฟิสิกส์ + สภาพอากาศที่<b>เกิดขึ้นจริง</b> ณ ชั่วโมงนั้น ดังนั้นตัวเลขนี้วัด &ldquo;error ของพยากรณ์อากาศที่ส่งผ่าน
        ฟิสิกส์&rdquo; ไม่ใช่ความคลาดเคลื่อนเทียบมิเตอร์
      </p>
      <p className="forecast-status forecast-status-caption">{data.lead_time_note}</p>
    </section>
  )
}
