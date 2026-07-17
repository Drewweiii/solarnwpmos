import { createContext, use, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { login as apiLogin, setUnauthorizedHandler } from './api'

export interface AuthState {
  token: string | null
  username: string | null
  role: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  /** Same effect as `logout()`, but records `reason` so the next Login
   * screen can explain *why* the user landed back there instead of it
   * looking like a random bug. Used for both an API-rejected (401) token
   * and lib/deployWatch.ts's proactive "a new deploy just went live" check. */
  forceLogout: (reason: string) => void
  autoLogoutReason: string | null
}

const AuthContext = createContext<AuthState | undefined>(undefined)

const STORAGE_KEY = 'nongfab_ems_token'

// Decoded for display/RBAC-aware UI only (e.g. hiding an operator-only
// action from a viewer) - never trusted as an auth decision by itself, the
// backend re-validates the signature on every request regardless.
function decodeClaims(token: string): { sub: string | null; role: string | null } {
  try {
    const payload = token.split('.')[1]
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    const decoded = JSON.parse(json) as { sub?: string; role?: string }
    return { sub: decoded.sub ?? null, role: decoded.role ?? null }
  } catch {
    return { sub: null, role: null }
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY))
  const [claims, setClaims] = useState(() => (token ? decodeClaims(token) : { sub: null, role: null }))
  const [autoLogoutReason, setAutoLogoutReason] = useState<string | null>(null)

  useEffect(() => {
    if (token) {
      localStorage.setItem(STORAGE_KEY, token)
      setClaims(decodeClaims(token))
    } else {
      localStorage.removeItem(STORAGE_KEY)
      setClaims({ sub: null, role: null })
    }
  }, [token])

  // Wires api.ts's module-level 401 hook to this provider's own logout -
  // any authenticated call the backend rejects (expired token, or a token
  // from before the API's most recent redeploy) ends the session the same
  // way clicking "Sign out" would, just with an explanation shown next.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null)
      setAutoLogoutReason('เซสชันหมดอายุหรือระบบมีการอัปเดต กรุณาเข้าสู่ระบบใหม่อีกครั้ง')
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      token,
      username: claims.sub,
      role: claims.role,
      autoLogoutReason,
      login: async (username: string, password: string) => {
        const result = await apiLogin(username, password)
        setToken(result.access_token)
        setAutoLogoutReason(null)
      },
      logout: () => {
        setToken(null)
        setAutoLogoutReason(null)
      },
      forceLogout: (reason: string) => {
        setToken(null)
        setAutoLogoutReason(reason)
      },
    }),
    [token, claims, autoLogoutReason],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}

export function useAuth(): AuthState {
  const ctx = use(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
