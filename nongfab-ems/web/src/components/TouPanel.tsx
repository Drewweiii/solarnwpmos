import { useTou } from '../lib/queries'

/** Does this array produce during the expensive hours? (project G, 2026-07-25)
 *
 * The Savings page prices every kWh at the TOU Peak rate, and said in its own
 * code that this was an approximation because it ignores weekends and off-peak
 * hours. This panel measures the approximation.
 *
 * Nothing published moves because of it: the Off-Peak rate ships equal to the
 * Peak rate, so the blended figure reproduces today's exactly until somebody
 * enters the real rate. The energy split needs no tariff and is real either way.
 */

const nf0 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 1 })
const nf4 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 4 })

export function TouPanel() {
  const { data, isLoading, isError } = useTou()

  if (isLoading) {
    return (
      <section className="forecast-panel">
        <h3>ผลิตตรงกับช่วงค่าไฟแพงไหม (TOU)</h3>
        <p className="grid-context-stat-sub">กำลังแยกพลังงานตามช่วงเวลา Peak / Off-Peak …</p>
      </section>
    )
  }

  if (isError || !data) {
    return (
      <section className="forecast-panel">
        <h3>ผลิตตรงกับช่วงค่าไฟแพงไหม (TOU)</h3>
        <p className="grid-context-stat-sub">ยังคำนวณไม่ได้ในขณะนี้</p>
      </section>
    )
  }

  return (
    <section className="forecast-panel">
      <h3>ผลิตตรงกับช่วงค่าไฟแพงไหม (TOU Peak / Off-Peak)</h3>

      <div className="grid-context-stats">
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">พลังงานที่ตกนอกช่วง Peak</span>
          <strong className="orientation-gain">{nf1.format(data.offpeak_share_pct)}%</strong>
          <span className="grid-context-stat-sub">
            {nf0.format(data.total_offpeak_kwh)} kWh/ปี · หน้า Savings ตีเป็นอัตรา Peak ทั้งหมด
          </span>
        </div>
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">อัตราเฉลี่ยถ่วงน้ำหนักที่แท้จริง</span>
          <strong>{nf4.format(data.blended_rate_thb_per_kwh)}</strong>
          <span className="grid-context-stat-sub">
            บาท/kWh · เทียบกับ {nf4.format(data.peak_rate_thb_per_kwh)} ที่ใช้อยู่
          </span>
        </div>
        <div className="grid-context-stat">
          <span className="grid-context-stat-label">ค่าที่ใช้อยู่สูงเกินจริง</span>
          <strong className={data.overstatement_pct > 0 ? 'orientation-gain' : 'orientation-flat'}>
            {data.offpeak_rate_is_set ? `+${nf1.format(data.overstatement_pct)}%` : 'ยังบอกไม่ได้'}
          </strong>
          <span className="grid-context-stat-sub">
            {data.offpeak_rate_is_set ? 'เทียบกับอัตราเฉลี่ยจริง' : 'ต้องกรอกอัตรา Off-Peak จริงก่อน'}
          </span>
        </div>
      </div>

      {!data.offpeak_rate_is_set && (
        <p className="grid-context-stat-sub orientation-warning">
          ยังไม่ได้กรอกอัตรา Off-Peak จริง — ระบบตั้งไว้เท่ากับอัตรา Peak ไปก่อน
          ตัวเลขเงินที่เผยแพร่จึง<strong>เท่าเดิมทุกประการ</strong> ไม่มีอะไรขยับเงียบๆ
          กรอกอัตราจริงจากประกาศในหน้า Settings แล้วส่วนต่างจะโผล่มาเอง
        </p>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table className="orientation-table">
          <thead>
            <tr>
              <th>โซน</th>
              <th>ผลิตในช่วง Peak</th>
              <th>ผลิตนอกช่วง Peak</th>
            </tr>
          </thead>
          <tbody>
            {data.zones.map((zone) => (
              <tr key={zone.zone_id}>
                <td>
                  <strong>{zone.zone_id}</strong>
                </td>
                <td>
                  {nf1.format(zone.peak_share_pct)}%
                  <span className="grid-context-stat-sub"> ({nf0.format(zone.peak_kwh)} kWh)</span>
                </td>
                <td>
                  {nf1.format(zone.offpeak_share_pct)}%
                  <span className="grid-context-stat-sub"> ({nf0.format(zone.offpeak_kwh)} kWh)</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="grid-context-stat-sub">{data.window_note}</p>
      <p className="grid-context-stat-sub">
        <strong>ที่มองข้ามง่าย:</strong> {data.finding_note}
      </p>
      <p className="grid-context-stat-sub orientation-assumed">{data.holiday_note}</p>
    </section>
  )
}
