import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useForecastEvolution } from '../lib/queries'
import { formatDateHourIct } from '../lib/timeScrub'
import type { EvolutionResponse } from '../lib/types'

/** Did the forecast settle, or lurch? (2026-07-25, project D)
 *
 * A forecast is not one number, it is a sequence of answers to the same
 * question, each issued closer to the event than the last. This page has only
 * ever shown the newest answer, which hides the thing that actually earns or
 * loses trust in a model: whether its story converges as the hour approaches.
 *
 * 180 → 175 → 172 is a model that knew early. 180 → 90 → 165 is not, even if
 * the last number turns out to be right. On a chart that shows only the latest
 * issuance, those two look identical.
 *
 * The x-axis is LEAD TIME, counting down to zero, so the reader follows the
 * story toward the event rather than left-to-right in issue order.
 */

const nf1 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 1 })

function convergenceVerdict(data: NonNullable<EvolutionResponse['highlight']>): string {
  if (data.is_converging === null) return 'ยังบอกไม่ได้ว่าลู่เข้าหรือไม่ — คำพยากรณ์ยังน้อยรอบเกินไป'
  if (data.is_converging) return 'คำทำนายค่อยๆ นิ่งลงเมื่อใกล้เวลาจริง — เป็นพฤติกรรมที่ควรเป็น'
  return 'คำทำนายยังแกว่งแรงตอนใกล้เวลาจริง — แปลว่ารอบท้ายๆ ยังเปลี่ยนใจมาก'
}

export function ForecastEvolutionPanel({ zone }: { zone: string }) {
  const { data, isLoading, isError } = useForecastEvolution(zone)

  if (isLoading) {
    return (
      <section className="forecast-panel" aria-label="Forecast evolution">
        <h3>คำพยากรณ์เปลี่ยนไปยังไงเมื่อใกล้เวลาจริง (Forecast evolution)</h3>
        <p className="grid-context-stat-sub">กำลังดึงประวัติคำพยากรณ์ …</p>
      </section>
    )
  }

  if (isError || !data) {
    return (
      <section className="forecast-panel" aria-label="Forecast evolution">
        <h3>คำพยากรณ์เปลี่ยนไปยังไงเมื่อใกล้เวลาจริง (Forecast evolution)</h3>
        <p className="grid-context-stat-sub">ยังดึงข้อมูลไม่ได้ในขณะนี้</p>
      </section>
    )
  }

  if (!data.available || !data.highlight) {
    return (
      <section className="forecast-panel" aria-label="Forecast evolution">
        <h3>คำพยากรณ์เปลี่ยนไปยังไงเมื่อใกล้เวลาจริง (Forecast evolution)</h3>
        <p className="grid-context-stat-sub">{data.reason}</p>
        <p className="grid-context-stat-sub orientation-warning">{data.collection_note}</p>
      </section>
    )
  }

  const highlight = data.highlight
  // Lead time descending: the leftmost point is the earliest answer, the
  // rightmost the one given just before the hour arrived.
  const rows = highlight.issuances.map((issuance) => ({
    lead: Number(issuance.lead_hours.toFixed(1)),
    pred: Number(issuance.pred_kw.toFixed(2)),
  }))
  const latest = highlight.latest_pred_kw

  return (
    <section className="forecast-panel" aria-label="Forecast evolution">
      <h3>คำพยากรณ์เปลี่ยนไปยังไงเมื่อใกล้เวลาจริง (Forecast evolution)</h3>
      <p className="grid-context-stat-sub">
        ชั่วโมงเป้าหมายที่ระบบเปลี่ยนใจมากที่สุดใน {data.window_days} วันล่าสุด:{' '}
        <b>{formatDateHourIct(highlight.target_time)} น.</b> · ถูกพยากรณ์ทั้งหมด {highlight.n_issuances} รอบ
      </p>

      <div className="grid-context-stats">
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">รอบแรกที่ทำนาย</span>
          <strong>{highlight.first_pred_kw === null ? '—' : nf1.format(highlight.first_pred_kw)}</strong>
          <span className="grid-context-stat-sub">kW</span>
        </div>
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">รอบล่าสุด</span>
          <strong>{latest === null ? '—' : nf1.format(latest)}</strong>
          <span className="grid-context-stat-sub">kW</span>
        </div>
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">แกว่งมากสุดระหว่างทาง</span>
          <strong className="orientation-gain">
            {highlight.max_swing_kw === null ? '—' : nf1.format(highlight.max_swing_kw)}
          </strong>
          <span className="grid-context-stat-sub">
            kW · ปรับรวมรอบแรก→ล่าสุด{' '}
            {highlight.total_revision_kw === null
              ? '—'
              : `${highlight.total_revision_kw >= 0 ? '+' : ''}${nf1.format(highlight.total_revision_kw)} kW`}
          </span>
        </div>
      </div>

      <div style={{ width: '100%', height: 210 }}>
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ top: 16, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis
              dataKey="lead"
              // Reversed so time runs toward the event: far-out issuances on the
              // left, the last word on the right.
              reversed
              tick={{ fontSize: 11 }}
              label={{ value: 'ล่วงหน้ากี่ชั่วโมง (ชม.)', position: 'insideBottom', offset: -4, fontSize: 11 }}
            />
            <YAxis unit=" kW" tick={{ fontSize: 11 }} width={62} />
            <Tooltip
              formatter={(value) => (typeof value === 'number' ? `${value.toFixed(1)} kW` : String(value))}
              labelFormatter={(label) => `ออกล่วงหน้า ${label} ชม.`}
            />
            {latest !== null && (
              <ReferenceLine y={latest} stroke="var(--border)" strokeDasharray="4 4" ifOverflow="extendDomain" />
            )}
            <Line type="monotone" dataKey="pred" name="คำพยากรณ์" stroke="var(--chart-aod)" strokeWidth={2} dot />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <p className="grid-context-stat-sub">
        <b>อ่านผล:</b> {convergenceVerdict(highlight)}
        {data.n_targets_with_trend > 1 && ` · มีอีก ${data.n_targets_with_trend - 1} ชั่วโมงที่มีข้อมูลพอจะดูแบบนี้ได้`}
      </p>
      <p className="grid-context-stat-sub orientation-warning">{data.collection_note}</p>

      <details>
        <summary style={{ cursor: 'pointer', fontSize: '0.85rem' }}>คำนวณยังไง</summary>
        <p className="grid-context-stat-sub">{data.method_note}</p>
      </details>
    </section>
  )
}
