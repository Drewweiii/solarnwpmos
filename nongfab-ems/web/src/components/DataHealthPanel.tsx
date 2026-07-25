// System Health & Anomalies (2026-07-25). Two diagnostics that were previously
// invisible on the site:
//
// 1. DATA FEED HEALTH. Every model input comes from an external source on its own
//    cadence. When one silently stops, the model keeps answering - it just falls
//    back to defaults, and nothing said so. That is exactly how the CAMS aerosol
//    feed broke earlier the same day (a startup backfill with no refresh loop);
//    the only symptom was five cells reading "no data". This names it.
//    Observation feeds are judged on how OLD their newest row is; forecast
//    ("coverage") feeds on how far FORWARD they still reach, because a forecast
//    feed that is merely recent has already run out of usable window.
//
// 2. OUTPUT ANOMALIES. Days whose expected energy fell well below the month's
//    norm, with the likely weather driver ranked. The panel repeats the server's
//    `basis_note`: with no metered output at this site, this never claims the
//    array itself underperformed - it flags a day worth looking at and names the
//    measured weather that most likely explains it.
import { useFeedHealth, useOutputAnomalies } from '../lib/queries'
import { formatDateHourIct } from '../lib/timeScrub'

export interface DataHealthPanelProps {
  zone: string
}

const STATUS_BADGE: Record<string, { icon: string; label: string; className: string }> = {
  ok: { icon: '🟢', label: 'ปกติ', className: 'health-ok' },
  stale: { icon: '🟡', label: 'ข้อมูลค้าง', className: 'health-stale' },
  missing: { icon: '🔴', label: 'ไม่มีข้อมูล', className: 'health-missing' },
}

const CAUSE_LABEL: Record<string, string> = {
  cloud: '☁️ เมฆ',
  rain: '🌧️ ฝน',
  soiling: '🧽 คราบสกปรก',
  aerosol: '🌫️ ฝุ่น/ละออง',
  unknown: '❓ ไม่ระบุ',
}

function badge(status: string) {
  return STATUS_BADGE[status] ?? { icon: '⚪', label: status, className: '' }
}

export function DataHealthPanel({ zone }: DataHealthPanelProps) {
  const feeds = useFeedHealth()
  const anomalies = useOutputAnomalies(zone)
  const overall = feeds.data ? badge(feeds.data.overall_status) : null

  return (
    <section className="verify-panel" aria-label="System health and anomalies">
      <h3 className="forecast-minute-title">🩺 สุขภาพข้อมูลและความผิดปกติ (System Health &amp; Anomalies)</h3>

      {feeds.isLoading && <p className="forecast-status">กำลังตรวจสอบแหล่งข้อมูล…</p>}
      {feeds.data && overall && (
        <>
          <div className={`health-overall ${overall.className}`}>
            <span className="health-overall-icon" aria-hidden="true">
              {overall.icon}
            </span>
            <span className="health-overall-label">
              สถานะรวมของแหล่งข้อมูล: <b>{overall.label}</b> · ตรวจเมื่อ {formatDateHourIct(feeds.data.checked_at)}
            </span>
          </div>

          <div className="verify-table-scroll">
            <table className="verify-table">
              <caption>
                แหล่งข้อมูลที่โมเดลใช้ — feed แบบ &ldquo;พยากรณ์&rdquo; วัดจากการครอบคลุม<b>ล่วงหน้า</b> ไม่ใช่ความใหม่
                (ถ้าครอบคลุมหมด โมเดลจะเงียบๆ กลับไปใช้ค่า default)
              </caption>
              <thead>
                <tr>
                  <th scope="col">แหล่งข้อมูล</th>
                  <th scope="col">ประเภท</th>
                  <th scope="col">สถานะ</th>
                  <th scope="col">แถว</th>
                  <th scope="col">รายละเอียด</th>
                </tr>
              </thead>
              <tbody>
                {feeds.data.feeds.map((feed) => {
                  const b = badge(feed.status)
                  return (
                    <tr key={feed.name} className={b.className}>
                      <th scope="row">{feed.label}</th>
                      <td>{feed.kind === 'coverage' ? 'พยากรณ์ (ล่วงหน้า)' : 'ค่าที่วัดได้'}</td>
                      <td>
                        {b.icon} {b.label}
                      </td>
                      <td>{feed.rows.toLocaleString()}</td>
                      <td className="health-detail">{feed.detail}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h4 className="health-subtitle">วันที่ผลผลิตต่ำกว่าปกติ ({zone})</h4>
      {anomalies.isLoading && <p className="forecast-status">กำลังหาวันที่ผิดปกติ…</p>}
      {anomalies.data && !anomalies.data.available && (
        <p className="forecast-status forecast-status-caption">{anomalies.data.reason}</p>
      )}
      {anomalies.data?.available && anomalies.data.anomalies.length === 0 && (
        <p className="forecast-status forecast-status-caption">
          ✅ ไม่พบวันที่ต่ำกว่าเกณฑ์ในช่วง {anomalies.data.days_assessed} วันที่ตรวจ (เกณฑ์ปกติ{' '}
          {anomalies.data.norm_kwh_per_day?.toFixed(0)} kWh/วัน)
        </p>
      )}
      {anomalies.data?.available && anomalies.data.anomalies.length > 0 && (
        <div className="verify-table-scroll">
          <table className="verify-table">
            <caption>
              เทียบกับค่าปกติของเดือนนี้ {anomalies.data.norm_kwh_per_day?.toFixed(0)} kWh/วัน (จาก{' '}
              {anomalies.data.days_assessed} วันที่ตรวจ)
            </caption>
            <thead>
              <tr>
                <th scope="col">วันที่</th>
                <th scope="col">ได้จริง (kWh)</th>
                <th scope="col">% ของปกติ</th>
                <th scope="col">ขาดไป (kWh)</th>
                <th scope="col">สาเหตุที่เป็นไปได้</th>
              </tr>
            </thead>
            <tbody>
              {anomalies.data.anomalies.map((a) => (
                <tr key={a.day}>
                  <th scope="row">{a.day}</th>
                  <td>{a.energy_kwh.toFixed(1)}</td>
                  <td>{(a.ratio * 100).toFixed(0)}%</td>
                  <td>{a.shortfall_kwh.toFixed(1)}</td>
                  <td className="health-detail">
                    {CAUSE_LABEL[a.likely_cause] ?? a.likely_cause} — {a.cause_detail}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {anomalies.data && <p className="forecast-status forecast-status-caption">{anomalies.data.basis_note}</p>}
    </section>
  )
}
