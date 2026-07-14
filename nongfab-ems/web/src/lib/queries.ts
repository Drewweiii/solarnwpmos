import { useQueries, useQuery } from '@tanstack/react-query'
import { getAssets, getForecast, getGeometry, getPerformance, getSunPath } from './api'
import type { ForecastHorizon } from './types'
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

export function useForecast(zone: string, horizon: ForecastHorizon) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['forecast', zone, horizon],
    queryFn: () => getForecast(zone, horizon, token!),
    enabled: Boolean(token) && zone !== ALL_ZONES_ID,
    retry: false, // 404 (no model trained yet) shouldn't be retried
  })
}

export function usePerformance(zone: string) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['performance', zone],
    queryFn: () => getPerformance(zone, token!),
    enabled: Boolean(token) && zone !== ALL_ZONES_ID,
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
    })),
  })
}

/** `at`: ISO timestamp to evaluate the sun/shading at - omit for "now".
 * Kept out of the query key's identity when unset vs a specific instant so
 * "now" queries still get react-query's normal staleTime/refetch behavior. */
export function useGeometry(zone: string, at?: string) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['geometry', zone, at ?? 'now'],
    queryFn: () => getGeometry(zone, at, token!),
    enabled: Boolean(token) && zone !== ALL_ZONES_ID,
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
