import { describe, expect, it } from 'vitest'
import { buildAtIso, minutesToHhMm, todayIso } from '../timeScrub'

describe('minutesToHhMm', () => {
  it('pads hours and minutes to two digits', () => {
    expect(minutesToHhMm(0)).toBe('00:00')
    expect(minutesToHhMm(5)).toBe('00:05')
    expect(minutesToHhMm(60)).toBe('01:00')
  })

  it('formats a mid-day time correctly', () => {
    expect(minutesToHhMm(12 * 60 + 30)).toBe('12:30')
  })
})

describe('buildAtIso', () => {
  it('combines a date and minute-of-day into a UTC ISO timestamp', () => {
    expect(buildAtIso('2026-07-14', 0)).toBe('2026-07-14T00:00:00Z')
    expect(buildAtIso('2026-07-14', 12 * 60 + 30)).toBe('2026-07-14T12:30:00Z')
  })
})

describe('todayIso', () => {
  it('returns a YYYY-MM-DD formatted date', () => {
    expect(todayIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
