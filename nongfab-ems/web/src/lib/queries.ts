import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getAssets,
  getCloudConditions,
  getCurrentConditions,
  getFeatureImportance,
  getExpansion,
  getGridToday,
  getFeedHealth,
  getForecastVerification,
  getOutputAnomalies,
  getSoiling,
  getEnergyReport,
  getSavingsSummary,
  getSettings,
  putSettings,
  deleteSetting,
  resetSettings,
  getFeedback,
  getForecast,
  getGeometry,
  getIrradianceMap,
  getMoonPath,
  getPerformance,
  getPrecipitationConditions,
  getSunPath,
  getUvHistory,
  getUvHourlyHistory,
  getWeatherStrip,
  postFeedback,
  postFinancial,
  postSimulate,
} from './api'
import type { FinancialRequest, ForecastHorizon, SimulateRequest } from './types'
import { useAuth } from './auth'
import { loadChatProfile } from './chatProfile'

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

// Site-wide, not per-zone (see routes_weather.py's own get_cloud_conditions
// docstring) - drives Solar3DPage's drifting cloud layer. Polled at the same
// cadence as the rest of the "live" dashboard data (see LIVE_REFETCH_
// INTERVAL_MS's own docstring above) so the cloud layer's opacity/drift
// direction stays current with whatever the Himawari poller last saw.
export function useCloudConditions() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['cloud-conditions'],
    queryFn: () => getCloudConditions(token!),
    enabled: Boolean(token),
    refetchInterval: LIVE_REFETCH_INTERVAL_MS,
  })
}

// Site-wide, not per-zone (see routes_weather.py's own get_precipitation_
// conditions docstring) - drives Solar3DPage's rain animation. Same polling
// cadence as useCloudConditions above, for the same "stays current with the
// live dashboard" reasoning.
export function usePrecipitationConditions() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['precipitation-conditions'],
    queryFn: () => getPrecipitationConditions(token!),
    enabled: Boolean(token),
    refetchInterval: LIVE_REFETCH_INTERVAL_MS,
  })
}

// Site-wide, not per-zone (see routes_weather.py's own get_current_
// conditions docstring) - drives ForecastPage's 9-variable 3x3 table
// (2026-07-18 user request). Same live-dashboard polling cadence as the
// cloud/precipitation queries above - UV specifically won't actually change
// between polls (it's daily-resolution server-side), but polling it at the
// same cadence as everything else costs nothing extra (one shared endpoint)
// and keeps this hook simple rather than special-casing one field's cadence.
export function useCurrentConditions() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['current-conditions'],
    queryFn: () => getCurrentConditions(token!),
    enabled: Boolean(token),
    refetchInterval: LIVE_REFETCH_INTERVAL_MS,
  })
}

// Per-zone hour-ahead feature importance (2026-07-24) - slow-moving (only
// changes on a retrain), so a long staleTime, not the 60s live cadence.
export function useFeatureImportance(zone: string) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['feature-importance', zone],
    queryFn: () => getFeatureImportance(token!, zone),
    enabled: Boolean(token),
    staleTime: 5 * 60 * 1000,
  })
}

// Expansion scenarios are pure config + seasonal model output - they only change
// when config/assets.yaml does, so this is effectively static per deploy.
export function useGridToday() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['grid-today'],
    queryFn: () => getGridToday(token!),
    enabled: Boolean(token),
    // EGAT publishes one new sample a minute and the API caches for the same
    // interval, so anything faster than this just re-reads the same snapshot.
    refetchInterval: 60 * 1000,
    staleTime: 60 * 1000,
  })
}

export function useExpansion() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['expansion'],
    queryFn: () => getExpansion(token!),
    enabled: Boolean(token),
    staleTime: 60 * 60 * 1000,
  })
}

// Feed health is the one diagnostic worth polling briskly: its whole purpose is
// to notice a source going quiet, and a stale reading of staleness is useless.
export function useFeedHealth() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['diagnostics-feeds'],
    queryFn: () => getFeedHealth(token!),
    enabled: Boolean(token),
    refetchInterval: 5 * 60 * 1000,
    staleTime: 60 * 1000,
  })
}

// Anomalies only change as whole days complete.
export function useOutputAnomalies(zone: string, days = 45) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['diagnostics-anomalies', zone, days],
    queryFn: () => getOutputAnomalies(token!, zone, days),
    enabled: Boolean(token),
    staleTime: 30 * 60 * 1000,
  })
}

// Verification scores a whole window of past forecasts against actuals, which
// only changes as new hours complete - a long staleTime, deliberately off the
// live-dashboard cadence.
export function useForecastVerification(zone: string, days = 30) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['forecast-verification', zone, days],
    queryFn: () => getForecastVerification(token!, zone, days),
    enabled: Boolean(token),
    staleTime: 15 * 60 * 1000,
  })
}

// The soiling assessment walks up to 90 days of history server-side and only
// changes as new air-quality/rainfall data lands (hourly at most), so it is
// deliberately off the live-dashboard polling cadence with a long staleTime.
export function useSoiling(zone: string) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['soiling', zone],
    queryFn: () => getSoiling(token!, zone),
    enabled: Boolean(token),
    staleTime: 30 * 60 * 1000,
  })
}

// Site-wide, not per-zone - drives ForecastPage's daily UV bar chart
// (2026-07-19). Deliberately NOT on the 60s live-dashboard polling cadence
// (see LIVE_REFETCH_INTERVAL_MS above) - UV is daily-resolution server-side
// (see routes_weather.py's own get_uv_history docstring), so polling it
// every 60s like the rest of the dashboard would just be repeated requests
// for data that cannot have changed within a day. A long staleTime instead,
// same "slow-moving data" pattern as useZones above.
export function useUvHistory() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['uv-history'],
    queryFn: () => getUvHistory(token!),
    enabled: Boolean(token),
    staleTime: 30 * 60 * 1000,
  })
}

// Hourly UV curve (Open-Meteo hourly=uv_index, 2026-07-22 roadmap item 5) -
// the real intraday shape, unlike useUvHistory's one-bar-per-day list. Same
// slow-moving-data staleTime: the backend only refreshes it a few times a day.
export function useUvHourlyHistory() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['uv-hourly-history'],
    queryFn: () => getUvHourlyHistory(token!),
    enabled: Boolean(token),
    staleTime: 30 * 60 * 1000,
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

export function useMoonPath(zone: string, date?: string) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['moon-path', zone, date ?? 'today'],
    queryFn: () => getMoonPath(zone, date, token!),
    enabled: Boolean(token) && zone !== ALL_ZONES_ID,
    staleTime: 60 * 60 * 1000, // a whole day's moon-path arc doesn't change within the same UTC day
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

/** Site-wide savings & carbon summary (ISB/GIS/Jetty + combined) for the
 * Energy Report bottom table - a single call covers every zone, so it is not
 * zone-scoped like `useEnergyReport`. Slow-moving (seasonal estimates), so the
 * same 5-min staleTime as the energy report is plenty. */
export function useSavingsSummary() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['savings-summary'],
    queryFn: () => getSavingsSummary(token!),
    enabled: Boolean(token),
    staleTime: 5 * 60 * 1000,
  })
}

/** `at`: ISO timestamp to evaluate the irradiance grid at - omit for "now",
 * same convention as `useGeometry`. `placeholderData: keepPreviousData` for
 * the same reason as `useGeometry`: without it, the irradiance ground
 * overlay (Solar3DScene.tsx's `IrradianceGroundOverlay`, previously a
 * separate MapLibre canvas before the two were merged into one WebGL scene
 * 2026-07-18) would flicker/unmount its points on every time-scrubber tick
 * instead of smoothly updating their color as fresh data streams in -
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
    // Attach the visitor's self-chosen display name (chatProfile.ts) so admin
    // sees who actually wrote the note, not just the shared login username.
    mutationFn: (text: string) => postFeedback(text, token!, loadChatProfile()?.displayName ?? null),
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

// --- Editable system values (2026-07-25) ---------------------------------
// One query feeds the whole settings page: the response is self-describing
// (label/unit/bounds/step/origin per key), so the page renders every group
// from it without hardcoding fields. Not polled - these only change when
// somebody publishes, and every mutation below invalidates the key.

/** GET /settings. Viewer-level: anyone signed in may read the values (and try
 * them locally); `can_publish` in the response says whether this caller may
 * save a shared default. */
export function useSystemSettings() {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['settings'],
    queryFn: () => getSettings(token!),
    enabled: Boolean(token),
    staleTime: 60 * 1000,
  })
}

/** PUT /settings - publish a batch as the shared system default (admin-only
 * server-side). Validated as a whole backend-side: one bad field rejects the
 * entire submission rather than saving half of it. */
export function usePublishSettings() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (values: Record<string, number>) => putSettings(values, token!),
    // Published values feed physics/money calculations across the whole app
    // (loss factors, capacities, financial assumptions), so drop every cached
    // query rather than just the settings one - otherwise the dashboard would
    // keep showing figures computed from the previous values.
    onSuccess: () => queryClient.invalidateQueries(),
  })
}

/** DELETE /settings/{key} - reset ONE value back to the shipped default. */
export function useResetSetting() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (key: string) => deleteSetting(key, token!),
    onSuccess: () => queryClient.invalidateQueries(),
  })
}

/** POST /settings/reset - reset EVERY value back to the shipped defaults. */
export function useResetAllSettings() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => resetSettings(token!),
    onSuccess: () => queryClient.invalidateQueries(),
  })
}
