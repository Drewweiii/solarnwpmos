/** Theme selection, including a mode for projectors (2026-07-26, project R).
 *
 * The site had dark mode via `@media (prefers-color-scheme: dark)` and no way
 * to override it. Two problems with that. A visitor whose laptop is in dark
 * mode could not get a light page to screenshot for a document, and - the one
 * that actually bites - this project gets shown on a **projector in a lit
 * room**, where the screen palette's `--text: #6b6375` on `#fff` is a grey that
 * simply is not there by the time it reaches the wall.
 *
 * So there are four preferences and three resolved themes. `present` is a real
 * theme, not dark mode with bigger text: near-black on pure white, heavier
 * chart strokes, larger base size.
 *
 * HOW THE ATTRIBUTE GETS SET, AND WHY IT ALWAYS IS. `index.html` runs a tiny
 * synchronous script in `<head>` that resolves the stored preference and
 * stamps `data-theme` on `<html>` before first paint, so there is no flash of
 * the wrong theme. Because that attribute is therefore always present, the
 * stylesheet needs only `:root[data-theme='dark']` and `[data-theme='present']`
 * - the palette lives in exactly one place instead of being duplicated between
 * a media query and an attribute selector, which is how those two drift apart.
 */

export type ThemePreference = 'auto' | 'light' | 'dark' | 'present'
export type ResolvedTheme = 'light' | 'dark' | 'present'

export const THEME_STORAGE_KEY = 'nongfab_ems_theme'

const PREFERENCES: readonly ThemePreference[] = ['auto', 'light', 'dark', 'present']

export const THEME_LABELS: Record<ThemePreference, string> = {
  auto: 'ตามระบบ',
  light: 'สว่าง',
  dark: 'มืด',
  present: 'นำเสนอ',
}

export const THEME_ICONS: Record<ThemePreference, string> = {
  auto: '🖥️',
  light: '☀️',
  dark: '🌙',
  present: '📽️',
}

/** Spelled out rather than left for the viewer to discover, because "นำเสนอ"
 * does not tell anyone what it changes. */
export const THEME_HINTS: Record<ThemePreference, string> = {
  auto: 'ใช้ค่าสว่าง/มืดตามการตั้งค่าของเครื่อง',
  light: 'บังคับโหมดสว่าง',
  dark: 'บังคับโหมดมืด',
  present: 'คอนทราสต์สูง ตัวอักษรใหญ่ เส้นกราฟหนา — สำหรับฉายโปรเจกเตอร์ในห้องที่มีแสง',
}

export function isThemePreference(value: unknown): value is ThemePreference {
  return typeof value === 'string' && (PREFERENCES as readonly string[]).includes(value)
}

/** Reads the stored preference, falling back to `auto` for anything unexpected
 * - including a `localStorage` that throws, which is what Safari does in
 * private browsing rather than returning null. */
export function loadThemePreference(storage: Pick<Storage, 'getItem'> = localStorage): ThemePreference {
  try {
    const raw = storage.getItem(THEME_STORAGE_KEY)
    return isThemePreference(raw) ? raw : 'auto'
  } catch {
    return 'auto'
  }
}

export function saveThemePreference(
  preference: ThemePreference,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  try {
    storage.setItem(THEME_STORAGE_KEY, preference)
  } catch {
    // A viewer who cannot persist the choice should still get the theme for
    // this session; losing it on reload beats failing to apply it at all.
  }
}

/** `auto` is the only preference that consults the OS. `present` deliberately
 * ignores it: somebody who picked projector mode wants projector mode, not a
 * dark room's idea of it. */
export function resolveTheme(preference: ThemePreference, prefersDark: boolean): ResolvedTheme {
  if (preference === 'auto') return prefersDark ? 'dark' : 'light'
  return preference
}

export function applyTheme(resolved: ResolvedTheme, root: HTMLElement = document.documentElement): void {
  root.dataset.theme = resolved
}

const OS_DARK_QUERY = '(prefers-color-scheme: dark)'

/** Whether the OS is asking for dark right now.
 *
 * Guarded because `matchMedia` is not universally present - jsdom has no
 * implementation, and calling it unguarded from a header component is enough
 * to take the whole shell down. False is the right answer when we cannot ask:
 * `auto` then resolves to light, which is the palette that renders acceptably
 * everywhere.
 */
export function prefersDarkNow(): boolean {
  if (typeof matchMedia !== 'function') return false
  try {
    return matchMedia(OS_DARK_QUERY).matches
  } catch {
    return false
  }
}

/** Calls back when the OS light/dark setting changes. Returns an unsubscribe
 * that is safe to call even when nothing could be subscribed. */
export function subscribeToOsTheme(onChange: () => void): () => void {
  if (typeof matchMedia !== 'function') return () => {}
  try {
    const media = matchMedia(OS_DARK_QUERY)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  } catch {
    return () => {}
  }
}

/** The next preference in the cycle, for a single-button toggle. */
export function nextPreference(current: ThemePreference): ThemePreference {
  const i = PREFERENCES.indexOf(current)
  return PREFERENCES[(i + 1) % PREFERENCES.length]
}

export const THEME_PREFERENCES = PREFERENCES
