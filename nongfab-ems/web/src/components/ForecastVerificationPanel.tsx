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
import type { VerificationMetrics, VerificationResponse } from '../lib/types'
import { Provenanced } from './Provenanced'

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
          <Provenanced valueKey="verification.skill_score">Skill score เทียบ persistence</Provenanced> ·{' '}
          {verdict.label}
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

      <IntervalSection data={data} />

      <SkySection data={data} />

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

/** Did the band the chart draws actually hold? (2026-07-25, project A)
 *
 * The forecast chart shades a nominal 90% prediction interval. Whether reality
 * landed inside it 90% of the time had never been measured against issued
 * forecasts - the PICP figure elsewhere in this codebase is computed on a
 * training hold-out, which is the exact distinction the rest of this panel
 * exists to draw for the point forecast.
 *
 * Coverage is shown next to mean width on purpose. Coverage on its own is
 * trivially gamed: a band from -∞ to +∞ scores 100%. Pinball loss is included
 * because it is a proper scoring rule - widening the band cannot improve it.
 */
function IntervalSection({ data }: { data: VerificationResponse }) {
  const interval = data.interval
  // Older API builds don't send this block at all; a panel that crashed on a
  // stale backend would be a worse regression than a missing section.
  if (!interval) return null

  if (interval.n === 0) {
    return (
      <p className="forecast-status forecast-status-caption">
        <b>แถบความเชื่อมั่น:</b> ยังตรวจไม่ได้ในช่วงนี้ — คำพยากรณ์ที่บันทึกไว้ยังไม่มีแถบความเชื่อมั่นแนบมา
        (โหมดสำรองเชิงฟิสิกส์ไม่ได้เผยแพร่แถบ) ซึ่ง<b>ไม่ได้แปลว่าแถบพลาด</b> แต่แปลว่ายังไม่มีอะไรให้ตรวจ
      </p>
    )
  }

  // Negative gap = narrower than advertised = overconfident. That direction is
  // the one worth flagging: a viewer reads the shaded band as a promise.
  const overconfident = interval.coverage_gap_pct < -5
  const tooWide = interval.coverage_gap_pct > 5

  return (
    <div className="verify-interval">
      <h4 className="verify-interval-title">แถบความเชื่อมั่นที่เผยแพร่ เชื่อถือได้แค่ไหน</h4>

      <div className="verify-interval-stats">
        <div className="verify-interval-stat">
          <span className="verify-interval-label">ครอบคลุมความจริงได้จริง</span>
          <strong className={overconfident ? 'verify-interval-bad' : 'verify-interval-good'}>
            {interval.coverage_pct.toFixed(1)}%
          </strong>
          <span className="verify-interval-sub">
            ควรได้ {interval.nominal_pct.toFixed(0)}% · ต่าง {interval.coverage_gap_pct >= 0 ? '+' : ''}
            {interval.coverage_gap_pct.toFixed(1)} จุด
          </span>
        </div>
        <div className="verify-interval-stat">
          <span className="verify-interval-label">ความกว้างเฉลี่ยของแถบ</span>
          <strong>{interval.mean_width_kw.toFixed(1)} kW</strong>
          <span className="verify-interval-sub">
            {interval.pinaw_pct === null ? 'ยังเทียบกับกำลังติดตั้งไม่ได้' : `${interval.pinaw_pct.toFixed(1)}% ของกำลังติดตั้ง`}
          </span>
        </div>
        <div className="verify-interval-stat">
          <span className="verify-interval-label">Pinball loss</span>
          <strong>{interval.pinball_kw.toFixed(2)} kW</strong>
          <span className="verify-interval-sub">ยิ่งต่ำยิ่งดี · ขยายแถบเฉยๆ ไม่ช่วย</span>
        </div>
        <div className="verify-interval-stat">
          <span className="verify-interval-label">พลาดไปทางไหน</span>
          <strong>
            ต่ำ {interval.miss_low_pct.toFixed(1)}% / สูง {interval.miss_high_pct.toFixed(1)}%
          </strong>
          <span className="verify-interval-sub">พลาดข้างเดียวมากๆ = แถบวางผิดตำแหน่ง ไม่ใช่แค่แคบไป</span>
        </div>
      </div>

      <p className="forecast-status forecast-status-caption">
        {overconfident && (
          <>
            <b>ผลตรวจ: แถบแคบเกินจริง</b> — ความจริงหลุดออกนอกแถบบ่อยกว่าที่แถบรับปากไว้ ผู้อ่านกราฟจึงกำลังเห็นความมั่นใจ
            ที่มากเกินกว่าที่โมเดลมีจริง{' '}
          </>
        )}
        {tooWide && (
          <>
            <b>ผลตรวจ: แถบกว้างเกินจำเป็น</b> — ครอบคลุมได้เกินเป้า แปลว่าปลอดภัยไว้ก่อน แต่แถบที่กว้างเกินไปแทบไม่บอกอะไร{' '}
          </>
        )}
        {!overconfident && !tooWide && (
          <>
            <b>ผลตรวจ: แถบสมเหตุสมผล</b> — ครอบคลุมได้ใกล้เคียงกับที่รับปากไว้{' '}
          </>
        )}
        (จาก {interval.n} ชั่วโมงที่มีแดดและมีแถบแนบมาจริง)
      </p>

      {data.interval_note && <p className="forecast-status forecast-status-caption">{data.interval_note}</p>}
      {data.pinball_note && <p className="forecast-status forecast-status-caption">{data.pinball_note}</p>}
    </div>
  )
}

/** Which skies does this model actually struggle with? (2026-07-25, project C)
 *
 * One RMSE per zone averages a cloudless January morning together with an
 * afternoon of monsoon convection, and a model can look respectable by being
 * good at the easy half. Splitting by clear-sky index is how solar-forecasting
 * work is expected to report itself, and it answers the question a single
 * number cannot: not "how big is the error" but "when is this model helpless".
 *
 * Buckets with no hours are still rendered, greyed: an omitted row reads as a
 * condition with no errors rather than one with no data.
 */
const SKY_LABELS: Record<string, string> = {
  clear: '☀️ ฟ้าใส',
  partly_cloudy: '⛅ มีเมฆบางส่วน',
  overcast: '☁️ ฟ้าครึ้ม',
}

function SkySection({ data }: { data: VerificationResponse }) {
  const rows = data.by_sky
  // Older API builds omit the block entirely.
  if (!rows || rows.length === 0) return null

  const scored = rows.filter((row) => row.metrics.n > 0)
  if (scored.length === 0) {
    return (
      <p className="forecast-status forecast-status-caption">
        <b>แยกตามสภาพฟ้า:</b> ยังแยกไม่ได้ — ยังไม่มีชั่วโมงไหนที่บอกสภาพฟ้าได้จากข้อมูลพยากรณ์อากาศที่เก็บไว้
        {data.sky_unclassified_n ? ` (${data.sky_unclassified_n} ชั่วโมงระบุสภาพฟ้าไม่ได้)` : ''}
      </p>
    )
  }

  // The hardest condition by RMSE, among those that actually have hours. Named
  // rather than left for the reader to spot in the table - it is the finding.
  const worst = scored.reduce((a, b) => (b.metrics.rmse_kw > a.metrics.rmse_kw ? b : a))

  return (
    <div className="verify-interval">
      <h4 className="verify-interval-title">โมเดลพลาดตอนฟ้าเป็นแบบไหน</h4>

      <div className="verify-table-scroll">
        <table className="verify-table">
          <thead>
            <tr>
              <th scope="col">สภาพฟ้า</th>
              <th scope="col">n (ชม.)</th>
              <th scope="col">MAE (kW)</th>
              <th scope="col">RMSE (kW)</th>
              <th scope="col">อคติ MBE (kW)</th>
              <th scope="col">Skill</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.sky} className={row.metrics.n === 0 ? 'verify-sky-empty' : undefined}>
                <th scope="row">{SKY_LABELS[row.sky] ?? row.sky}</th>
                <td>{row.metrics.n}</td>
                <td>{row.metrics.n === 0 ? '—' : row.metrics.mae_kw.toFixed(2)}</td>
                <td>{row.metrics.n === 0 ? '—' : row.metrics.rmse_kw.toFixed(2)}</td>
                <td>
                  {row.metrics.n === 0
                    ? '—'
                    : `${row.metrics.mbe_kw >= 0 ? '+' : ''}${row.metrics.mbe_kw.toFixed(2)}`}
                </td>
                <td>{row.metrics.skill_score == null ? '—' : row.metrics.skill_score.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="forecast-status forecast-status-caption">
        <b>สภาพฟ้าที่ยากที่สุดตอนนี้คือ {SKY_LABELS[worst.sky] ?? worst.sky}</b> (RMSE {worst.metrics.rmse_kw.toFixed(2)} kW จาก{' '}
        {worst.metrics.n} ชั่วโมง) — ตัวเลข RMSE รวมของทั้งไซต์กลบเรื่องนี้ไว้ เพราะเฉลี่ยวันฟ้าใสที่ทำนายง่ายเข้าไปด้วย
        {data.sky_unclassified_n ? ` · อีก ${data.sky_unclassified_n} ชั่วโมงระบุสภาพฟ้าไม่ได้ จึงไม่ถูกนับในตารางนี้` : ''}
      </p>
      {data.sky_note && <p className="forecast-status forecast-status-caption">{data.sky_note}</p>}
    </div>
  )
}
