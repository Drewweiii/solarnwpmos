import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getAssets,
  getEnergyReport,
  getFeedback,
  getForecast,
  getGeometry,
  getIrradianceMap,
  getPerformance,
  getSunPath,
  getWeatherStrip,
  postFeedback,
  postFinancial,
  postSimulate,
} from './api'
import type { FinancialRequest, ForecastHorizon, SimulateRequest } from './types'
import { useAuth } from './auth'

export const ALL_ZONES_ID = 'ALL'
export const REAL_ZONE_IDS = ['GIS', 'ISB', 'Jetty'] as const

export function useZones() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['assets'],
    queryFn: () => getAssets(token!),
    enabled: Boolean(token),
    staleTime: 5 * 60 * 1000, // plant geometry/equipment changes rarely
  })
}

// Dashboard KPI/chart data (performance + forecast) polls every 60s so the
// numbers visibly move without a manual reload - approved 2026-07-16 after
// the user noticed the demo's numbers never changed. Geometry/sun-path/
// energy-report/assets are deliberately NOT polled here: they're either
// scrub-driven (geometry/irradiance-map re-fetch on time-slider change
// already) or genuinely slow-moving (assets/energy-report).
const LIVE_REFETCH_INTERVAL_MS = 60_000

export function useForecast(zone: string, horizon: ForecastHorizon) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['forecast', zone, horizon],
    queryFn: () => getForecast(zone, horizon, token!),
    enabled: Boolean(token) && zone !== ALL_ZONES_ID,
    retry: false, // 404 (no model trained yet) shouldn't be retried
    refetchInterval: LIVE_REFETCH_INTERVAL_MS,
  })
}

// Site-wide, not per-zone (see api.ts's own getWeatherStrip docstring) - one
// shared query regardless of which zone tab is selected.
export function useWeatherStrip() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['weather-strip'],
    queryFn: () => getWeatherStrip(token!),
    enabled: Boolean(token),
    refetchInterval: LIVE_REFETCH_INTERVAL_MS,
  })
}

export function usePerformance(zone: string) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['performance', zone],
    queryFn: () => getPerformance(zone, token!),
    enabled: Boolean(token) && zone !== ALL_ZONES_ID,
    refetchInterval: LIVE_REFETCH_INTERVAL_MS,
  })
}

/** One /performance call per real zone in parallel - backs the "All" (รวม)
 * zone selection, which has no single backend endpoint of its own. */
export function useAllZonesPerformance() {
  const { token } = useAuth()
  return useQueries({
    queries: REAL_ZONE_IDS.map((zone) => ({
      queryKey: ['performance', zone],
      queryFn: () => getPerformance(zone, token!),
      enabled: Boolean(token),
      refetchInterval: LIVE_REFETCH_INTERVAL_MS,
    })),
  })
}

/** One /forecast call per real zone in parallel - backs the "All" (รวม)
 * zone selection's forecast line/band. */
export function useAllZonesForecast(horizon: ForecastHorizon) {
  const { token } = useAuth()
  return useQueries({
    queries: REAL_ZONE_IDS.map((zone) => ({
      queryKey: ['forecast', zone, horizon],
      queryFn: () => getForecast(zone, horizon, token!),
      enabled: Boolean(token),
      retry: false,
      refetchInterval: LIVE_REFETCH_INTERVAL_MS,
    })),
  })
}

/** `at`: ISO timestamp to evaluate the sun/shading at - omit for "now".
 * Kept out of the query key's identity when unset vs a specific instant so
 * "now" queries still get react-query's normal staleTime/refetch behavior.
 * `placeholderData: keepPreviousData` - each `at` is a distinct query key
 * (a distinct cache entry), so without it `data` would go `undefined`
 * between every time-scrubber tick; the 3D page only renders `Solar3DScene`
 * while `data` is defined, so that gap was unmounting/remounting the whole
 * WebGL canvas on every tick, discarding the user's camera pan/zoom - found
 * via this page's own live verification (see web/README.md). */
export function useGeometry(zone: string, at?: string) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['geometry', zone, at ?? 'now'],
    queryFn: () => getGeometry(zone, at, token!),
    enabled: Boolean(token) && zone !== ALL_ZONES_ID,
    placeholderData: keepPreviousData,
  })
}

export function useSunPath(zone: string, date?: string) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['sun-path', zone, date ?? 'today'],
    queryFn: () => getSunPath(zone, date, token!),
    enabled: Boolean(token) && zone !== ALL_ZONES_ID,
    staleTime: 60 * 60 * 1000, // a whole day's sun-path arc doesn't change within the same UTC day
  })
}

export function useEnergyReport(zone: string) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['energy-report', zone],
    queryFn: () => getEnergyReport(zone, token!),
    enabled: Boolean(token) && zone !== ALL_ZONES_ID,
    staleTime: 5 * 60 * 1000, // annual/loss/SLD figures don't change within a session
  })
}

/** `at`: ISO timestamp to evaluate the irradiance grid at - omit for "now",
 * same convention as `useGeometry`. `placeholderData: keepPreviousData` for
 * the same reason as `useGeometry`: without it, `IrradianceMapView` (the
 * MapLibre canvas) would unmount/remount on every time-scrubber tick,
 * silently resetting the layer-visibility toggles back to their default -
 * caught live (see web/README.md). */
export function useIrradianceMap(at?: string) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['irradiance-map', at ?? 'now'],
    queryFn: () => getIrradianceMap(at, token!),
    enabled: Boolean(token),
    placeholderData: keepPreviousData,
  })
}

/** POST /simulate/{zone} is a mutation, not a query - the Simulation
 * Playground (STEP 9) runs it on demand ("Run simulation"), not on every
 * slider tick, since it's gated at operator-or-higher as a heavier
 * what-if computation (see api/routes_simulate.py's own docstring), not a
 * plain read like every other hook in this file. */
export function useSimulate() {
  const { token } = useAuth()
  return useMutation({
    mutationFn: ({ zone, request }: { zone: string; request: SimulateRequest }) => postSimulate(zone, request, token!),
  })
}

/** POST /financial is also a mutation, not a query, same reasoning as
 * useSimulate() above - a heavier what-if computation run on demand, not a
 * plain read. */
export function useFinancial() {
  const { token } = useAuth()
  return useMutation({
    mutationFn: (request: FinancialRequest) => postFinancial(request, token!),
  })
}

/** POST /feedback (contact form) - a mutation, not a query, same as
 * useSimulate/useFinancial above. Invalidates the admin inbox query so an
 * admin who happens to have that page open sees new submissions without a
 * manual refresh. */
export function useSubmitFeedback() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (text: string) => postFeedback(text, token!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['feedback'] }),
  })
}

/** GET /feedback (admin-only inbox) - polled at the same cadence as the
 * other "live" dashboard data so a new visitor message shows up without a
 * manual refresh. */
export function useFeedbackInbox() {
  const { token, role } = useAuth()
  return useQuery({
    queryKey: ['feedback'],
    queryFn: () => getFeedback(token!),
    enabled: Boolean(token) && role === 'admin',
    refetchInterval: LIVE_REFETCH_INTERVAL_MS,
  })
}
