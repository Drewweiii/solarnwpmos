// Expansion Planner (2026-07-25). config/assets.yaml already records the real
// planned phases (Jetty 1.5 = +100 kW AC, 2 = +300 kW, "target total 600kW AC")
// and nothing on the site answered what they actually buy: how much of the
// terminal's own 13.5 MW load each phase moves, and what the LAST kilowatt buys
// compared with the first.
//
// The marginal column is the point. A phase's total looks impressive next to
// nothing; its yield per added kWp is what says whether it is still a good deal.
//
// Two caveats the panel states rather than hides: CAPEX is still the documented
// ฿30,000/kWp placeholder (so payback is an estimate), and each phase's energy is
// scaled proportionally from today's array rather than simulated from a layout
// that doesn't exist yet for phase 2.
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useExpansion } from '../lib/queries'

function formatThb(value: number | null): string {
  if (value == null) return '—'
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)} ล้านบาท`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)} พันบาท`
  return `${value.toFixed(0)} บาท`
}

function formatEnergy(kwh: number | null): string {
  if (kwh == null) return '—'
  if (kwh >= 1_000_000) return `${(kwh / 1_000_000).toFixed(2)} GWh`
  return `${(kwh / 1_000).toFixed(1)} MWh`
}

export function ExpansionPlannerPanel() {
  const expansion = useExpansion()
  const data = expansion.data

  if (expansion.isLoading) {
    return (
      <section className="ems-panel" aria-label="Expansion planner">
        <h3 className="ems-panel-title">📈 แผนขยายกำลังผลิต (Expansion Planner)</h3>
        <p className="forecast-status">กำลังคำนวณแผนขยาย…</p>
      </section>
    )
  }

  if (!data || !data.available) {
    return (
      <section className="ems-panel" aria-label="Expansion planner">
        <h3 className="ems-panel-title">📈 แผนขยายกำลังผลิต (Expansion Planner)</h3>
        <p className="forecast-status forecast-status-caption">
          {data?.reason ?? 'ยังคำนวณแผนขยายไม่ได้ — ต้องมีข้อมูลเฟสขยายใน config/assets.yaml'}
        </p>
      </section>
    )
  }

  const chartData = data.scenarios.map((s) => ({
    label: s.label,
    offset: s.solar_offset_pct == null ? 0 : Number(s.solar_offset_pct.toFixed(3)),
    ac: s.ac_capacity_kw,
  }))
  const last = data.scenarios[data.scenarios.length - 1]

  return (
    <section className="ems-panel" aria-label="Expansion planner">
      <h3 className="ems-panel-title">📈 แผนขยายกำลังผลิต (Expansion Planner)</h3>

      <p className="ems-caption">
        แผนที่บันทึกไว้ใน assets.yaml จะพา AC จาก {data.scenarios[0].ac_capacity_kw.toFixed(0)} kW ไปที่{' '}
        {last.ac_capacity_kw.toFixed(0)} kW — ครอบคลุมโหลดของคลังได้{' '}
        <b>{last.solar_offset_pct == null ? '—' : `${last.solar_offset_pct.toFixed(2)}%`}</b>
        {data.facility_load_kw ? ` (โหลดคลังเฉลี่ย ${(data.facility_load_kw / 1000).toFixed(1)} MW)` : ''}
      </p>

      <div className="verify-table-scroll">
        <table className="verify-table">
          <caption>แต่ละแถวคือสถานะรวมหลังจบเฟสนั้น · คอลัมน์ &ldquo;เฉพาะเฟสนี้&rdquo; คือส่วนที่เฟสนั้นเพิ่มเข้ามาเอง</caption>
          <thead>
            <tr>
              <th scope="col">สถานะ</th>
              <th scope="col">AC (kW)</th>
              <th scope="col">DC (kWp)</th>
              <th scope="col">พลังงาน/ปี</th>
              <th scope="col">ครอบคลุมโหลด</th>
              <th scope="col">ประหยัดค่าไฟ/ปี</th>
              <th scope="col">เฉพาะเฟสนี้: พลังงาน</th>
              <th scope="col">เฉพาะเฟสนี้: kWh/kWp</th>
              <th scope="col">เงินลงทุน (ประมาณ)</th>
              <th scope="col">คืนทุน (ปี, ประมาณ)</th>
            </tr>
          </thead>
          <tbody>
            {data.scenarios.map((s) => (
              <tr key={s.label}>
                <th scope="row">{s.label}</th>
                <td>{s.ac_capacity_kw.toFixed(0)}</td>
                <td>{s.dc_capacity_kwp.toFixed(1)}</td>
                <td>{formatEnergy(s.annual_energy_kwh)}</td>
                <td>{s.solar_offset_pct == null ? '—' : `${s.solar_offset_pct.toFixed(2)}%`}</td>
                <td>{formatThb(s.annual_bill_saving_thb)}</td>
                <td>{formatEnergy(s.marginal_annual_energy_kwh)}</td>
                <td>{s.marginal_energy_per_kwp == null ? '—' : s.marginal_energy_per_kwp.toFixed(0)}</td>
                <td>{formatThb(s.capex_estimate_thb)}</td>
                <td>{s.simple_payback_years == null ? '—' : s.simple_payback_years.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="expansion-chart" style={{ width: '100%', height: 200 }}>
        <ResponsiveContainer>
          <BarChart data={chartData} margin={{ top: 18, right: 12, left: 0, bottom: 4 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 12 }} />
            <YAxis unit="%" tick={{ fontSize: 11 }} width={54} />
            <Tooltip formatter={(value) => [typeof value === 'number' ? `${value.toFixed(3)}%` : String(value), 'ครอบคลุมโหลด']} />
            <Bar dataKey="offset" name="ครอบคลุมโหลด" fill="var(--chart-salt)" radius={[4, 4, 0, 0]}>
              <LabelList
                dataKey="offset"
                position="top"
                fontSize={11}
                formatter={(value) => (typeof value === 'number' ? `${value.toFixed(2)}%` : String(value ?? ''))}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {data.targets.length > 0 && (
        <>
          <h4 className="health-subtitle">ถ้าต้องการครอบคลุมโหลดให้ได้จริงจัง ต้องใหญ่แค่ไหน</h4>
          <div className="verify-table-scroll">
            <table className="verify-table">
              <caption>คำนวณจากผลผลิตต่อ kWp ของอาร์เรย์ปัจจุบัน — เพื่อให้เห็นสเกลที่แท้จริงของโหลดระดับ MW</caption>
              <thead>
                <tr>
                  <th scope="col">เป้าหมายครอบคลุมโหลด</th>
                  <th scope="col">ต้องมี DC (kWp)</th>
                  <th scope="col">เทียบของปัจจุบัน</th>
                </tr>
              </thead>
              <tbody>
                {data.targets.map((t) => (
                  <tr key={t.target_offset_pct}>
                    <th scope="row">{t.target_offset_pct.toFixed(0)}%</th>
                    <td>{t.required_dc_capacity_kwp.toFixed(0)}</td>
                    <td>{t.times_current_capacity.toFixed(1)}×</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <p className="ems-caption">
        ⚠️ {data.capex_note}
        {data.implied_tariff_thb_per_kwh != null && (
          <>
            {' '}ค่าไฟที่ใช้คำนวณคือ <b>{data.implied_tariff_thb_per_kwh.toFixed(2)} บาท/kWh</b> ซึ่งได้จากค่าไฟจริงต่อปีหารด้วยหน่วยที่ใช้จริง
            ของคลัง (ไม่ใช่ค่า tariff สมมติในโมดูล Financial)
          </>
        )}
      </p>
      <p className="ems-caption">{data.method_note}</p>
    </section>
  )
}
