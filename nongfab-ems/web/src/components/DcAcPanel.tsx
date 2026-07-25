import { useDcAc } from '../lib/queries'
import type { ZoneRatio } from '../lib/types'

/** Inverter clipping and DC headroom (project F, 2026-07-25).
 *
 * Two findings, and the second is the useful one:
 *
 *  1. This site barely clips. GIS's DC:AC of 1.20 reads as "expect midday
 *     clipping", but after a ~20% loss stack the AC side almost never reaches
 *     the inverter's rating, so the real loss is a fraction of a percent.
 *  2. ISB's inverter is LARGER than its array - free capacity that modules
 *     could use without buying an inverter.
 *
 * The panel deliberately names no "optimal" ratio: more DC always yields more
 * energy, so an optimum would be an artefact of the placeholder CAPEX. It shows
 * what the next kWp is worth instead, which a real quote can be divided by.
 */

const nf0 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 1 })
const nf2 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 2 })

/** How to describe a zone's sizing in one phrase. Exported for tests: the
 * boundary at 1.0 is what separates "has free room" from "is over-sized", and
 * mislabelling it would invert the panel's only recommendation. */
export function sizingLabel(zone: ZoneRatio): string {
  if (zone.has_headroom) return 'อินเวอร์เตอร์ใหญ่กว่าแผง — ใส่แผงเพิ่มได้ฟรี'
  if (zone.built.clipping_loss_pct >= 1.0) return 'แผงใหญ่กว่าอินเวอร์เตอร์ — เริ่มมีการตัดยอด'
  return 'สมดุลดี — แทบไม่มีการตัดยอด'
}

export function DcAcPanel() {
  const { data, isLoading, isError } = useDcAc()

  if (isLoading) {
    return (
      <section className="forecast-panel">
        <h3>ขนาดแผงเทียบอินเวอร์เตอร์ (DC:AC) — เสียพลังงานจากการตัดยอดเท่าไร</h3>
        <p className="grid-context-stat-sub">กำลังคำนวณเส้นโค้งการตัดยอด …</p>
      </section>
    )
  }

  if (isError || !data) {
    return (
      <section className="forecast-panel">
        <h3>ขนาดแผงเทียบอินเวอร์เตอร์ (DC:AC)</h3>
        <p className="grid-context-stat-sub">ยังคำนวณไม่ได้ในขณะนี้</p>
      </section>
    )
  }

  const headroomZones = data.zones.filter((z) => z.has_headroom)

  return (
    <section className="forecast-panel">
      <h3>ขนาดแผงเทียบอินเวอร์เตอร์ (DC:AC) — เสียพลังงานจากการตัดยอดเท่าไร</h3>

      <div className="grid-context-stats">
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">พลังงานที่ถูกอินเวอร์เตอร์ตัดทิ้งทั้งไซต์</span>
          <strong>{nf0.format(data.total_clipped_kwh)}</strong>
          <span className="grid-context-stat-sub">kWh/ปี · น้อยกว่าที่ตัวเลข DC:AC ชวนให้คิดมาก</span>
        </div>
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">กำลังติดตั้งที่ใส่เพิ่มได้โดยไม่ต้องซื้ออินเวอร์เตอร์</span>
          <strong className={data.total_headroom_kwp > 0 ? 'orientation-gain' : ''}>
            {nf1.format(data.total_headroom_kwp)}
          </strong>
          <span className="grid-context-stat-sub">
            kWp{headroomZones.length > 0 && ` · อยู่ที่ ${headroomZones.map((z) => z.zone_id).join(', ')}`}
          </span>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table className="orientation-table">
          <thead>
            <tr>
              <th>โซน</th>
              <th>DC : AC</th>
              <th>ตัดยอด</th>
              <th>ผลผลิตต่อ kWp</th>
              <th>kWp ถัดไปให้</th>
              <th>สรุป</th>
            </tr>
          </thead>
          <tbody>
            {data.zones.map((zone) => (
              <tr key={zone.zone_id}>
                <td>
                  <strong>{zone.zone_id}</strong>
                </td>
                <td>
                  {nf2.format(zone.built.dc_ac_ratio)}
                  <span className="grid-context-stat-sub"> ({nf0.format(zone.ac_capacity_kw)} kW AC)</span>
                </td>
                <td className={zone.built.clipping_loss_pct >= 1.0 ? 'orientation-gain' : 'orientation-flat'}>
                  {nf2.format(zone.built.clipping_loss_pct)}%
                </td>
                <td>{nf0.format(zone.built.specific_yield_kwh_per_kwp)} kWh/kWp</td>
                <td>
                  {zone.marginal_kwh_per_added_kwp === null
                    ? '—'
                    : `${nf0.format(zone.marginal_kwh_per_added_kwp)} kWh/ปี`}
                </td>
                <td className="grid-context-stat-sub">{sizingLabel(zone)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="grid-context-stat-sub orientation-warning">{data.no_optimum_note}</p>

      <details>
        <summary style={{ cursor: 'pointer', fontSize: '0.85rem' }}>คำนวณยังไง</summary>
        <p className="grid-context-stat-sub">{data.method_note}</p>
      </details>
    </section>
  )
}
