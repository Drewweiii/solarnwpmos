/** The local, per-browser draft of system settings (2026-07-25).
 *
 * The permission model the user chose is hybrid: anyone signed in may TRY
 * different values, but only an admin may publish one as the shared default.
 * "Trying" a value means writing it here - it lives in this browser only and
 * changes nothing for anybody else.
 *
 * Shared (rather than living inside SettingsPage) because the browser-applied
 * settings - the `hand.*` group - must honour the draft too: a viewer tuning
 * hand-control feel should see it take effect in the 3D view immediately, which
 * is the whole point of letting them try values they can't publish.
 */

export const SETTINGS_DRAFT_KEY = 'nongfab_settings_draft'

/** Fired on this window whenever the draft changes, so anything already
 * mounted (the 3D scene's hand control) picks up a new value without a reload.
 * `storage` events only fire in OTHER tabs, so a same-tab signal is needed. */
export const SETTINGS_DRAFT_EVENT = 'nongfab:settings-draft'

export function loadSettingsDraft(): Record<string, number> {
  try {
    const raw = localStorage.getItem(SETTINGS_DRAFT_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, unknown>
    // Defensive: a hand-edited or stale entry must not inject NaN into the
    // camera integrator, so keep only real finite numbers.
    const out: Record<string, number> = {}
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof value === 'number' && Number.isFinite(value)) out[key] = value
    }
    return out
  } catch {
    return {}
  }
}

export function saveSettingsDraft(draft: Record<string, number>): void {
  try {
    localStorage.setItem(SETTINGS_DRAFT_KEY, JSON.stringify(draft))
  } catch {
    // a full/blocked localStorage must not break the form itself
  }
  try {
    window.dispatchEvent(new CustomEvent(SETTINGS_DRAFT_EVENT))
  } catch {
    // no window (SSR/tests without DOM) - nothing to notify
  }
}
