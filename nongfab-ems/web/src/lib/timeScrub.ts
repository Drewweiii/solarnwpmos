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
