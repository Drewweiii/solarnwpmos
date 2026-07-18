import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth'
import { useChatSocket } from '../useChatSocket'
import type { ChatProfile } from '../chatProfile'
import { MockWebSocket } from './mockWebSocket'
import * as api from '../api'

const profile: ChatProfile = { clientId: 'my-client-id', displayName: 'ทดสอบ', avatarId: 'cat' }

function setToken() {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
}

function historyMessage(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    type: 'message',
    id: 1,
    username: 'alice',
    role: 'viewer',
    text: 'hi',
    created_at: '2026-01-01T00:00:00Z',
    display_name: 'Alice',
    avatar: 'fox',
    client_id: 'alice-client',
    ...overrides,
  }
}

describe('useChatSocket', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    MockWebSocket.instances.length = 0
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  it('applies history, presence, and message events pushed by the server', async () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    act(() => ws.emit({ type: 'history', messages: [historyMessage()] }))
    await waitFor(() => expect(result.current.messages).toHaveLength(1))

    act(() => ws.emit({ type: 'presence', count: 3, usernames: ['alice', 'bob', 'carol'] }))
    await waitFor(() => expect(result.current.onlineCount).toBe(3))

    act(() => ws.emit(historyMessage({ id: 2, text: 'hello back' })))
    await waitFor(() => expect(result.current.messages).toHaveLength(2))
    expect(result.current.messages[1].text).toBe('hello back')
  })

  it('sendMessage sends the trimmed text plus the caller-supplied profile once the socket is open', () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]

    result.current.sendMessage('too early')
    expect(ws.sent).toHaveLength(0)

    act(() => ws.open())
    result.current.sendMessage('  hello there  ')
    expect(ws.sent).toEqual([
      JSON.stringify({ text: 'hello there', display_name: 'ทดสอบ', avatar: 'cat', client_id: 'my-client-id' }),
    ])
  })

  it('does not send a blank message', () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    result.current.sendMessage('   ')
    expect(ws.sent).toHaveLength(0)
  })

  it('counts an incoming message from someone else as unread while not actively viewing', async () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit({ type: 'history', messages: [] }))

    act(() => ws.emit(historyMessage({ id: 5, client_id: 'someone-else' })))
    await waitFor(() => expect(result.current.unreadCount).toBe(1))
  })

  it('does not count its own message (matched by client_id) as unread', async () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit({ type: 'history', messages: [] }))

    act(() => ws.emit(historyMessage({ id: 5, client_id: profile.clientId })))
    await waitFor(() => expect(result.current.messages).toHaveLength(1))
    expect(result.current.unreadCount).toBe(0)
  })

  it('does not accumulate unread while isActiveView is true, and clears any existing unread on becoming active', async () => {
    setToken()
    const { result, rerender } = renderHook(({ active }: { active: boolean }) => useChatSocket(profile, active), {
      wrapper: AuthProvider,
      initialProps: { active: false },
    })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit({ type: 'history', messages: [] }))
    act(() => ws.emit(historyMessage({ id: 5, client_id: 'someone-else' })))
    await waitFor(() => expect(result.current.unreadCount).toBe(1))

    rerender({ active: true })
    await waitFor(() => expect(result.current.unreadCount).toBe(0))

    act(() => ws.emit(historyMessage({ id: 6, client_id: 'someone-else', text: 'while viewing' })))
    await waitFor(() => expect(result.current.messages).toHaveLength(2))
    expect(result.current.unreadCount).toBe(0)
  })

  it('loadOlder prepends a page fetched from GET /chat/history and flags when there is nothing further back', async () => {
    setToken()
    const older = [historyMessage({ id: 1, text: 'oldest' })]
    vi.spyOn(api, 'getChatHistory').mockResolvedValue({ messages: older })

    const { result } = renderHook(() => useChatSocket(profile, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    // A full page (PAGE_SIZE=50) of initial history so hasMoreOlder starts
    // true - otherwise the single-message history below would already look
    // like "that's everything" and loadOlder would short-circuit.
    const initialHistory = Array.from({ length: 50 }, (_, i) => historyMessage({ id: 100 + i, text: `msg ${i}` }))
    act(() => ws.emit({ type: 'history', messages: initialHistory }))
    await waitFor(() => expect(result.current.messages).toHaveLength(50))
    expect(result.current.hasMoreOlder).toBe(true)

    await act(async () => {
      result.current.loadOlder()
      await Promise.resolve()
    })

    await waitFor(() => expect(result.current.messages).toHaveLength(51))
    expect(result.current.messages[0].text).toBe('oldest')
    expect(api.getChatHistory).toHaveBeenCalledWith(100, expect.any(String), 50)
    expect(result.current.hasMoreOlder).toBe(false) // fewer than PAGE_SIZE returned
  })
})
