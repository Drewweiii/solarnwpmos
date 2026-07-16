// Shared date/time-scrubber helpers - used by both Solar3DPage (per-zone sun
// sweep) and IrradianceMapPage (plant-wide irradiance time scrubber), so
// kept here once rather than duplicated across both pages.

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
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
