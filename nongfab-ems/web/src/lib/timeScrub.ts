// Shared date/time-scrubber helpers - used by both Solar3DPage (per-zone sun
// sweep) and IrradianceMapPage (plant-wide irradiance time scrubber), so
// kept here once rather than duplicated across both pages.

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

/** YYYY-MM-DD calendar date in Thai local time (ICT = UTC+7) - the "en-CA"
 * locale happens to format as ISO (YYYY-MM-DD) directly, avoiding a manual
 * component-by-component reassembly. Used to decide whether a timestamp
 * falls on "today" (ICT) vs an earlier day, per this project's Thailand-
 * first display convention (see root CLAUDE.md) - a plain UTC calendar-day
 * slice (`iso.slice(0, 10)`) would misclassify ICT's early morning hours
 * (00:00-06:59 ICT = UTC+7, so still the *previous* UTC calendar day) as
 * "yesterday" even though a Thai viewer reads them as today. */
export function ictDateKey(iso: string): string {
  return new Date(iso).toLocaleDateString('en-CA', { timeZone: 'Asia/Bangkok' })
}

export function minutesToHhMm(minutes: number): string {
  const h = Math.floor(minutes / 60)
    .toString()
    .padStart(2, '0')
  const m = (minutes % 60).toString().padStart(2, '0')
  return `${h}:${m}`
}

export function buildAtIso(date: string, minutes: number): string {
  const hh = Math.floor(minutes / 60)
    .toString()
    .padStart(2, '0')
  const mm = (minutes % 60).toString().padStart(2, '0')
  return `${date}T${hh}:${mm}:00Z`
}

/** Converts a UTC minutes-of-day value - the time-scrubber sliders'
 * (Solar3DPage/IrradianceMapPage) own internal state, fed straight into
 * buildAtIso above - into the Thai local (ICT = UTC+7) HH:MM label to show
 * next to it, without changing what timestamp actually gets queried.
 *
 * Deliberately display-only: redefining the slider's *value* itself as
 * ICT-semantic (so dragging to the visual "noon" mark queries 12:00 ICT
 * directly) would need buildAtIso to shift the calendar *date* too whenever
 * the ICT time crosses midnight relative to the UTC one (e.g. "2026-07-17
 * 03:00 ICT" is "2026-07-16 20:00 UTC" - the *previous* UTC day) - a
 * genuine semantic change with real date-boundary-bug risk, not just a
 * label swap. Keeping the value UTC and converting only for display avoids
 * that risk entirely while still showing the correct real-world Thai time.
 */
export function utcMinutesToIctHhMm(utcMinutesOfDay: number): string {
  return minutesToHhMm((utcMinutesOfDay + 7 * 60) % (24 * 60))
}

/** HH:MM in UTC, for chart axis ticks/tooltips - also used by
 * SimulationPlaygroundPage's result chart, not just ForecastPage's. */
export function formatHourUtc(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' })
}

/** "17 Jul 01:00" in UTC - for charts spanning more than one calendar day
 * (ForecastPage's day-ahead horizon runs 72h/3 days), where HH:MM alone
 * repeats every day and gives no sense of which day a tick is on. User
 * asked for the date to visibly advance across the x-axis, not just the
 * time (2026-07-17). */
export function formatDateHourUtc(iso: string): string {
  const d = new Date(iso)
  // 'en-GB' forces day-month order ("17 Jul") deterministically - the
  // browser's default locale (passing []) would otherwise flip to
  // month-day ("Jul 17") for e.g. US-locale viewers, making the axis
  // format depend on who's looking at it.
  const datePart = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' })
  const timePart = formatHourUtc(iso)
  return `${datePart} ${timePart}`
}

/** HH:MM in Thai local time (ICT = UTC+7, Asia/Bangkok) - the default for
 * every chart/display in this app (2026-07-17): the user found UTC-computed
 * but visually-unlabeled times confusing across the site (a bare "12:00"
 * that's actually 19:00 in Thailand reads as a plausible local time with
 * nothing to say otherwise). `formatHourUtc` above is kept only where a UTC
 * figure is still useful as an explicitly-labeled secondary reference (e.g.
 * LiveClock's own dual display), not as the default anymore. */
export function formatHourIct(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Bangkok' })
}

/** "17 Jul 08:00" in Thai local time - see formatDateHourUtc's own docstring
 * for why multi-day charts need the date, not just HH:MM. */
export function formatDateHourIct(iso: string): string {
  const d = new Date(iso)
  const datePart = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'Asia/Bangkok' })
  const timePart = formatHourIct(iso)
  return `${datePart} ${timePart}`
}
