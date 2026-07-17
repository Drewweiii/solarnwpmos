import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useDeployWatch } from '../deployWatch'
import * as api from '../api'

function fetchResolvingHtml(html: string) {
  return { ok: true, text: async () => html } as Response
}

describe('useDeployWatch', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('does not fire on the very first check (only establishes a baseline)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResolvingHtml('<html>v1</html>')))
    vi.spyOn(api, 'getVersion').mockResolvedValue({ deploy_id: 'd1' })
    const onDetected = vi.fn()

    renderHook(() => useDeployWatch(onDetected))
    await vi.advanceTimersByTimeAsync(0)

    expect(onDetected).not.toHaveBeenCalled()
  })

  it('fires when the served index.html changes on a later poll (frontend/Cloudflare redeploy)', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(fetchResolvingHtml('<html>v1</html>'))
      .mockResolvedValue(fetchResolvingHtml('<html>v2</html>'))
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(api, 'getVersion').mockResolvedValue({ deploy_id: 'd1' })
    const onDetected = vi.fn()

    renderHook(() => useDeployWatch(onDetected))
    await vi.advanceTimersByTimeAsync(0) // baseline
    await vi.advanceTimersByTimeAsync(60_000) // next poll

    expect(onDetected).toHaveBeenCalledOnce()
  })

  it('fires when the backend deploy_id changes on a later poll (Railway redeploy)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResolvingHtml('<html>same</html>')))
    vi.spyOn(api, 'getVersion').mockResolvedValueOnce({ deploy_id: 'd1' }).mockResolvedValue({ deploy_id: 'd2' })
    const onDetected = vi.fn()

    renderHook(() => useDeployWatch(onDetected))
    await vi.advanceTimersByTimeAsync(0) // baseline
    await vi.advanceTimersByTimeAsync(60_000) // next poll

    expect(onDetected).toHaveBeenCalledOnce()
  })

  it('does not fire while nothing changes across several polls', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResolvingHtml('<html>same</html>')))
    vi.spyOn(api, 'getVersion').mockResolvedValue({ deploy_id: 'd1' })
    const onDetected = vi.fn()

    renderHook(() => useDeployWatch(onDetected))
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(180_000)

    expect(onDetected).not.toHaveBeenCalled()
  })

  it('only fires once even if both signals change on the same poll', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(fetchResolvingHtml('<html>v1</html>'))
      .mockResolvedValue(fetchResolvingHtml('<html>v2</html>'))
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(api, 'getVersion').mockResolvedValueOnce({ deploy_id: 'd1' }).mockResolvedValue({ deploy_id: 'd2' })
    const onDetected = vi.fn()

    renderHook(() => useDeployWatch(onDetected))
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(60_000)

    expect(onDetected).toHaveBeenCalledOnce()
  })

  it('tolerates a transient fetch failure without firing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))
    vi.spyOn(api, 'getVersion').mockRejectedValue(new Error('network down'))
    const onDetected = vi.fn()

    renderHook(() => useDeployWatch(onDetected))
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(60_000)

    expect(onDetected).not.toHaveBeenCalled()
  })
})
