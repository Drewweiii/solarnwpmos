import { describe, expect, it } from 'vitest'
import {
  buildAtIso,
  formatDateHourIct,
  formatDateHourUtc,
  formatHourIct,
  formatHourUtc,
  ictDateKey,
  minutesToHhMm,
  todayIso,
  utcMinutesToIctHhMm,
} from '../timeScrub'

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

describe('utcMinutesToIctHhMm', () => {
  it('adds 7 hours for the ICT offset', () => {
    expect(utcMinutesToIctHhMm(5 * 60)).toBe('12:00') // Solar3DPage's own default - 05:00 UTC = noon ICT
  })

  it('wraps past midnight back to the start of the day', () => {
    expect(utcMinutesToIctHhMm(18 * 60)).toBe('01:00') // 18:00 UTC + 7h = 01:00 ICT the next day
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

describe('formatHourUtc', () => {
  it('formats an ISO timestamp as 24h HH:MM in UTC, ignoring the local timezone', () => {
    expect(formatHourUtc('2026-07-17T05:30:00Z')).toBe('05:30')
  })
})

describe('formatDateHourUtc', () => {
  it('formats an ISO timestamp with a short date plus 24h time, both in UTC', () => {
    expect(formatDateHourUtc('2026-07-17T05:30:00Z')).toBe('17 Jul 05:30')
  })

  it('advances the date part across a UTC midnight boundary', () => {
    expect(formatDateHourUtc('2026-07-17T23:00:00Z')).toBe('17 Jul 23:00')
    expect(formatDateHourUtc('2026-07-18T00:00:00Z')).toBe('18 Jul 00:00')
  })
})

describe('formatHourIct', () => {
  it('formats an ISO timestamp as 24h HH:MM in Thai local time (UTC+7)', () => {
    expect(formatHourIct('2026-07-17T05:30:00Z')).toBe('12:30')
  })

  it('rolls over into the next day past 17:00 UTC', () => {
    expect(formatHourIct('2026-07-17T17:30:00Z')).toBe('00:30')
  })
})

describe('ictDateKey', () => {
  it('returns a YYYY-MM-DD date in Thai local time', () => {
    expect(ictDateKey('2026-07-17T05:30:00Z')).toBe('2026-07-17') // 12:30 ICT, same UTC date
  })

  it('rolls the date forward across the UTC+7 boundary (late UTC evening)', () => {
    expect(ictDateKey('2026-07-17T17:30:00Z')).toBe('2026-07-18') // 00:30 ICT the next day
  })

  it('keeps the *previous* UTC date for ICT early-morning hours', () => {
    // 2026-07-13T18:00:00Z is 01:00 ICT on 2026-07-14 - a UTC date slice
    // would wrongly say "2026-07-13".
    expect(ictDateKey('2026-07-13T18:00:00Z')).toBe('2026-07-14')
  })
})

describe('formatDateHourIct', () => {
  it('formats an ISO timestamp with a short date plus 24h time, both in Thai local time', () => {
    expect(formatDateHourIct('2026-07-17T05:30:00Z')).toBe('17 Jul 12:30')
  })

  it('advances the date part across the UTC+7 day boundary, not the UTC one', () => {
    // 2026-07-17T17:30:00Z is 2026-07-18T00:30 ICT - the date must roll over
    // even though the UTC calendar date is still the 17th.
    expect(formatDateHourIct('2026-07-17T17:30:00Z')).toBe('18 Jul 00:30')
  })
})
