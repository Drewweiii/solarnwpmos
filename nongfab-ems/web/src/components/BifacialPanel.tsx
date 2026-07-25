import { useBifacial } from '../lib/queries'

/** The rear face nobody is counting (project H, 2026-07-25).
 *
 * The installed module is bifacial and every published yield figure treats it
 * as one-sided. This says how much that leaves out - and, just as importantly,
 * that the figure is NOT in those published numbers, because rear gain turns on
 * ground albedo and mounting height that nobody measured.
 *
 * Each row carries the two assumptions that produced its number, so a reader
 * can see what the estimate rests on without leaving the row.
 */

const nf1 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 1 })
const nf2 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 2 })

export function BifacialPanel() {
  const { data, isLoading, isError } = useBifacial()

  if (isLoading) {
    return (
      <section className="forecast-panel">
        <h3>แผงสองหน้า (bifacial) — ด้านหลังรับแสงได้เท่าไร</h3>
        <p className="grid-context-stat-sub">กำลังคำนวณแสงที่ตกด้านหลังแผง …</p>
      </section>
    )
  }

  if (isError || !data) {
    return (
      <section className="forecast-panel">
        <h3>แผงสองหน้า (bifacial)</h3>
        <p className="grid-context-stat-sub">ยังคำนวณไม่ได้ในขณะนี้</p>
      </section>
    )
  }

  return (
    <section className="forecast-panel">
      <h3>แผงสองหน้า (bifacial) — ด้านหลังรับแสงได้เท่าไร</h3>

      <p className="grid-context-stat-sub">{data.module_note}</p>

      <div style={{ overflowX: 'auto' }}>
        <table className="orientation-table">
          <thead>
            <tr>
              <th>โซน</th>
              <th>พื้นใต้แผง</th>
              <th>ได้เพิ่มจากด้านหลัง</th>
              <th>สมมติ albedo</th>
              <th>สมมติความสูง</th>
            </tr>
          </thead>
          <tbody>
            {data.zones.map((zone) => (
              <tr key={zone.zone_id}>
                <td>
                  <strong>{zone.zone_id}</strong>
                </td>
                <td>{zone.ground_label}</td>
                <td className="orientation-gain">
                  +{nf1.format(zone.gain_pct)}%
                  <span className="grid-context-stat-sub">
                    {' '}
                    ({nf1.format(zone.gain_pct_low)}–{nf1.format(zone.gain_pct_high)}%)
                  </span>
                </td>
                <td className="orientation-assumed">{nf2.format(zone.albedo_assumed)}</td>
                <td className="orientation-assumed">{nf1.format(zone.height_m_assumed)} ม.</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="grid-context-stat-sub orientation-warning">{data.not_applied_note}</p>
      <p className="grid-context-stat-sub">
        <strong>ปลดล็อกยังไง:</strong> {data.unlock_note}
      </p>

      <details>
        <summary style={{ cursor: 'pointer', fontSize: '0.85rem' }}>คำนวณยังไง</summary>
        <p className="grid-context-stat-sub">{data.method_note}</p>
      </details>
    </section>
  )
}
