import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getAssets, getVersion, setUnauthorizedHandler } from '../api'

function fetchResolving(status: number, body: unknown = {}) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'error',
    json: async () => body,
    text: async () => JSON.stringify(body),
  })
}

describe('request() unauthorized handling', () => {
  afterEach(() => {
    setUnauthorizedHandler(null)
    vi.unstubAllGlobals()
  })

  it('calls the registered unauthorized handler on a 401 for an authenticated call', async () => {
    vi.stubGlobal('fetch', fetchResolving(401, { detail: 'token expired' }))
    const handler = vi.fn()
    setUnauthorizedHandler(handler)

    await expect(getAssets('sometoken')).rejects.toBeInstanceOf(ApiError)
    expect(handler).toHaveBeenCalledOnce()
  })

  it('does not call the handler on a non-401 error', async () => {
    vi.stubGlobal('fetch', fetchResolving(500, { detail: 'server error' }))
    const handler = vi.fn()
    setUnauthorizedHandler(handler)

    await expect(getAssets('sometoken')).rejects.toBeInstanceOf(ApiError)
    expect(handler).not.toHaveBeenCalled()
  })

  it('does nothing when no handler is registered (no-op, not a crash)', async () => {
    vi.stubGlobal('fetch', fetchResolving(401, { detail: 'token expired' }))
    setUnauthorizedHandler(null)
    await expect(getAssets('sometoken')).rejects.toBeInstanceOf(ApiError)
  })
})

describe('getVersion', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches /version without an Authorization header', async () => {
    const fetchMock = fetchResolving(200, { deploy_id: 'abc123' })
    vi.stubGlobal('fetch', fetchMock)

    const result = await getVersion()

    expect(result).toEqual({ deploy_id: 'abc123' })
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/version')
    expect(new Headers(options.headers).has('Authorization')).toBe(false)
  })
})
