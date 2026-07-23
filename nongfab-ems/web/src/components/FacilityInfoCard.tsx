// "About this facility" card (2026-07-23) - gives viewers the context that the
// solar array sits on PTT LNG's Nong Fab receiving terminal (officially "Map Ta
// Phut LNG Terminal 2"), Thailand's 2nd onshore LNG import terminal. Every
// figure is PUBLIC information from the cited sources (config/assets.yaml's
// site.lng_terminal, researched 2026-07-23) - NOT measured by this project and
// NOT the solar plant's own numbers - so the card labels it as such and links
// the sources rather than presenting it as first-party data.
import { useState } from 'react'
import type { LngTerminal } from '../lib/types'

export interface FacilityInfoCardProps {
  terminal: LngTerminal | null | undefined
}

function fmtInt(n: number | null | undefined): string {
  return n == null ? '—' : n.toLocaleString('en-US')
}

export function FacilityInfoCard({ terminal }: FacilityInfoCardProps) {
  const [open, setOpen] = useState(false)
  if (!terminal) return null

  const stats: Array<{ label: string; value: string }> = [
    {
      label: 'กำลังแปลงก๊าซ (Regasification)',
      value:
        terminal.regas_capacity_mmtpa != null
          ? `${terminal.regas_capacity_mmtpa} MMTPA${terminal.peak_capacity_mmtpa != null ? ` (พีค ${terminal.peak_capacity_mmtpa})` : ''}`
          : '—',
    },
    {
      label: 'ถังเก็บ LNG (Storage)',
      value:
        terminal.storage_tank_count != null
          ? `${terminal.storage_tank_count} ถัง × ${fmtInt(terminal.storage_tank_capacity_m3)} m³${terminal.storage_tank_type ? ` (${terminal.storage_tank_type})` : ''}`
          : '—',
    },
    {
      label: 'ท่าเรือ (Jetty)',
      value:
        terminal.jetty_length_km_public != null
          ? `~${terminal.jetty_length_km_public} กม.${terminal.jetty_length_km_user_stated != null ? ` (ผู้ใช้ระบุ ${terminal.jetty_length_km_user_stated})` : ''}`
          : '—',
    },
    {
      label: 'รับเรือ LNG (Carriers)',
      value:
        terminal.lng_carrier_min_m3 != null && terminal.lng_carrier_max_m3 != null
          ? `${fmtInt(terminal.lng_carrier_min_m3)}–${fmtInt(terminal.lng_carrier_max_m3)} m³`
          : '—',
    },
    { label: 'เริ่มดำเนินการ (Operational)', value: terminal.operational_since_year != null ? String(terminal.operational_since_year) : '—' },
    { label: 'เจ้าของ / ผู้ก่อสร้าง', value: [terminal.owner, terminal.epc_contractors].filter(Boolean).join(' · ') || '—' },
  ]

  const green: string[] = []
  if (terminal.cold_energy_reuse) green.push('นำความเย็น LNG กลับมาเดินระบบ HVAC อาคาร')
  if (terminal.seawater_recycling) green.push('รีไซเคิลน้ำทะเลผ่านอุโมงค์ใต้น้ำ')

  return (
    <section className="facility-info-card">
      <button
        type="button"
        className="facility-info-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="facility-info-title">🏭 เกี่ยวกับคลัง LNG ที่ตั้งโซลาร์ (About this facility)</span>
        <span className="facility-info-chevron" aria-hidden="true">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="facility-info-body">
          <p className="facility-info-name">{terminal.official_name}</p>
          <dl className="facility-info-grid">
            {stats.map((s) => (
              <div className="facility-info-stat" key={s.label}>
                <dt>{s.label}</dt>
                <dd>{s.value}</dd>
              </div>
            ))}
          </dl>

          {green.length > 0 && (
            <p className="facility-info-green">♻️ ความยั่งยืน: {green.join(' · ')}</p>
          )}

          <p className="facility-info-disclaimer">
            ข้อมูลข้างต้นเป็นข้อมูลสาธารณะของตัวคลัง LNG (ไม่ใช่ตัวเลขของระบบโซลาร์ และไม่ได้วัดเองในโปรเจกต์นี้)
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
