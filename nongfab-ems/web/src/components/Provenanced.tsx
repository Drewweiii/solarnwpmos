import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useProvenance } from '../lib/queries'
import type { ProvenanceStep } from '../lib/types'
import './Provenanced.css'

/** Click a number, see where it came from (2026-07-26, project O).
 *
 * Wrap any published figure in this and it grows a small ⓘ that opens the
 * chain behind it: source → model → setting → computation, with each link's
 * origin, and the weakest link as the headline.
 *
 * WHY THE HEADLINE IS THE WEAKEST LINK. A figure is only as sound as its
 * shakiest input. Showing an average, or the best origin present, would let a
 * payback number that rests on a placeholder CAPEX read as "mostly confirmed",
 * which is the exact overclaim this site spends its effort avoiding.
 *
 * The chain is fetched lazily on first open, and the fetching hook lives in
 * `ProvenancePopover` rather than in `Provenanced` itself. That is deliberate:
 * a closed ⓘ then costs a wrapper's `useState` and nothing else - no query, no
 * auth context - so wrapping a number in one of these cannot change how the
 * host component behaves, or what its tests have to provide, until somebody
 * actually clicks.
 */

const KIND_ICON: Record<ProvenanceStep['kind'], string> = {
  source: '📡',
  model: '🧮',
  setting: '⚙️',
  computation: '∑',
}

const KIND_LABEL: Record<ProvenanceStep['kind'], string> = {
  source: 'แหล่งข้อมูล',
  model: 'โมเดล',
  setting: 'ค่าที่ตั้งไว้',
  computation: 'การคำนวณ',
}

const nfValue = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 4 })

function StepRow({ step }: { step: ProvenanceStep }) {
  return (
    <li className="prov-step">
      <span className="prov-step-icon" aria-hidden="true">
        {KIND_ICON[step.kind] ?? '•'}
      </span>
      <div className="prov-step-body">
        <div className="prov-step-head">
          <span className="prov-step-kind">{KIND_LABEL[step.kind] ?? step.kind}</span>
          {step.origin && (
            <span className={`prov-origin prov-origin-${step.origin}`}>{step.origin_label}</span>
          )}
        </div>
        <strong className="prov-step-label">{step.label}</strong>
        <p className="prov-step-detail">{step.detail}</p>
        {step.setting_key && (
          <p className="prov-step-registry">
            <code>{step.setting_key}</code>
            {step.default_value !== null && (
              <>
                {' = '}
                <span className="prov-step-value">
                  {nfValue.format(step.default_value)} {step.unit}
                </span>
              </>
            )}
            {/* The registry's own note, read live server-side - not a copy that
                would keep saying whatever it said the day it was written. */}
            {step.registry_note && <span className="prov-step-note"> — {step.registry_note}</span>}
          </p>
        )}
      </div>
    </li>
  )
}

function ProvenancePopover({ valueKey, onClose }: { valueKey: string; onClose: () => void }) {
  const { data, isLoading, isError } = useProvenance(valueKey, true)

  return (
    <div className="prov-popover" role="dialog" aria-label="ที่มาของตัวเลข">
      {isLoading && <p className="prov-status">กำลังตามรอยที่มา …</p>}
      {isError && <p className="prov-status">ยังดึงที่มาของตัวเลขนี้ไม่ได้ในขณะนี้</p>}
      {data && (
        <>
          <div className="prov-header">
            <strong className="prov-title">{data.label}</strong>
            {data.unit && <span className="prov-unit">{data.unit}</span>}
            <button type="button" className="prov-close" aria-label="ปิด" onClick={onClose}>
              ✕
            </button>
          </div>

          {data.weakest_origin && (
            <div className={`prov-weakest prov-origin-${data.weakest_origin}`}>
              <span className="prov-weakest-label">ขั้นที่อ่อนที่สุดในสาย</span>
              <strong>{data.weakest_origin_label}</strong>
            </div>
          )}
          <p className="prov-weakest-note">{data.weakest_note}</p>

          <ol className="prov-steps">
            {data.steps.map((step, i) => (
              <StepRow key={`${step.kind}-${step.setting_key ?? i}`} step={step} />
            ))}
          </ol>

          <p className="prov-caveat">
            <strong>ข้อควรระวัง:</strong> {data.caveat}
          </p>
          {data.shown_on.length > 0 && (
            <p className="prov-shown-on">ตัวเลขเดียวกันนี้แสดงที่: {data.shown_on.join(' · ')}</p>
          )}
        </>
      )}
    </div>
  )
}

interface Props {
  /** A key from GET /provenance. Unknown keys 404 with the known list, so a
   * typo shows up as an error in the popover rather than as a silent no-op. */
  valueKey: string
  children: ReactNode
  /** Extra class on the wrapper, for callers that need the ⓘ to sit inside an
   * existing layout rather than beside it. */
  className?: string
}

export function Provenanced({ valueKey, children, className }: Props) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLSpanElement>(null)

  // Escape closes, and so does a click anywhere outside. Without the outside
  // click a viewer who opens two of these on one page ends up with both open
  // and overlapping.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    const onClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onClick)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onClick)
    }
  }, [open])

  return (
    <span ref={wrapRef} className={className ? `provenanced ${className}` : 'provenanced'}>
      {children}
      <button
        type="button"
        className="prov-button"
        aria-expanded={open}
        aria-label="ตัวเลขนี้มาจากไหน"
        title="ตัวเลขนี้มาจากไหน"
        onClick={() => setOpen((v) => !v)}
      >
        ⓘ
      </button>

      {open && <ProvenancePopover valueKey={valueKey} onClose={() => setOpen(false)} />}
    </span>
  )
}
