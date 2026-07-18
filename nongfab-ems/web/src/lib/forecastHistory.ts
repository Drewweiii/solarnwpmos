import { useEffect, useMemo, useRef, useState } from 'react'
import type { ForecastPoint } from './types'

/**
 * Accumulates every forecast point ever seen across polls, keyed by its
 * target timestamp, instead of only ever showing whatever the latest poll
 * returned. Necessary because Intra-day/Day-ahead's `/forecast` endpoint is
 * always computed fresh "as of now" (see `forecast/serving.py`'s
 * `issued_at`) - it only ever returns lead hours *forward* from whenever it
 * was called, never a record of what was predicted for an hour that has
 * since passed. Without this, the Forecast line and Prediction interval
 * band visibly vanished for any hour the moment it dropped out of that
 * forward window (the user's own 2026-07-18 report, across all/GIS/ISB/
 * Jetty) - even though the app *had* already fetched and rendered a real
 * prediction for that hour a few polls earlier. Once accumulated, a row
 * carries both `generated` (real/actual, from the merge in chartData.ts)
 * and `pred`/`lower`/`upper` side by side, so hovering a past point's
 * tooltip shows both together for comparison - the whole point of the fix.
 *
 * A newer issuance for the same target hour overwrites the older one
 * (forecasts issued closer to the target time are more accurate, so the
 * freshest value for a given hour should win over an older one).
 *
 * `resetKey` (e.g. `${zoneId}:${horizon}`) clears the accumulated history
 * whenever the viewer switches to a different zone or horizon - carrying
 * GIS's history over onto ISB, or Day-ahead's onto Intra-day, would
 * misrepresent what was actually predicted for that series. Reset happens
 * synchronously during render (not in a `useEffect`) so the previous
 * series' stale history never flashes on screen for a frame first.
 *
 * Session-only (an in-memory `Map`, not persisted anywhere) - reloading the
 * page or opening a fresh tab starts the history over. That's an accepted
 * limitation, not a bug: a durable server-side archive of every forecast
 * ever issued is a much bigger feature than this fix calls for.
 */
// Field-by-field, not `===` - callers rebuild `latest` from scratch on every
// render (`sumForecastAcrossZones`/query-derived arrays have no referential
// stability across renders, only the underlying values do), so comparing
// object identity here marked every point "changed" on every render even
// when nothing actually did, which fed straight back into this hook's own
// `setHistory` call and produced an infinite render loop in practice
// ("Maximum update depth exceeded", found live testing this fix). Comparing
// by value instead means the effect below settles once the accumulated
// value actually matches what's already stored, letting React bail out.
function candidateErrorsEqual(a: Record<string, number> | null, b: Record<string, number> | null): boolean {
  const aEntries = Object.entries(a ?? {})
  const bEntries = Object.entries(b ?? {})
  if (aEntries.length !== bEntries.length) return false
  return aEntries.every(([algo, rmse]) => b?.[algo] === rmse)
}

function pointsEqual(a: ForecastPoint, b: ForecastPoint): boolean {
  return (
    a.pred === b.pred &&
    a.lower === b.lower &&
    a.upper === b.upper &&
    a.algorithm === b.algorithm &&
    a.error === b.error &&
    candidateErrorsEqual(a.candidate_errors, b.candidate_errors)
  )
}

export function useForecastHistory(latest: ForecastPoint[], resetKey: string): ForecastPoint[] {
  const [history, setHistory] = useState<Map<string, ForecastPoint>>(() => new Map())
  const resetKeyRef = useRef(resetKey)

  if (resetKeyRef.current !== resetKey) {
    resetKeyRef.current = resetKey
    setHistory(new Map())
  }

  useEffect(() => {
    if (latest.length === 0) return
    setHistory((prev) => {
      let changed = false
      const next = new Map(prev)
      for (const point of latest) {
        const existing = next.get(point.timestamp)
        if (existing == null || !pointsEqual(existing, point)) {
          next.set(point.timestamp, point)
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [latest])

  return useMemo(() => [...history.values()].sort((a, b) => a.timestamp.localeCompare(b.timestamp)), [history])
}
