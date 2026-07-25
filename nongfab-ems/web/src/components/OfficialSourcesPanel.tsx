import { useOfficialSources } from '../lib/queries'
import type { OfficialSourceItem } from '../lib/types'

/** "เพื่อความชัวร์" (2026-07-25): where the tariff and emission numbers on this
 * site actually came from, and whether EGAT / PEA / กกพ have published anything
 * new since they were transcribed.
 *
 * It lives on the settings page because that is where value provenance already
 * lives (`origin` badges) - this is the same idea taken outside the codebase,
 * to the agencies that issue the figures.
 *
 * It deliberately does NOT display a scraped rate. Thai tariff announcements
 * are scanned images and OCR reads Thai numerals wrongly and silently (see
 * api/official_sources.py for the evidence), so the honest product is: name the
 * document, link it, and shout when a new one appears.
 */

const STATUS_LABEL: Record<string, string> = {
  ok: 'ตรงกับที่บันทึกไว้',
  changed: 'มีประกาศใหม่ ควรตรวจสอบ',
  unreachable: 'เข้าเว็บหน่วยงานไม่ได้',
}

const STATUS_ICON: Record<string, string> = { ok: '🟢', changed: '🟠', unreachable: '⚪' }

function ictDateTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Bangkok' })
}

export function OfficialSourcesPanel() {
  const sources = useOfficialSources()

  if (sources.isLoading) return <p className="forecast-status">กำลังตรวจสอบแหล่งอ้างอิงทางการ…</p>
  if (sources.error || !sources.data) {
    return <p className="forecast-status forecast-status-warn">ตรวจสอบแหล่งอ้างอิงทางการไม่สำเร็จ</p>
  }

  const d = sources.data
  const changed = d.sources.filter((s) => s.status === 'changed')

  return (
    <section className="settings-sources" aria-label="แหล่งอ้างอิงทางการ">
      <h2>แหล่งอ้างอิงทางการ (กฟผ. · กฟภ. · กกพ. · PTT LNG)</h2>
      <p className="settings-note">{d.method_note}</p>

      {changed.length > 0 && (
        <p className="settings-sources-alert">
          ⚠️ มี {changed.length} หน่วยงานที่เผยแพร่เอกสารใหม่หลังจากวันที่บันทึกค่าไว้ ({d.baseline_captured}) —
          ควรเปิดอ่านประกาศล่าสุดแล้วตรวจว่าตัวเลขในเว็บยังถูกต้อง
        </p>
      )}

      <p className="settings-sources-checked">
        ตรวจสอบล่าสุด {ictDateTime(d.checked_at)} · เทียบกับรายการเอกสารที่บันทึกไว้เมื่อ {d.baseline_captured}
      </p>

      <div className="settings-sources-list">
        {d.sources.map((source) => (
          <SourceCard key={source.key} source={source} />
        ))}
      </div>
    </section>
  )
}

function SourceCard({ source }: { source: OfficialSourceItem }) {
  return (
    <article className={`settings-source settings-source-${source.status}`}>
      <header className="settings-source-head">
        <span className="settings-source-agency">{source.agency}</span>
        <span className="settings-source-status">
          {STATUS_ICON[source.status] ?? '⚪'} {STATUS_LABEL[source.status] ?? source.status}
        </span>
      </header>

      <p className="settings-source-full">{source.agency_full}</p>
      <p className="settings-source-purpose">{source.purpose}</p>

      {/* rel=noreferrer as well as noopener: these are external government
          sites and there is no reason to hand them this app's URL. */}
      <a className="settings-source-link" href={source.page_url} target="_blank" rel="noopener noreferrer">
        เปิดหน้าเว็บทางการ ↗
      </a>

      <p className="settings-source-detail">{source.detail}</p>

      {source.added.length > 0 && (
        <div className="settings-source-docs">
          <strong>เอกสารใหม่:</strong>
          <ul>
            {source.added.map((doc) => (
              <li key={doc}>{doc}</li>
            ))}
          </ul>
        </div>
      )}
      {source.removed.length > 0 && (
        <div className="settings-source-docs">
          <strong>เอกสารที่หายไป:</strong>
          <ul>
            {source.removed.map((doc) => (
              <li key={doc}>{doc}</li>
            ))}
          </ul>
        </div>
      )}

      {source.quoted.length > 0 && (
        <div className="settings-source-quoted">
          <strong>ค่าที่เว็บนี้อ้างอิงจากหน่วยงานนี้</strong>
          {source.quoted.map((q) => (
            <div key={q.label} className={`settings-source-value${q.note ? ' settings-source-value-flagged' : ''}`}>
              <span className="settings-source-value-label">{q.label}</span>
              <strong className="settings-source-value-number">{q.value}</strong>
              <code className="settings-source-value-where">{q.code_location}</code>
              {q.note && <p className="settings-source-value-note">{q.note}</p>}
            </div>
          ))}
        </div>
      )}
    </article>
  )
}
