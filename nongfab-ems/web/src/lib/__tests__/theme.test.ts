import { describe, expect, it } from 'vitest'
import {
  applyTheme,
  isThemePreference,
  loadThemePreference,
  nextPreference,
  prefersDarkNow,
  resolveTheme,
  saveThemePreference,
  subscribeToOsTheme,
  THEME_HINTS,
  THEME_PREFERENCES,
  THEME_STORAGE_KEY,
} from '../theme'

describe('theme preferences', () => {
  it('only auto consults the operating system', () => {
    expect(resolveTheme('auto', true)).toBe('dark')
    expect(resolveTheme('auto', false)).toBe('light')
    // Someone who explicitly picked a theme means it, whatever their OS says.
    expect(resolveTheme('light', true)).toBe('light')
    expect(resolveTheme('dark', false)).toBe('dark')
    // Projector mode in particular must not be re-interpreted by a dark room.
    expect(resolveTheme('present', true)).toBe('present')
  })

  it('cycles through every preference and returns to the start', () => {
    let p = THEME_PREFERENCES[0]
    const seen = [p]
    for (let i = 0; i < THEME_PREFERENCES.length - 1; i++) {
      p = nextPreference(p)
      seen.push(p)
    }
    expect(new Set(seen).size).toBe(THEME_PREFERENCES.length)
    expect(nextPreference(p)).toBe(THEME_PREFERENCES[0])
  })

  it('falls back to auto for junk in storage rather than crashing', () => {
    expect(loadThemePreference({ getItem: () => 'neon' })).toBe('auto')
    expect(loadThemePreference({ getItem: () => null })).toBe('auto')
    expect(isThemePreference('present')).toBe(true)
    expect(isThemePreference('sepia')).toBe(false)
  })

  it('survives a localStorage that throws', () => {
    // Safari in private browsing does this rather than returning null, and a
    // theme toggle is not worth a white screen.
    const hostile = {
      getItem: () => {
        throw new Error('denied')
      },
      setItem: () => {
        throw new Error('denied')
      },
    }
    expect(loadThemePreference(hostile)).toBe('auto')
    expect(() => saveThemePreference('dark', hostile)).not.toThrow()
  })

  it('round-trips through real storage', () => {
    localStorage.clear()
    saveThemePreference('present')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('present')
    expect(loadThemePreference()).toBe('present')
  })

  it('stamps the resolved theme onto the element the stylesheet selects on', () => {
    const root = document.createElement('html')
    applyTheme('present', root)
    expect(root.dataset.theme).toBe('present')
    expect(root.matches("[data-theme='present']")).toBe(true)
  })

  it('does not need matchMedia to exist', () => {
    // jsdom has no matchMedia, and calling it unguarded from a header
    // component took the whole app shell down with "matchMedia is not a
    // function" - caught by six unrelated Layout tests, not by this file.
    expect(typeof matchMedia).not.toBe('function')
    expect(prefersDarkNow()).toBe(false)
    const unsubscribe = subscribeToOsTheme(() => {})
    expect(() => unsubscribe()).not.toThrow()
  })

  it('explains what every preference does', () => {
    // "นำเสนอ" on a button tells nobody what it changes; the hint is the only
    // place that does, so an empty one would be a silent feature.
    for (const p of THEME_PREFERENCES) {
      expect(THEME_HINTS[p]?.length ?? 0).toBeGreaterThan(10)
    }
  })
})
