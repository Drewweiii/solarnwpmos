import type {
  AssetRegistry,
  ForecastHorizon,
  ForecastResponse,
  GeometryResponse,
  PerformanceResponse,
  SimulateRequest,
  SimulateResponse,
  SunPathResponse,
  Zone,
} from './types'

const API_BASE_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, token: string | null, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const resp = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = (await resp.json()) as { detail?: string }
      detail = body.detail ?? detail
    } catch {
      // response body wasn't JSON - fall back to statusText
    }
    throw new ApiError(resp.status, detail)
  }
  return (await resp.json()) as T
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const resp = await fetch(`${API_BASE_URL}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username, password }),
  })
  if (!resp.ok) {
    throw new ApiError(resp.status, 'incorrect username or password')
  }
  return (await resp.json()) as TokenResponse
}

export const getAssets = (token: string): Promise<AssetRegistry> => request('/assets', token)

export const getZone = (zoneId: string, token: string): Promise<Zone> => request(`/assets/${zoneId}`, token)

export const getForecast = (zone: string, horizon: ForecastHorizon, token: string): Promise<ForecastResponse> =>
  request(`/forecast/${zone}/${horizon}`, token)

export const getPerformance = (zone: string, token: string): Promise<PerformanceResponse> =>
  request(`/performance/${zone}`, token)

export const postSimulate = (zone: string, body: SimulateRequest, token: string): Promise<SimulateResponse> =>
  request(`/simulate/${zone}`, token, { method: 'POST', body: JSON.stringify(body) })

export const getGeometry = (zone: string, at: string | undefined, token: string): Promise<GeometryResponse> =>
  request(`/geometry/${zone}${at ? `?at=${encodeURIComponent(at)}` : ''}`, token)

export const getSunPath = (zone: string, date: string | undefined, token: string): Promise<SunPathResponse> =>
  request(`/sun-path/${zone}${date ? `?date=${encodeURIComponent(date)}` : ''}`, token)
