import type {
  AssetRegistry,
  ChatMessage,
  OnlineUser,
  CloudConditionsResponse,
  CurrentConditionsResponse,
  EnergyReportResponse,
  SavingsSummaryResponse,
  FeedbackItem,
  FinancialRequest,
  FinancialResponse,
  ForecastHorizon,
  ForecastResponse,
  GeometryResponse,
  IrradianceMapResponse,
  MoonPathResponse,
  PerformanceResponse,
  PrecipitationConditionsResponse,
  SimulateRequest,
  SimulateResponse,
  SunPathResponse,
  UvHistoryResponse,
  UvHourlyHistoryResponse,
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

/** Makes one authenticated REST call purely to find out whether `token` is
 * still accepted by the API. On a 401 (expired, or minted before the API's
 * most recent redeploy - see auth.py's deploy_id claim) `request()` fires the
 * app-wide unauthorized handler -> logout, exactly as any other authenticated
 * call would. Used by useChatSocket to turn a silently-rejected WebSocket
 * handshake (a pre-accept 403 the browser can't read the status of) into the
 * same re-login flow, instead of reconnecting forever on a dead token. Reuses
 * `/assets` rather than adding a bespoke endpoint - it's a small, always-
 * available authenticated GET. */
export const verifyToken = (token: string): Promise<AssetRegistry> => request('/assets', token)

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

export const getCloudConditions = (token: string): Promise<CloudConditionsResponse> => request('/weather/clouds', token)

export const getPrecipitationConditions = (token: string): Promise<PrecipitationConditionsResponse> =>
  request('/weather/precipitation', token)

export const getCurrentConditions = (token: string): Promise<CurrentConditionsResponse> => request('/weather/conditions', token)

export const getUvHistory = (token: string): Promise<UvHistoryResponse> => request('/weather/uv-history', token)

export const getUvHourlyHistory = (token: string): Promise<UvHourlyHistoryResponse> =>
  request('/weather/uv-hourly-history', token)

export const postSimulate = (zone: string, body: SimulateRequest, token: string): Promise<SimulateResponse> =>
  request(`/simulate/${zone}`, token, { method: 'POST', body: JSON.stringify(body) })

export const postFinancial = (body: FinancialRequest, token: string): Promise<FinancialResponse> =>
  request('/financial', token, { method: 'POST', body: JSON.stringify(body) })

export const getGeometry = (zone: string, at: string | undefined, token: string): Promise<GeometryResponse> =>
  request(`/geometry/${zone}${at ? `?at=${encodeURIComponent(at)}` : ''}`, token)

export const getSunPath = (zone: string, date: string | undefined, token: string): Promise<SunPathResponse> =>
  request(`/sun-path/${zone}${date ? `?date=${encodeURIComponent(date)}` : ''}`, token)

export const getMoonPath = (zone: string, date: string | undefined, token: string): Promise<MoonPathResponse> =>
  request(`/moon-path/${zone}${date ? `?date=${encodeURIComponent(date)}` : ''}`, token)

export const getEnergyReport = (zone: string, token: string): Promise<EnergyReportResponse> =>
  request(`/energy-report/${zone}`, token)

export const getSavingsSummary = (token: string): Promise<SavingsSummaryResponse> =>
  request(`/savings/summary`, token)

// --- REST chat transport (2026-07-20, replaces the WebSocket) -------------
export interface ChatProfileFields {
  clientId: string
  displayName: string
  avatarId: string
}

export const chatPresence = (fields: ChatProfileFields, token: string): Promise<{ users: OnlineUser[] }> =>
  request('/chat/presence', token, {
    method: 'POST',
    body: JSON.stringify({ client_id: fields.clientId, display_name: fields.displayName, avatar: fields.avatarId }),
  })

export const chatSend = (
  fields: ChatProfileFields,
  recipientClientId: string,
  text: string,
  token: string,
): Promise<{ message: ChatMessage }> =>
  request('/chat/send', token, {
    method: 'POST',
    body: JSON.stringify({
      client_id: fields.clientId,
      recipient_client_id: recipientClientId,
      text,
      display_name: fields.displayName,
      avatar: fields.avatarId,
    }),
  })

export const chatInbox = (myClientId: string, afterId: number, token: string): Promise<{ messages: ChatMessage[] }> =>
  request(`/chat/inbox?my_client_id=${encodeURIComponent(myClientId)}&after_id=${afterId}`, token)

export const getIrradianceMap = (at: string | undefined, token: string): Promise<IrradianceMapResponse> =>
  request(`/irradiance-map${at ? `?at=${encodeURIComponent(at)}` : ''}`, token)

export interface VersionResponse {
  deploy_id: string
}

// Unauthenticated on purpose (see main.py's /version) - lib/deployWatch.ts
// polls this regardless of whether the session has any other query running,
// so an idle tab still notices a backend redeploy.
export const getVersion = (): Promise<VersionResponse> => request('/version', null)

export const postFeedback = (text: string, token: string, displayName?: string | null): Promise<FeedbackItem> =>
  request('/feedback', token, { method: 'POST', body: JSON.stringify({ text, display_name: displayName ?? null }) })

export const getFeedback = (token: string): Promise<FeedbackItem[]> => request('/feedback', token)

// ws_chat.py's `/ws/chat` handshake auth, same `?token=` convention as every
// other authenticated call - derived from API_BASE_URL's http(s) scheme
// rather than a second env var, so it can never drift out of sync with it.
// `clientId`/`displayName`/`avatarId` also ride along as query params (not
// headers - browsers can't set custom headers on a WS upgrade) since the
// server now needs to know who this socket is *at connect time*, before any
// message is ever sent (it's what populates the online-users list).
export function chatSocketUrl(token: string, clientId: string, displayName: string, avatarId: string): string {
  const wsBase = API_BASE_URL.replace(/^http/, 'ws')
  const params = new URLSearchParams({ token, client_id: clientId })
  if (displayName) params.set('display_name', displayName)
  if (avatarId) params.set('avatar', avatarId)
  return `${wsBase}/ws/chat?${params.toString()}`
}

// A conversation is now scoped to one specific pair of visitors (private
// messaging, not one shared public room - see ws_chat.py's module
// docstring), so both ends of the pair are required. `beforeId` omitted
// loads the most recent page; passed, it pages further back within that
// same pair - never messages the two exchanged with anyone else.
export const getChatHistory = (
  myClientId: string,
  peerClientId: string,
  token: string,
  beforeId?: number,
  limit = 50,
): Promise<{ messages: ChatMessage[] }> => {
  const params = new URLSearchParams({ my_client_id: myClientId, peer_client_id: peerClientId, limit: String(limit) })
  if (beforeId != null) params.set('before_id', String(beforeId))
  return request(`/chat/history?${params.toString()}`, token)
}
