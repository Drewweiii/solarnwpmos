// Energy Management panel (2026-07-23) - the EMS headline view the user asked to
// emphasize. Three parts, all built from data the Energy Report already returns
// (no new fetch). The facility-load offset uses config/assets.yaml
// site.facility_electrical_load_kw, a REAL user-stated figure (13.5 MW) - only
// its flat shape is an approximation, and the caption says so:
//   1. KPI strip: annual energy, PR, specific yield, capacity factor, CO2.
//   2. Solar-vs-facility-load offset gauge.
//   3. Energy accounting roll-up (day/month/year kWh) tied to the PPA code.
import type { EnergyReportResponse } from '../lib/types'
import {
  buildEnergyKpis,
  formatEnergy,
  formatThb,
  solarBillSavingPct,
  solarBillSavingThbPerYear,
  solarOffsetPct,
} from '../lib/energyManagement'

export interface EnergyManagementPanelProps {
  report: EnergyReportResponse
  facilityLoadKw: number | null | undefined
  facilityAnnualCostThb?: number | null
  ppaCode?: string
}

// The Energy Report only carries annual + monthly energy, so derive the
// day/month roll-up from the annual figure (an even split) rather than invent
// separate numbers - honest about being a breakdown of the same annual total.
function accountingRows(report: EnergyReportResponse): Array<{ label: string; value: string }> {
  const annual = report.annual.ac_energy_kwh
  // Prefer the real month-by-month estimates when present (they already vary by
  // rainy season); fall back to a flat 1/12 only if monthly is empty.
  const monthlyAvg =
    report.monthly.length > 0
      ? report.monthly.reduce((s, m) => s + m.ac_energy_kwh, 0) / report.monthly.length
      : annual / 12
  return [
    { label: 'ต่อวัน (เฉลี่ย)', value: formatEnergy(annual / 365) },
    { label: 'ต่อเดือน (เฉลี่ย)', value: formatEnergy(monthlyAvg) },
    { label: 'ต่อปี', value: formatEnergy(annual) },
  ]
}

export function EnergyManagementPanel({ report, facilityLoadKw, facilityAnnualCostThb, ppaCode }: EnergyManagementPanelProps) {
  const kpis = buildEnergyKpis({
    annualAcEnergyKwh: report.annual.ac_energy_kwh,
    acCapacityKw: report.system_summary.ac_capacity_kw,
    performanceRatio: report.annual.performance_ratio,
    specificYieldKwhPerKwp: report.annual.specific_yield_kwh_per_kwp,
    co2SavedKgPerYear: report.co2_saved_kg_per_year,
  })
  const offsetPct = solarOffsetPct(report.annual.ac_energy_kwh, facilityLoadKw)
  const billSaving = solarBillSavingThbPerYear(report.annual.ac_energy_kwh, facilityAnnualCostThb, facilityLoadKw)
  const billSavingPct = solarBillSavingPct(report.annual.ac_energy_kwh, facilityAnnualCostThb, facilityLoadKw)
  const rows = accountingRows(report)

  return (
    <section className="ems-panel" aria-label="Energy management">
      <h3 className="ems-panel-title">⚡ Energy Management</h3>

      {/* 1. KPI strip */}
      <div className="ems-kpi-grid">
        {kpis.map((k) => (
          <div className="ems-kpi" key={k.key}>
            <span className="ems-kpi-label">{k.label}</span>
            <span className="ems-kpi-value">{k.value}</span>
            {k.hint && <span className="ems-kpi-hint">{k.hint}</span>}
          </div>
        ))}
      </div>

      {/* 2. Solar offset of facility load */}
      <div className="ems-offset">
        <div className="ems-offset-head">
          <span className="ems-offset-label">โซลาร์ครอบคลุมโหลดไฟฟ้าของคลัง (Solar offset of facility load)</span>
          <span className="ems-offset-value">{offsetPct == null ? '—' : `${offsetPct.toFixed(offsetPct < 1 ? 2 : 1)}%`}</span>
        </div>
        {offsetPct != null && (
          <div className="ems-offset-bar" role="img" aria-label={`Solar offsets about ${offsetPct.toFixed(2)} percent of facility load`}>
            <div className="ems-offset-bar-fill" style={{ width: `${Math.max(0.5, Math.min(100, offsetPct))}%` }} />
          </div>
        )}
        <p className="ems-caption">
          {facilityLoadKw == null
            ? 'ยังไม่มีค่าโหลดไฟฟ้าของคลัง — ใส่ค่าจริงเพื่อคำนวณสัดส่วนนี้'
            : `เทียบกับโหลดไฟฟ้าเฉลี่ยของคลัง ~${(facilityLoadKw / 1000).toFixed(1)} MW (เฉลี่ยรายวัน 13–14 MW, ข้อมูลผู้ใช้)`}
        </p>
      </div>

      {/* Solar bill saving vs the facility's real annual electricity cost */}
      {billSaving != null && facilityAnnualCostThb != null && (
        <div className="ems-billsave">
          <div className="ems-offset-head">
            <span className="ems-offset-label">โซลาร์ช่วยประหยัดค่าไฟคลัง (Bill saving)</span>
            <span className="ems-offset-value">
              ~{formatThb(billSaving)}/ปี{billSavingPct != null && ` (${billSavingPct.toFixed(billSavingPct < 1 ? 2 : 1)}%)`}
            </span>
          </div>
          <p className="ems-caption">
            คิดจากพลังงานโซลาร์ต่อปี × ค่าไฟเฉลี่ยของคลังเอง (~{(facilityAnnualCostThb / 1_000_000).toFixed(0)} ล้านบาท/ปี ÷ พลังงานที่คลังใช้ ≈{' '}
            {((facilityAnnualCostThb / (facilityLoadKw! * 8760))).toFixed(2)} บาท/kWh) — ประมาณการจากตัวเลขจริงที่ผู้ใช้ให้มา
          </p>
        </div>
      )}

      {/* 3. Energy accounting */}
      <div className="ems-accounting">
        <div className="ems-accounting-head">
          <span>บัญชีพลังงานที่ผลิต (Energy delivered)</span>
          {ppaCode && <span className="ems-ppa">PPA: {ppaCode}</span>}
        </div>
        <dl className="ems-accounting-grid">
          {rows.map((r) => (
            <div className="ems-accounting-row" key={r.label}>
              <dt>{r.label}</dt>
              <dd>{r.value}</dd>
            </div>
          ))}
        </dl>
        <p className="ems-caption">
          ประมาณการจากพลังงานรายปี (แยกรายเดือนตามฤดูฝน/แล้งจากโมเดลจำลอง) — ดูรายละเอียดต่อเดือนในกราฟด้านล่าง
        </p>
      </div>
    </section>
  )
}
