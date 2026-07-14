import { createContext, use, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { login as apiLogin } from './api'

export interface AuthState {
  token: string | null
  username: string | null
  role: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
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

  useEffect(() => {
    if (token) {
      localStorage.setItem(STORAGE_KEY, token)
      setClaims(decodeClaims(token))
    } else {
      localStorage.removeItem(STORAGE_KEY)
      setClaims({ sub: null, role: null })
    }
  }, [token])

  const value = useMemo<AuthState>(
    () => ({
      token,
      username: claims.sub,
      role: claims.role,
      login: async (username: string, password: string) => {
        const result = await apiLogin(username, password)
        setToken(result.access_token)
      },
      logout: () => setToken(null),
    }),
    [token, claims],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}

export function useAuth(): AuthState {
  const ctx = use(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
