import { useOrientation } from '../lib/queries'
import type { ZoneOrientation } from '../lib/types'

/** Is the array pointed the right way? (project D, 2026-07-25)
 *
 * Shows, per zone, the orientation that collects the most energy at Nong Fab's
 * latitude next to the one the system currently models.
 *
 * The caveat is not a footnote here, it is the design constraint. No zone's
 * tilt or azimuth was ever surveyed - assets.yaml says `tilt_deg: null` for all
 * three - so the "gain" column compares against an ASSUMED angle. The panel
 * leads with the optimum (which is real: it comes from the sun path, not from
 * what was built) and marks every gain figure as provisional until somebody
 * measures the array.
 */

const nf0 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 1 })

/** 180 -> "ใต้". Exported for tests: a wrong compass label would make a correct
 * optimum read as nonsense, and it is the sort of thing that only breaks at the
 * boundaries. */
export function compassLabel(azimuthDeg: number): string {
  const points = ['เหนือ', 'ตอ.เฉียงเหนือ', 'ตะวันออก', 'ตอ.เฉียงใต้', 'ใต้', 'ตต.เฉียงใต้', 'ตะวันตก', 'ตต.เฉียงเหนือ']
  const index = Math.round((((azimuthDeg % 360) + 360) % 360) / 45) % 8
  return points[index]
}

function ZoneRow({ zone }: { zone: ZoneOrientation }) {
  const improves = zone.gain_pct > 0.05
  return (
    <tr>
      <td>
        <strong>{zone.zone_id}</strong>
      </td>
      <td>
        {nf0.format(zone.current.tilt_deg)}° / {nf0.format(zone.current.azimuth_deg)}° ({compassLabel(zone.current.azimuth_deg)})
        {!zone.current_is_measured && <span className="orientation-assumed"> · ค่าสมมติ</span>}
      </td>
      <td>
        {nf0.format(zone.optimum.tilt_deg)}° / {nf0.format(zone.optimum.azimuth_deg)}° ({compassLabel(zone.optimum.azimuth_deg)})
      </td>
      <td className={improves ? 'orientation-gain' : 'orientation-flat'}>
        {improves ? `+${nf1.format(zone.gain_pct)}%` : 'ตรงจุดที่ดีที่สุดแล้ว'}
      </td>
    </tr>
  )
}

export function OrientationPanel() {
  const { data, isLoading, isError } = useOrientation()

  if (isLoading) {
    return (
      <section className="forecast-panel">
        <h3>มุมติดตั้งแผง — ตอนนี้เทียบกับที่ดีที่สุด</h3>
        <p className="grid-context-stat-sub">กำลังกวาดหามุมที่ให้พลังงานสูงสุดจากเส้นทางดวงอาทิตย์ …</p>
      </section>
    )
  }

  if (isError || !data) {
    return (
      <section className="forecast-panel">
        <h3>มุมติดตั้งแผง — ตอนนี้เทียบกับที่ดีที่สุด</h3>
        <p className="grid-context-stat-sub">ยังคำนวณมุมที่ดีที่สุดไม่ได้ในขณะนี้</p>
      </section>
    )
  }

  const jetty = data.zones.find((z) => z.note !== null)

  return (
    <section className="forecast-panel">
      <h3>มุมติดตั้งแผง — ตอนนี้เทียบกับที่ดีที่สุด</h3>

      {data.any_unmeasured && (
        <p className="grid-context-stat-sub orientation-warning">{data.unmeasured_note}</p>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table className="orientation-table">
          <thead>
            <tr>
              <th>โซน</th>
              <th>มุมที่ระบบใช้อยู่ (เอียง / ทิศ)</th>
              <th>มุมที่ดีที่สุด</th>
              <th>ส่วนต่าง</th>
            </tr>
          </thead>
          <tbody>
            {data.zones.map((zone) => (
              <ZoneRow key={zone.zone_id} zone={zone} />
            ))}
          </tbody>
        </table>
      </div>

      <p className="grid-context-stat-sub">
        <strong>ใช้ได้ทันทีกับเฟสขยาย:</strong> {data.expansion_note}
      </p>

      {jetty && <p className="grid-context-stat-sub">{jetty.note}</p>}

      <details>
        <summary style={{ cursor: 'pointer', fontSize: '0.85rem' }}>คำนวณยังไง และทำไมตัวเลขนี้ไม่ไปเปลี่ยนหน้า Financial</summary>
        <p className="grid-context-stat-sub">{data.method_note}</p>
        <p className="grid-context-stat-sub">{data.pipeline_note}</p>
      </details>
    </section>
  )
}
