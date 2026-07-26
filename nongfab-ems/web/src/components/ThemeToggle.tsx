import { useEffect, useState } from 'react'
import {
  applyTheme,
  loadThemePreference,
  nextPreference,
  prefersDarkNow,
  resolveTheme,
  saveThemePreference,
  subscribeToOsTheme,
  THEME_HINTS,
  THEME_ICONS,
  THEME_LABELS,
  type ThemePreference,
} from '../lib/theme'
import './ThemeToggle.css'

/** Cycle ตามระบบ → สว่าง → มืด → นำเสนอ (2026-07-26, project R).
 *
 * One button rather than a menu: four states is few enough to cycle, and the
 * current one is always legible on the button itself, so nobody has to open
 * anything to find out where they are.
 *
 * The interesting state is `present`. This project gets shown on a projector in
 * a lit room, where the normal palette's mid-greys do not survive the trip to
 * the wall - that mode is near-black on white with thicker chart strokes and a
 * larger base size. The hint text says so, because "นำเสนอ" on its own does not
 * tell anyone what it does.
 */
export function ThemeToggle() {
  const [preference, setPreference] = useState<ThemePreference>(() => loadThemePreference())

  // Keep the DOM in step with the preference. `index.html` already applied the
  // stored value before first paint; this handles every change after that.
  useEffect(() => {
    const sync = () => applyTheme(resolveTheme(preference, prefersDarkNow()))
    sync()
    // Only `auto` cares what the OS is doing, but subscribing unconditionally
    // costs nothing and avoids a stale listener when the preference changes.
    return subscribeToOsTheme(sync)
  }, [preference])

  const advance = () => {
    const next = nextPreference(preference)
    saveThemePreference(next)
    setPreference(next)
  }

  return (
    <button
      type="button"
      className="theme-toggle print-hide"
      onClick={advance}
      title={THEME_HINTS[preference]}
      aria-label={`ธีม: ${THEME_LABELS[preference]} — กดเพื่อเปลี่ยน`}
    >
      <span aria-hidden="true">{THEME_ICONS[preference]}</span>
      <span className="theme-toggle-label">{THEME_LABELS[preference]}</span>
    </button>
  )
}
