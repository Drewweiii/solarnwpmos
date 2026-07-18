import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth'
import { useChatSocket } from '../useChatSocket'
import { MockWebSocket } from './mockWebSocket'

function setToken() {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
}

describe('useChatSocket', () => {
  beforeEach(() => {
    localStorage.clear()
    MockWebSocket.instances.length = 0
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  it('applies history, presence, and message events pushed by the server', async () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    act(() =>
      ws.emit({
        type: 'history',
        messages: [{ type: 'message', id: 1, username: 'alice', role: 'viewer', text: 'hi', created_at: '2026-01-01T00:00:00Z' }],
      }),
    )
    await waitFor(() => expect(result.current.messages).toHaveLength(1))

    act(() => ws.emit({ type: 'presence', count: 3, usernames: ['alice', 'bob', 'carol'] }))
    await waitFor(() => expect(result.current.onlineCount).toBe(3))

    act(() => ws.emit({ type: 'message', id: 2, username: 'bob', role: 'viewer', text: 'hello back', created_at: '2026-01-01T00:01:00Z' }))
    await waitFor(() => expect(result.current.messages).toHaveLength(2))
    expect(result.current.messages[1].text).toBe('hello back')
  })

  it('sendMessage only sends trimmed text once the socket is open', () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]

    result.current.sendMessage('too early')
    expect(ws.sent).toHaveLength(0)

    act(() => ws.open())
    result.current.sendMessage('  hello there  ')
    expect(ws.sent).toEqual([JSON.stringify({ text: 'hello there' })])
  })

  it('does not send a blank message', () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    result.current.sendMessage('   ')
    expect(ws.sent).toHaveLength(0)
  })
})
