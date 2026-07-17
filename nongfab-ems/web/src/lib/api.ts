import type {
  AssetRegistry,
  EnergyReportResponse,
  FinancialRequest,
  FinancialResponse,
  ForecastHorizon,
  ForecastResponse,
  GeometryResponse,
  IrradianceMapResponse,
  PerformanceResponse,
  SimulateRequest,
  SimulateResponse,
  SunPathResponse,
  WeatherStripResponse,
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

// Set by AuthProvider (lib/auth.tsx) on mount - api.ts has no React context
// of its own, so this module-level slot is how a 401 from any authenticated
// call gets turned into a logout. Covers both ordinary token expiry and (as
// of 2026-07-17) a token minted before the API's most recent redeploy, see
// auth.py's deploy_id claim on the backend side - either way the token is
// dead, and the user asked that this always force a fresh sign-in rather
// than leave the app quietly broken.
type UnauthorizedHandler = () => void
let unauthorizedHandler: UnauthorizedHandler | null = null

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler
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
    // Only calls that actually sent a token reach here on a 401 - login()
    // itself uses a separate raw fetch, not request(), so a wrong-password
    // attempt on the login screen never triggers this.
    if (resp.status === 401 && token) unauthorizedHandler?.()
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

// Site-wide, not per-zone (see routes_weather.py's own docstring) -
// `hoursEachSide` matches the backend's own generous default window so the
// frontend can always slice a smaller display range out of one cached response.
export const getWeatherStrip = (token: string, hoursEachSide = 12): Promise<WeatherStripResponse> =>
  request(`/weather/strip?hours_each_side=${hoursEachSide}`, token)

export const postSimulate = (zone: string, body: SimulateRequest, token: string): Promise<SimulateResponse> =>
  request(`/simulate/${zone}`, token, { method: 'POST', body: JSON.stringify(body) })

export const postFinancial = (body: FinancialRequest, token: string): Promise<FinancialResponse> =>
  request('/financial', token, { method: 'POST', body: JSON.stringify(body) })

export const getGeometry = (zone: string, at: string | undefined, token: string): Promise<GeometryResponse> =>
  request(`/geometry/${zone}${at ? `?at=${encodeURIComponent(at)}` : ''}`, token)

export const getSunPath = (zone: string, date: string | undefined, token: string): Promise<SunPathResponse> =>
  request(`/sun-path/${zone}${date ? `?date=${encodeURIComponent(date)}` : ''}`, token)

export const getEnergyReport = (zone: string, token: string): Promise<EnergyReportResponse> =>
  request(`/energy-report/${zone}`, token)

export const getIrradianceMap = (at: string | undefined, token: string): Promise<IrradianceMapResponse> =>
  request(`/irradiance-map${at ? `?at=${encodeURIComponent(at)}` : ''}`, token)

export interface VersionResponse {
  deploy_id: string
}

// Unauthenticated on purpose (see main.py's /version) - lib/deployWatch.ts
// polls this regardless of whether the session has any other query running,
// so an idle tab still notices a backend redeploy.
export const getVersion = (): Promise<VersionResponse> => request('/version', null)
