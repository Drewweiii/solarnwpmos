import { useMemo, useState } from 'react'
import { OfficialSourcesPanel } from '../components/OfficialSourcesPanel'
import { usePublishSettings, useResetAllSettings, useResetSetting, useSystemSettings } from '../lib/queries'
import { loadSettingsDraft, saveSettingsDraft } from '../lib/settingsDraft'
import type { SettingItem } from '../lib/types'
import './SettingsPage.css'

/** Part 2 of "editable system values" (2026-07-25) - the screen for the
 * settings backend shipped in part 1. ONE generic form renders all eight
 * groups straight from `GET /settings`'s own metadata (label, unit, bounds,
 * step, origin, note): adding a value backend-side needs no change here.
 *
 * Permission model, as the user chose it (hybrid): anyone signed in may read
 * the values and try different numbers *in their own browser* - those live in
 * a localStorage draft and change nothing for anybody else. Only an admin
 * (`can_publish`) may publish a draft as the shared system default, and only
 * an admin may reset one back to the value this build ships with.
 *
 * `origin` is shown on every field on purpose: it is what stops somebody
 * overwriting a confirmed site figure thinking it was a guess, or trusting a
 * placeholder thinking it was measured.
 */

// The draft lives in a shared module (settingsDraft.ts) rather than here: the
// browser-applied `hand.*` group reads it too, so a viewer tuning hand control
// sees their trial value take effect in the 3D view straight away.
const loadDraft = loadSettingsDraft
const saveDraft = saveSettingsDraft

/** Draft entries that actually differ from the published value - the only
 * ones worth sending, and what the "unsaved" count reflects. */
export function pendingChanges(settings: SettingItem[], draft: Record<string, number>): Record<string, number> {
  const out: Record<string, number> = {}
  for (const item of settings) {
    const drafted = draft[item.key]
    if (drafted !== undefined && drafted !== item.value) out[item.key] = drafted
  }
  return out
}

function formatWhen(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Bangkok' })
}

export function SettingsPage() {
  const settingsQuery = useSystemSettings()
  const publish = usePublishSettings()
  const resetOne = useResetSetting()
  const resetAll = useResetAllSettings()
  const [draft, setDraft] = useState<Record<string, number>>(() => loadDraft())
  const [openGroup, setOpenGroup] = useState<string | null>(null)

  const data = settingsQuery.data
  const settings = useMemo(() => data?.settings ?? [], [data])
  const pending = useMemo(() => pendingChanges(settings, draft), [settings, draft])
  const pendingCount = Object.keys(pending).length

  const grouped = useMemo(() => {
    const byGroup = new Map<string, SettingItem[]>()
    for (const item of settings) {
      const list = byGroup.get(item.group) ?? []
      list.push(item)
      byGroup.set(item.group, list)
    }
    return Array.from(byGroup.entries())
  }, [settings])

  function setValue(key: string, value: number) {
    setDraft((prev) => {
      const next = { ...prev, [key]: value }
      saveDraft(next)
      return next
    })
  }

  function clearDraftFor(key: string) {
    setDraft((prev) => {
      const next = { ...prev }
      delete next[key]
      saveDraft(next)
      return next
    })
  }

  function clearWholeDraft() {
    setDraft({})
    saveDraft({})
  }

  if (settingsQuery.isLoading) return <p className="forecast-status">กำลังโหลดค่าระบบ…</p>
  if (settingsQuery.error || !data) {
    return <p className="forecast-status forecast-status-warn">โหลดค่าระบบไม่สำเร็จ</p>
  }

  const canPublish = data.can_publish

  return (
    <div className="settings-page">
      <section className="settings-intro">
        <h2>ค่าระบบที่แก้ไขได้</h2>
        <p>
          ค่าทั้งหมด {settings.length} ค่าใน {grouped.length} กลุ่มนี้ป้อนเข้าการคำนวณจริงของเว็บ (ฟิสิกส์ การเงิน และเกณฑ์ตรวจสุขภาพระบบ){' '}
          {canPublish ? (
            <>คุณเป็นแอดมิน จึง <strong>บันทึกเป็นค่ากลางของระบบ</strong> ให้ทุกคนเห็นได้</>
          ) : (
            <>คุณลองเปลี่ยนตัวเลขดูได้ตามใจ — <strong>ค่าที่แก้จะอยู่แค่ในเบราว์เซอร์ของคุณเอง</strong> ไม่กระทบคนอื่น (เฉพาะแอดมินที่บันทึกเป็นค่ากลางได้)</>
          )}
        </p>
        <p className="settings-note">
          ป้ายกำกับ “ที่มาของค่า” บอกว่าค่าตั้งต้นแต่ละตัวมาจากไหน — ค่าที่ยืนยันแล้วกับค่าประมาณไม่ควรถูกแก้ด้วยความมั่นใจเท่ากัน
        </p>
      </section>

      <div className="settings-toolbar" role="group" aria-label="จัดการค่าที่แก้ไข">
        <span className="settings-pending" aria-live="polite">
          {pendingCount > 0 ? `แก้ไว้ ${pendingCount} ค่า (ยังไม่บันทึก)` : 'ยังไม่มีค่าที่แก้ไว้'}
        </span>
        {pendingCount > 0 && (
          <button type="button" className="settings-btn" onClick={clearWholeDraft}>
            ล้างค่าที่ลองไว้
          </button>
        )}
        {canPublish && (
          <>
            <button
              type="button"
              className="settings-btn settings-btn-primary"
              disabled={pendingCount === 0 || publish.isPending}
              onClick={() => publish.mutate(pending, { onSuccess: clearWholeDraft })}
            >
              {publish.isPending ? 'กำลังบันทึก…' : `บันทึกเป็นค่ากลาง (${pendingCount})`}
            </button>
            <button
              type="button"
              className="settings-btn settings-btn-danger"
              disabled={resetAll.isPending}
              onClick={() => {
                if (window.confirm('คืนค่าทั้งหมดกลับเป็นค่าตั้งต้นของระบบ?')) {
                  resetAll.mutate(undefined, { onSuccess: clearWholeDraft })
                }
              }}
            >
              คืนค่าตั้งต้นทั้งหมด
            </button>
          </>
        )}
      </div>

      {publish.isError && <p className="settings-error">บันทึกไม่สำเร็จ: {(publish.error as Error).message}</p>}
      {publish.isSuccess && pendingCount === 0 && <p className="settings-success">บันทึกเป็นค่ากลางเรียบร้อยแล้ว</p>}

      {grouped.map(([group, items]) => {
        const groupLabel = items[0]?.group_label ?? data.groups[group] ?? group
        const isOpen = openGroup === null || openGroup === group
        const changedHere = items.filter((i) => pending[i.key] !== undefined).length
        return (
          <section key={group} className="settings-group" aria-label={groupLabel}>
            <button
              type="button"
              className="settings-group-header"
              aria-expanded={isOpen}
              onClick={() => setOpenGroup(openGroup === group ? null : group)}
            >
              <span className="settings-group-title">{groupLabel}</span>
              <span className="settings-group-meta">
                {changedHere > 0 && <span className="settings-chip settings-chip-changed">แก้ไว้ {changedHere}</span>}
                <span className="settings-group-count">{items.length} ค่า</span>
              </span>
            </button>

            {isOpen && (
              <div className="settings-fields">
                {items.map((item) => (
                  <SettingField
                    key={item.key}
                    item={item}
                    draftValue={draft[item.key]}
                    canPublish={canPublish}
                    onChange={(v) => setValue(item.key, v)}
                    onClearDraft={() => clearDraftFor(item.key)}
                    onResetPublished={() => resetOne.mutate(item.key, { onSuccess: () => clearDraftFor(item.key) })}
                  />
                ))}
              </div>
            )}
          </section>
        )
      })}

      {/* Where the hand-entered tariff/emission numbers came from, and whether
          the issuing agency has published anything newer (2026-07-25). Sits
          below the form because it is about the values' provenance, not about
          editing them. */}
      <OfficialSourcesPanel />
    </div>
  )
}

function SettingField({
  item,
  draftValue,
  canPublish,
  onChange,
  onClearDraft,
  onResetPublished,
}: {
  item: SettingItem
  draftValue: number | undefined
  canPublish: boolean
  onChange: (value: number) => void
  onClearDraft: () => void
  onResetPublished: () => void
}) {
  const shown = draftValue ?? item.value
  const isDrafted = draftValue !== undefined && draftValue !== item.value
  const outOfRange = shown < item.minimum || shown > item.maximum
  const inputId = `setting-${item.key}`

  return (
    <div className={`settings-field${isDrafted ? ' settings-field-drafted' : ''}`}>
      <label className="settings-field-label" htmlFor={inputId}>
        {item.label}
        {item.unit && <span className="settings-field-unit"> ({item.unit})</span>}
      </label>

      <div className="settings-field-row">
        <input
          id={inputId}
          type="number"
          className="settings-input"
          value={shown}
          min={item.minimum}
          max={item.maximum}
          step={item.step}
          onChange={(e) => {
            const v = Number(e.target.value)
            if (!Number.isNaN(v)) onChange(v)
          }}
        />
        {isDrafted && (
          <button type="button" className="settings-mini-btn" onClick={onClearDraft} title="ยกเลิกค่าที่ลองไว้">
            ↩︎ ยกเลิก
          </button>
        )}
        {/* Resetting a PUBLISHED override is an admin action against the shared
            default - distinct from clearing your own local draft above. */}
        {canPublish && item.overridden && (
          <button type="button" className="settings-mini-btn settings-mini-btn-danger" onClick={onResetPublished}>
            คืนค่าตั้งต้น
          </button>
        )}
      </div>

      <div className="settings-field-meta">
        <span className={`settings-chip settings-chip-origin settings-origin-${item.origin}`}>{item.origin_label}</span>
        {item.overridden && <span className="settings-chip settings-chip-overridden">แอดมินตั้งค่าไว้</span>}
        {item.frontend_only && <span className="settings-chip">ใช้ในเบราว์เซอร์</span>}
        <span className="settings-field-default">ค่าตั้งต้น {item.default}</span>
        {isDrafted && <span className="settings-field-was">เดิม {item.value}</span>}
      </div>

      {item.note && <p className="settings-field-note">{item.note}</p>}
      {outOfRange && (
        <p className="settings-field-warn">
          ต้องอยู่ระหว่าง {item.minimum} ถึง {item.maximum} — ค่านอกช่วงนี้จะถูกปฏิเสธตอนบันทึก
        </p>
      )}
      {item.overridden && item.updated_by && (
        <p className="settings-field-audit">
          แก้ล่าสุดโดย {item.updated_by}
          {item.updated_at ? ` · ${formatWhen(item.updated_at)}` : ''}
        </p>
      )}
    </div>
  )
}
