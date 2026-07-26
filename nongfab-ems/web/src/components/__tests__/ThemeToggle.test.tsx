import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { THEME_STORAGE_KEY } from '../../lib/theme'
import { ThemeToggle } from '../ThemeToggle'

function stubMatchMedia(prefersDark: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: prefersDark && query.includes('prefers-color-scheme: dark'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
}

describe('ThemeToggle', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    stubMatchMedia(false)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('applies the resolved theme to the element the stylesheet selects on', () => {
    stubMatchMedia(true)
    render(<ThemeToggle />)
    // Default preference is auto, OS says dark, so the attribute the palette
    // hangs off must say dark - the CSS has no media query left to fall back on.
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('cycles auto → light → dark → present and persists the choice', async () => {
    render(<ThemeToggle />)
    const button = screen.getByRole('button')

    await userEvent.click(button)
    expect(document.documentElement.dataset.theme).toBe('light')
    await userEvent.click(button)
    expect(document.documentElement.dataset.theme).toBe('dark')
    await userEvent.click(button)
    expect(document.documentElement.dataset.theme).toBe('present')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('present')
  })

  it('lets an explicit choice beat the operating system', async () => {
    stubMatchMedia(true)
    render(<ThemeToggle />)
    await userEvent.click(screen.getByRole('button'))
    // The whole reason this control exists: a dark-mode laptop must still be
    // able to show a light page.
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('restores a stored preference on next visit', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'present')
    render(<ThemeToggle />)
    expect(document.documentElement.dataset.theme).toBe('present')
  })

  it('names the current theme for screen readers rather than only drawing an icon', () => {
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: /ธีม: ตามระบบ/ })).toBeInTheDocument()
  })
})
