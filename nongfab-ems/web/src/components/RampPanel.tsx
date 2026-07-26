import { useForecastRamp } from '../lib/queries'
import { formatHourIct } from '../lib/timeScrub'
import type { RampResponse, RampStep } from '../lib/types'

/** How fast is the output about to change? (2026-07-25, project B)
 *
 * Every other forecast surface on this page answers "how much". None of them
 * answers "how fast", and those are different questions: a cloud front takes an
 * array from near-nameplate to a fraction of it inside an hour, and a level
 * forecast that is accurate at both ends still never says a cliff sits between
 * them.
 *
 * Two halves, and the second is what makes the first readable. The upcoming
 * ramps come from the intra-day series the chart above already draws; the
 * history is measured from recorded output, and answers "is a 60%/h fall
 * unusual here, or does it happen twice a week".
 *
 * The panel states plainly that nobody is expected to act on this. Nong Fab is
 * fully grid-tied with no battery and no curtailment - there is nothing to
 * dispatch. Presenting a ramp warning as an operational alert would dress the
 * number up as something this plant cannot use.
 */

const nf0 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 1 })

/** Exported for tests: the boundary between "worth a sentence" and "ordinary
 * afternoon drift" is the panel's only judgement, and getting it backwards
 * would either cry wolf daily or stay silent through a collapse. */
export function severityLabel(step: RampStep): string {
  if (step.severity === 'steep') return step.direction === 'down' ? 'ร่วงแรง' : 'พุ่งแรง'
  if (step.severity === 'moderate') return step.direction === 'down' ? 'ลดปานกลาง' : 'เพิ่มปานกลาง'
  return 'นิ่ง'
}

function severityClass(step: RampStep): string {
  if (step.severity === 'steep') return 'ramp-steep'
  if (step.severity === 'moderate') return 'ramp-moderate'
  return 'ramp-calm'
}

function AlertBanner({ data }: { data: RampResponse }) {
  const alert = data.alert
  if (!alert) {
    return (
      <p className="ramp-alert ramp-alert-quiet">
        ✅ <b>ช่วงข้างหน้ายังไม่มีการร่วงแรง</b> — กำลังผลิตที่พยากรณ์ไว้เปลี่ยนแปลงไม่เกินเกณฑ์{' '}
        {nf0.format(data.moderate_pct_per_h)}% ของกำลังติดตั้งต่อชั่วโมง
      </p>
    )
  }
  const pct = alert.pct_of_capacity_per_h
  return (
    <p className={`ramp-alert ${alert.severity === 'steep' ? 'ramp-alert-steep' : 'ramp-alert-moderate'}`}>
      ⚠️ <b>กำลังผลิตจะร่วง {nf1.format(Math.abs(alert.delta_kw))} kW</b> ระหว่าง {formatHourIct(alert.from_time)}–
      {formatHourIct(alert.to_time)} น.
      {pct !== null && <> (เท่ากับ {nf0.format(Math.abs(pct))}% ของกำลังติดตั้งต่อชั่วโมง)</>} — จาก{' '}
      {nf1.format(alert.from_kw)} เหลือ {nf1.format(alert.to_kw)} kW
    </p>
  )
}

export function RampPanel({ zone }: { zone: string }) {
  const { data, isLoading, isError } = useForecastRamp(zone)

  if (isLoading) {
    return (
      <section className="forecast-panel" aria-label="Ramp forecast">
        <h3>อัตราการเปลี่ยนแปลงกำลังผลิต (Ramp) — จะขึ้น-ลงเร็วแค่ไหน</h3>
        <p className="grid-context-stat-sub">กำลังคำนวณอัตราการเปลี่ยนแปลง …</p>
      </section>
    )
  }

  if (isError || !data) {
    return (
      <section className="forecast-panel" aria-label="Ramp forecast">
        <h3>อัตราการเปลี่ยนแปลงกำลังผลิต (Ramp)</h3>
        <p className="grid-context-stat-sub">ยังคำนวณไม่ได้ในขณะนี้</p>
      </section>
    )
  }

  if (!data.available) {
    return (
      <section className="forecast-panel" aria-label="Ramp forecast">
        <h3>อัตราการเปลี่ยนแปลงกำลังผลิต (Ramp)</h3>
        <p className="grid-context-stat-sub">{data.reason}</p>
      </section>
    )
  }

  const history = data.history
  const notableAhead = data.upcoming.filter((step) => step.severity !== 'calm')

  return (
    <section className="forecast-panel" aria-label="Ramp forecast">
      <h3>อัตราการเปลี่ยนแปลงกำลังผลิต (Ramp) — จะขึ้น-ลงเร็วแค่ไหน</h3>

      <AlertBanner data={data} />

      {notableAhead.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="orientation-table">
            <thead>
              <tr>
                <th>ช่วงเวลา</th>
                <th>จาก → ถึง</th>
                <th>เปลี่ยนไป</th>
                <th>% กำลังติดตั้ง/ชม.</th>
                <th>ระดับ</th>
              </tr>
            </thead>
            <tbody>
              {notableAhead.map((step) => (
                <tr key={step.from_time}>
                  <td>
                    {formatHourIct(step.from_time)}–{formatHourIct(step.to_time)}
                  </td>
                  <td>
                    {nf1.format(step.from_kw)} → {nf1.format(step.to_kw)} kW
                  </td>
                  <td className={severityClass(step)}>
                    {step.delta_kw >= 0 ? '+' : ''}
                    {nf1.format(step.delta_kw)} kW
                  </td>
                  <td className={severityClass(step)}>
                    {step.pct_of_capacity_per_h === null
                      ? '—'
                      : `${step.pct_of_capacity_per_h >= 0 ? '+' : ''}${nf0.format(step.pct_of_capacity_per_h)}%`}
                  </td>
                  <td>{severityLabel(step)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {history && history.n_steps > 0 && (
        <div className="grid-context-stats">
          <div className="grid-context-stat">
            <span className="grid-context-stat-label">ร่วงแรงในรอบ {data.history_days} วัน</span>
            <strong>{history.n_steep_down}</strong>
            <span className="grid-context-stat-sub">
              ครั้ง · ลดปานกลางอีก {history.n_moderate_down} ครั้ง (จาก {history.n_steps} ช่วงเวลา)
            </span>
          </div>
          <div className="grid-context-stat">
            <span className="grid-context-stat-label">ร่วงแรงที่สุดที่เคยวัดได้</span>
            <strong>
              {history.worst_down_pct_per_h === null ? '—' : `${nf0.format(history.worst_down_pct_per_h)}%`}
            </strong>
            <span className="grid-context-stat-sub">ของกำลังติดตั้งต่อชั่วโมง</span>
          </div>
          <div className="grid-context-stat">
            <span className="grid-context-stat-label">ชั่วโมงที่มักร่วง</span>
            <strong>
              {history.busiest_down_hour_ict === null
                ? '—'
                : `${String(history.busiest_down_hour_ict).padStart(2, '0')}:00`}
            </strong>
            <span className="grid-context-stat-sub">
              {history.busiest_down_hour_ict === null
                ? 'ยังไม่มีการร่วงที่เข้าเกณฑ์'
                : `เวลาไทย · เกิด ${history.busiest_down_hour_count} ครั้งในช่วงนี้`}
            </span>
          </div>
        </div>
      )}

      <p className="grid-context-stat-sub orientation-warning">{data.no_action_note}</p>

      <details>
        <summary style={{ cursor: 'pointer', fontSize: '0.85rem' }}>คำนวณยังไง</summary>
        <p className="grid-context-stat-sub">{data.method_note}</p>
        <p className="grid-context-stat-sub">
          เกณฑ์ปัจจุบัน: ปานกลาง ≥ {nf0.format(data.moderate_pct_per_h)}%/ชม. · รุนแรง ≥{' '}
          {nf0.format(data.steep_pct_per_h)}%/ชม. (ปรับได้ในหน้า Settings)
        </p>
      </details>
    </section>
  )
}
