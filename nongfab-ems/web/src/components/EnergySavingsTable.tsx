import { useState } from 'react'
import { useSavingsSummary } from '../lib/queries'
import type { SavingsMetrics, ZoneSavings } from '../lib/types'
import './EnergySavingsTable.css'

/** Energy Report bottom table: how much the solar saves (in kWh and baht),
 * how much CO2 it avoids, and how much carbon credit it earns - per zone
 * (ISB / GIS / Jetty) plus a combined "all three" tab, and per horizon
 * (1 day / 1 month / 1 year / 25-year lifetime). Numbers come straight from
 * GET /savings/summary (see api/src/nongfab_api/green_savings.py for the real
 * reference-document sources of every rate/factor). Requested 2026-07-19. */

const HORIZONS: { key: keyof ZoneSavings['periods']; label: string; sub: string }[] = [
  { key: 'day', label: '1 วัน', sub: 'อัปเดตตามฤดู' },
  { key: 'month', label: '1 เดือน', sub: 'อัปเดตตามฤดู' },
  { key: 'year', label: '1 ปี', sub: 'ประมาณการ' },
  { key: 'lifetime', label: '25 ปี', sub: 'ตลอดโครงการ' },
]

const nf0 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 1 })
const nf2 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 2 })

/** kWh -> kWh / MWh / GWh so the 25-year column isn't an unreadable 18-digit run. */
function energy(kwh: number): string {
  if (kwh >= 1_000_000) return `${nf2.format(kwh / 1_000_000)} GWh`
  if (kwh >= 1_000) return `${nf1.format(kwh / 1_000)} MWh`
  return `${nf0.format(kwh)} kWh`
}

/** baht, compacted to ล้าน/พันล้าน for the long horizons. */
function baht(thb: number): string {
  if (thb >= 1_000_000_000) return `${nf2.format(thb / 1_000_000_000)} พันล้านบาท`
  if (thb >= 1_000_000) return `${nf2.format(thb / 1_000_000)} ล้านบาท`
  return `${nf0.format(thb)} บาท`
}

/** kgCO2 -> kg / ตัน. */
function co2(kg: number): string {
  if (kg >= 1_000) return `${nf1.format(kg / 1_000)} ตัน`
  return `${nf0.format(kg)} kg`
}

type CellFn = (m: SavingsMetrics) => string

interface Row {
  label: string
  hint?: string
  cell: CellFn
  strong?: boolean
  group?: string
}

const ROWS: Row[] = [
  { label: '⚡ พลังงานที่ผลิต', cell: (m) => energy(m.energy_kwh), strong: true },
  { label: '💰 ลดค่าไฟ (อัตราปกติ)', hint: 'TOU Peak HV', cell: (m) => baht(m.bill_saving_thb), strong: true },
  { label: '🟢 ลดการซื้อ UGT1', hint: 'หน่วย', cell: (m) => energy(m.ugt1_units_kwh), group: 'ugt1' },
  { label: '🟢 ลดการซื้อ UGT1', hint: 'บาท', cell: (m) => baht(m.ugt1_saving_thb), group: 'ugt1' },
  { label: '🟩 ลดการซื้อ UGT2', hint: 'หน่วย', cell: (m) => energy(m.ugt2_units_kwh), group: 'ugt2' },
  { label: '🟩 ลดการซื้อ UGT2', hint: 'บาท', cell: (m) => baht(m.ugt2_saving_thb), group: 'ugt2' },
  { label: '🌱 คาร์บอนเครดิต', hint: 'ตัน CO₂eq', cell: (m) => `${nf2.format(m.carbon_credit_units)} ตัน`, strong: true },
  { label: '🌱 มูลค่าคาร์บอนเครดิต', hint: '@100 บาท/ตัน', cell: (m) => baht(m.carbon_credit_value_thb) },
  { label: '🌳 เทียบเท่าต้นไม้', hint: 'ต้น', cell: (m) => `${nf0.format(m.trees_equivalent)} ต้น` },
  { label: '🏭 ลด CO₂ แฝง (scope 2)', hint: 'จากกริด', cell: (m) => co2(m.scope2_co2_avoided_kg), strong: true },
]

export function EnergySavingsTable() {
  const savings = useSavingsSummary()
  const [activeZone, setActiveZone] = useState<string>('combined')

  if (savings.isLoading) return <p className="forecast-status">กำลังโหลดตารางผลประหยัด…</p>
  if (savings.error || !savings.data) {
    return <p className="forecast-status forecast-status-warn">โหลดตารางผลประหยัดไม่สำเร็จ</p>
  }

  const zones = savings.data.zones
  const zone = zones.find((z) => z.zone === activeZone) ?? zones[zones.length - 1]
  const a = savings.data.assumptions

  return (
    <div className="savings-table-wrap">
      <div className="savings-tabs" role="tablist" aria-label="เลือกกลุ่ม">
        {zones.map((z) => (
          <button
            key={z.zone}
            type="button"
            role="tab"
            aria-selected={z.zone === zone.zone}
            className={`savings-tab${z.zone === zone.zone ? ' savings-tab-active' : ''}${
              z.zone === 'combined' ? ' savings-tab-combined' : ''
            }`}
            onClick={() => setActiveZone(z.zone)}
          >
            {z.zone === 'combined' ? 'รวม 3 กลุ่ม' : z.zone}
            <span className="savings-tab-kwp">{nf1.format(z.dc_capacity_kwp)} kWp</span>
          </button>
        ))}
      </div>

      <p className="savings-zone-caption">
        {zone.label}
        {zone.simulated && <span className="savings-sim-badge">ยังไม่ติดตั้งจริง (ประมาณการ)</span>}
      </p>

      <div className="savings-table-scroll">
        <table className="savings-table">
          <thead>
            <tr>
              <th className="savings-metric-col">รายการ</th>
              {HORIZONS.map((h) => (
                <th key={h.key}>
                  {h.label}
                  <span className="savings-th-sub">{h.sub}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row, i) => (
              <tr key={i} className={`${row.strong ? 'savings-row-strong' : ''} ${row.group ? `savings-row-${row.group}` : ''}`.trim()}>
                <th scope="row" className="savings-metric-col">
                  {row.label}
                  {row.hint && <span className="savings-row-hint">{row.hint}</span>}
                </th>
                {HORIZONS.map((h) => (
                  <td key={h.key}>{row.cell(zone.periods[h.key])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <details className="savings-assumptions">
        <summary>สมมติฐานและแหล่งอ้างอิง</summary>
        <ul>
          <li>
            อัตราค่าไฟปกติ: <strong>{a.normal_tariff}</strong> = {nf2.format(Number(a.normal_rate_thb_per_kwh))} บาท/หน่วย
            (แรงดัน {a.voltage_level})
          </li>
          <li>
            UGT1 = ค่าไฟปกติ + ส่วนเพิ่ม {nf2.format(Number(a.ugt1_premium_thb_per_kwh))} ={' '}
            {nf2.format(Number(a.ugt1_rate_thb_per_kwh))} บาท/หน่วย · UGT2 ({a.ugt2_portfolio}) ={' '}
            {nf2.format(Number(a.ugt2_rate_thb_per_kwh))} บาท/หน่วย
          </li>
          <li>
            EF scope 2 (กริดไทย TGO) = {a.ef_scope2_kg_per_kwh} kgCO₂/kWh · คาร์บอนเครดิต{' '}
            {a.carbon_credit_unit_per_kwp_year} ตัน/kWp/ปี ({a.trees_per_kwp_year} ต้น/kWp/ปี) · ราคากลาง{' '}
            {a.carbon_price_thb_per_tonne} บาท/ตัน
          </li>
          <li className="savings-assumptions-note">
            คาร์บอนเครดิตคิดแบบต่อกำลังติดตั้ง (rule of thumb) ส่วน “ลด CO₂ แฝง” คิดจากพลังงานจริง × EF · 1 ปี/25 ปี
            เป็นการประมาณการตามฤดูกาล + การเสื่อมของแผงตาม datasheet · ยังไม่มีข้อมูลผลิตจริงสะสม
          </li>
        </ul>
      </details>
    </div>
  )
}
