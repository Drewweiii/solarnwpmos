import { useEffect, useRef, useState } from 'react'
import { useProvenanceMany } from '../lib/queries'
import './PrintReport.css'

/** Print the page as a report, with every figure's origin attached (project Q,
 * 2026-07-26).
 *
 * The button is ordinary. The appendix is the point.
 *
 * A printed dashboard normally loses the one thing this project spends its
 * effort on: on screen a reader can click ⓘ and find out that the payback
 * figure rests on a placeholder CAPEX, and on paper that context is gone and
 * the number reads as fact. So the printed version carries a provenance
 * appendix - each published figure on the page, the chain behind it, and the
 * weakest link in that chain - generated from the same `/provenance` registry
 * the ⓘ popovers read, not from anything transcribed into a template.
 *
 * The appendix does not exist on screen and does not fetch until somebody asks
 * to print. Clicking the button mounts it, waits for the chains to arrive, and
 * only then calls `window.print()` - printing while the requests were still in
 * flight would produce a report whose appendix said "loading".
 */

const ORIGIN_ORDER: Record<string, number> = {
  placeholder: 0,
  tuning: 1,
  literature: 2,
  derived: 3,
  'measured-feed': 4,
  'as-built': 5,
  confirmed: 6,
}

const ICT_DATE = new Intl.DateTimeFormat('th-TH', {
  dateStyle: 'long',
  timeStyle: 'short',
  timeZone: 'Asia/Bangkok',
})

interface Props {
  /** Provenance keys for the figures this page publishes. Passed explicitly
   * rather than inferred: a page knows what it shows, and a wrong key fails
   * loudly as a 404 in the appendix instead of quietly omitting a figure. */
  valueKeys: string[]
  /** Printed at the top of the paper version. */
  title: string
  subtitle?: string
  /** Injectable so the cover-block test does not depend on the wall clock. */
  nowIso?: string
}

export function PrintReport({ valueKeys, title, subtitle, nowIso }: Props) {
  const [wanted, setWanted] = useState(false)
  const results = useProvenanceMany(valueKeys, wanted)
  const printed = useRef(false)

  const settled = wanted && results.length > 0 && results.every((r) => !r.isPending)

  useEffect(() => {
    if (!settled || printed.current) return
    printed.current = true
    // One frame so React has committed the appendix into the DOM before the
    // print dialog snapshots the page.
    const id = requestAnimationFrame(() => window.print())
    return () => cancelAnimationFrame(id)
  }, [settled])

  const chains = results.map((r) => r.data).filter((d) => d != null)
  const failed = results.filter((r) => r.isError).length
  const stamp = nowIso ? new Date(nowIso) : new Date()

  return (
    <>
      <button
        type="button"
        className="print-report-button print-hide"
        onClick={() => {
          printed.current = false
          setWanted(true)
        }}
      >
        🖨️ พิมพ์ / บันทึกเป็น PDF
      </button>
      {wanted && !settled && (
        <span className="print-report-status print-hide">กำลังรวบรวมที่มาของตัวเลขก่อนพิมพ์ …</span>
      )}

      {/* Cover block: only on paper, where there is no header bar to say what
          this document is or when it was produced. */}
      <div className="print-only print-cover">
        <h1 className="print-cover-title">{title}</h1>
        {subtitle && <p className="print-cover-subtitle">{subtitle}</p>}
        <p className="print-cover-meta">
          PTT LNG Terminal 2 (หนองแฟบ) · ระบบผลิตไฟฟ้าจากแสงอาทิตย์ 429 kWp
          <br />
          พิมพ์เมื่อ {ICT_DATE.format(stamp)} น. (เวลาไทย)
        </p>
      </div>

      {wanted && chains.length > 0 && (
        <section className="print-only print-appendix" aria-label="ภาคผนวก: ที่มาของตัวเลข">
          <h2 className="print-appendix-heading">ภาคผนวก — ที่มาของตัวเลขในรายงานนี้</h2>
          <p className="print-appendix-intro">
            ทุกตัวเลขที่เผยแพร่ในรายงานนี้ตามรอยกลับไปหาที่มาได้
            ระดับความน่าเชื่อถือที่ระบุคือ <strong>ขั้นที่อ่อนที่สุดในสาย</strong> ไม่ใช่ค่าเฉลี่ย —
            ตัวเลขจะแข็งแรงได้แค่เท่ากับข้อมูลที่อ่อนที่สุดที่มันใช้
          </p>

          {[...chains]
            // Weakest first: a reader skimming the appendix should meet the
            // figures that need the most caution before the solid ones.
            .sort((a, b) => (ORIGIN_ORDER[a.weakest_origin ?? ''] ?? 9) - (ORIGIN_ORDER[b.weakest_origin ?? ''] ?? 9))
            .map((chain) => (
              <div key={chain.key} className="prov-appendix-entry">
                <h3 className="print-appendix-label">
                  {chain.label}
                  {chain.unit && <span className="print-appendix-unit"> ({chain.unit})</span>}
                </h3>
                <p className="print-appendix-weakest">
                  ขั้นที่อ่อนที่สุด: <strong>{chain.weakest_origin_label || '—'}</strong>
                </p>
                <ol className="print-appendix-steps">
                  {chain.steps.map((step, i) => (
                    <li key={`${step.kind}-${step.setting_key ?? i}`}>
                      <strong>{step.label}</strong>
                      {step.origin_label && <span className="print-appendix-origin"> [{step.origin_label}]</span>}
                      <br />
                      {step.detail}
                      {step.setting_key && (
                        <>
                          <br />
                          <code>{step.setting_key}</code>
                          {step.default_value !== null && ` = ${step.default_value} ${step.unit}`}
                        </>
                      )}
                    </li>
                  ))}
                </ol>
                <p className="print-appendix-caveat">ข้อควรระวัง: {chain.caveat}</p>
              </div>
            ))}

          {/* An appendix that silently dropped a figure would be worse than no
              appendix - the reader would have no way to know it was incomplete. */}
          {failed > 0 && (
            <p className="print-appendix-caveat">
              หมายเหตุ: ดึงที่มาของตัวเลขไม่สำเร็จ {failed} รายการ ภาคผนวกนี้จึงยังไม่ครบทุกตัวเลขในรายงาน
            </p>
          )}
        </section>
      )}
    </>
  )
}
