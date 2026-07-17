import { useEffect, useRef } from 'react'
import { getVersion } from './api'

const DEPLOY_CHECK_INTERVAL_MS = 60_000

async function fetchIndexHtml(): Promise<string | null> {
  try {
    const resp = await fetch('/', { cache: 'no-store' })
    if (!resp.ok) return null
    return await resp.text()
  } catch {
    return null // offline/transient network error - never treat this as "a new deploy happened"
  }
}

/**
 * Detects a new deploy - either backend (Railway; `GET /version` returns a
 * fresh `deploy_id` minted once per API process boot, see main.py) or
 * frontend (Cloudflare Pages; the served `index.html` changes because
 * Vite's asset filenames are content-hashed, so any rebuild changes the
 * `<script>`/`<link>` tags even when nothing else did) - and calls
 * `onDeployDetected` the first time either signal changes from the
 * baseline captured when this hook mounted.
 *
 * This is the user's own explicit request (2026-07-17): any code Claude
 * ships, on either GitHub (-> Cloudflare, frontend) or Railway (backend),
 * should force every currently-logged-in session to sign back in, so
 * nobody keeps using a stale frontend against a new backend or vice versa.
 *
 * The backend half is *also* enforced server-side regardless of this hook
 * (auth.py's `deploy_id` JWT claim - any authenticated API call already
 * 401s after a redeploy, which lib/api.ts's unauthorized handler turns
 * into a logout on its own). This hook exists on top of that for two
 * reasons: it catches sessions sitting idle on a page with no active
 * queries (nothing would 401 yet), and it's the *only* mechanism that can
 * catch a frontend-only (Cloudflare) redeploy, since that never touches
 * the API at all.
 *
 * Only meaningful while mounted for an already-authenticated session (see
 * Layout.tsx, which is only rendered once `token` is set) - there is
 * nothing to log out of before then.
 */
export function useDeployWatch(onDeployDetected: () => void): void {
  const callbackRef = useRef(onDeployDetected)
  callbackRef.current = onDeployDetected

  useEffect(() => {
    let cancelled = false
    let baselineHtml: string | null = null
    let baselineDeployId: string | null = null
    let fired = false

    async function checkOnce() {
      const [html, versionResult] = await Promise.all([fetchIndexHtml(), getVersion().catch(() => null)])
      if (cancelled || fired) return

      if (html != null) {
        if (baselineHtml == null) baselineHtml = html
        else if (html !== baselineHtml) {
          fired = true
          callbackRef.current()
          return
        }
      }

      if (versionResult != null) {
        if (baselineDeployId == null) baselineDeployId = versionResult.deploy_id
        else if (versionResult.deploy_id !== baselineDeployId) {
          fired = true
          callbackRef.current()
        }
      }
    }

    void checkOnce() // establish the baseline promptly, don't wait a full interval
    const id = window.setInterval(() => void checkOnce(), DEPLOY_CHECK_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])
}
