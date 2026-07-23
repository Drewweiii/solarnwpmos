// "About this facility" card (2026-07-23) - gives viewers the context that the
// solar array sits on PTT LNG's Nong Fab receiving terminal (officially "Map Ta
// Phut LNG Terminal 2"), Thailand's 2nd onshore LNG import terminal. Every
// figure is PUBLIC information from the cited sources (config/assets.yaml's
// site.lng_terminal, researched 2026-07-23) - NOT measured by this project and
// NOT the solar plant's own numbers - so the card labels it as such and links
// the sources rather than presenting it as first-party data. Superlative claims
// ("world's longest", "largest in Thailand") are shown as attributed claims,
// not stated as bare fact.
import { useState } from 'react'
import type { LngTerminal } from '../lib/types'

export interface FacilityInfoCardProps {
  terminal: LngTerminal | null | undefined
}

function fmtInt(n: number | null | undefined): string {
  return n == null ? '—' : n.toLocaleString('en-US')
}

interface Stat {
  label: string
  value: string
}

interface Section {
  title: string
  stats: Stat[]
}

function buildSections(t: LngTerminal): Section[] {
  const sections: Section[] = []

  const overview: Stat[] = []
  if (t.also_known_as) overview.push({ label: 'ชื่อเดิม / รหัส', value: t.also_known_as })
  if (t.owner) overview.push({ label: 'เจ้าของ (Owner)', value: t.owner })
  if (t.epc_contractors) overview.push({ label: 'ผู้ก่อสร้าง (EPC)', value: t.epc_contractors })
  if (t.owners_engineer) overview.push({ label: "Owner's Engineer", value: t.owners_engineer })
  if (t.location) overview.push({ label: 'ที่ตั้ง (Location)', value: t.location })
  if (overview.length) sections.push({ title: 'ภาพรวม (Overview)', stats: overview })

  const capacity: Stat[] = []
  if (t.regas_capacity_mmtpa != null) {
    capacity.push({
      label: 'กำลังแปลงก๊าซ (Regasification)',
      value: `${t.regas_capacity_mmtpa} MMTPA${t.peak_capacity_mmtpa != null ? ` (พีค ${t.peak_capacity_mmtpa})` : ''}`,
    })
  }
  if (t.storage_tank_count != null) {
    capacity.push({
      label: 'ถังเก็บ LNG (Storage)',
      value: `${t.storage_tank_count} ถัง × ${fmtInt(t.storage_tank_capacity_m3)} m³${t.storage_tank_type ? ` (${t.storage_tank_type})` : ''}`,
    })
  }
  if (t.storage_claim) capacity.push({ label: 'จุดเด่นถังเก็บ', value: t.storage_claim })
  if (capacity.length) sections.push({ title: 'กำลังผลิต & การจัดเก็บ (Capacity & Storage)', stats: capacity })

  const marine: Stat[] = []
  if (t.jetty_length_km_public != null) {
    marine.push({
      label: 'ท่าเรือ (Jetty)',
      value: `~${t.jetty_length_km_public} กม.${t.jetty_length_km_user_stated != null ? ` (ผู้ใช้ระบุ ${t.jetty_length_km_user_stated})` : ''}`,
    })
  }
  if (t.trestle_length_km != null) marine.push({ label: 'Trestle unloading', value: `${t.trestle_length_km} กม.` })
  if (t.jetty_claim) marine.push({ label: 'จุดเด่นท่าเรือ', value: t.jetty_claim })
  if (t.lng_carrier_min_m3 != null && t.lng_carrier_max_m3 != null) {
    marine.push({ label: 'รับเรือ LNG (Carriers)', value: `${fmtInt(t.lng_carrier_min_m3)}–${fmtInt(t.lng_carrier_max_m3)} m³` })
  }
  if (marine.length) sections.push({ title: 'ท่าเรือ & การรับเรือ (Marine / Jetty)', stats: marine })

  const project: Stat[] = []
  if (t.contract_awarded_year != null) project.push({ label: 'เซ็นสัญญา EPC', value: String(t.contract_awarded_year) })
  if (t.investment_cost_billion_thb != null) project.push({ label: 'มูลค่าโครงการ', value: `~${t.investment_cost_billion_thb} พันล้านบาท` })
  if (t.epc_contract_value_musd != null) project.push({ label: 'มูลค่าสัญญา EPC', value: `~${fmtInt(t.epc_contract_value_musd)} ล้าน USD` })
  if (t.operational_since_year != null) project.push({ label: 'เริ่มดำเนินการ', value: String(t.operational_since_year) })
  if (t.first_cargo_date) {
    project.push({
      label: 'เรือลำแรก (First cargo)',
      value: [t.first_cargo_date, t.first_cargo_carrier, t.first_cargo_origin].filter(Boolean).join(' · '),
    })
  }
  if (project.length) sections.push({ title: 'โครงการ & การลงทุน (Project & Investment)', stats: project })

  const land: Stat[] = []
  if (t.land_area_total_ha != null) land.push({ label: 'พื้นที่รวม (Total)', value: `${t.land_area_total_ha} เฮกตาร์` })
  if (t.land_area_terminal_ha != null) land.push({ label: 'โซนคลัง (Terminal)', value: `${t.land_area_terminal_ha} เฮกตาร์` })
  if (t.land_area_office_ha != null) land.push({ label: 'โซนสำนักงาน (Office)', value: `${t.land_area_office_ha} เฮกตาร์` })
  if (land.length) sections.push({ title: 'การใช้ที่ดิน (Land use)', stats: land })

  const green: Stat[] = []
  if (t.cold_energy_reuse) green.push({ label: 'Cold-energy recovery', value: 'นำความเย็น LNG กลับมาเดินระบบ HVAC อาคาร' })
  if (t.seawater_recycling) green.push({ label: 'Seawater recycling', value: 'รีไซเคิลน้ำทะเลผ่านอุโมงค์ใต้น้ำ' })
  if (t.landscape_award) green.push({ label: 'รางวัล (Award)', value: t.landscape_award })
  if (green.length) sections.push({ title: '♻️ ความยั่งยืน (Sustainability)', stats: green })

  return sections
}

export function FacilityInfoCard({ terminal }: FacilityInfoCardProps) {
  const [open, setOpen] = useState(false)
  if (!terminal) return null
  const sections = buildSections(terminal)

  return (
    <section className="facility-info-card">
      <button type="button" className="facility-info-toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="facility-info-title">🏭 เกี่ยวกับคลัง LNG ที่ตั้งโซลาร์ (About this facility)</span>
        <span className="facility-info-chevron" aria-hidden="true">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="facility-info-body">
          <p className="facility-info-name">
            {terminal.official_name}
            {terminal.is_thailand_second_onshore_terminal && (
              <span className="facility-info-badge">คลัง LNG บนบกแห่งที่ 2 ของไทย</span>
            )}
          </p>

          {sections.map((section) => (
            <div className="facility-info-section" key={section.title}>
              <h4 className="facility-info-section-title">{section.title}</h4>
              <dl className="facility-info-grid">
                {section.stats.map((s) => (
                  <div className="facility-info-stat" key={s.label}>
                    <dt>{s.label}</dt>
                    <dd>{s.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}

          <p className="facility-info-disclaimer">
            ข้อมูลข้างต้นเป็นข้อมูลสาธารณะของตัวคลัง LNG (Terminal 2 / Nong Fab เท่านั้น — ไม่รวม Terminal 1) ไม่ใช่ตัวเลขของระบบโซลาร์
            และไม่ได้วัดเองในโปรเจกต์นี้ — คำกล่าว "ยาว/ใหญ่ที่สุด" เป็นการอ้างอิงตามแหล่งข่าว (เช่น Saipem)
            {terminal.sources.length > 0 && ' — แหล่งอ้างอิง: '}
            {terminal.sources.map((url, i) => (
              <span key={url}>
                {i > 0 && ', '}
                <a href={url} target="_blank" rel="noreferrer noopener">
                  [{i + 1}]
                </a>
              </span>
            ))}
          </p>
        </div>
      )}
    </section>
  )
}
