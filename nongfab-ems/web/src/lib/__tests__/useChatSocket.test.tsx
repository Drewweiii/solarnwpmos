import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth'
import { useChatSocket } from '../useChatSocket'
import type { ChatProfile } from '../chatProfile'
import type { ChatMessage } from '../types'
import { MockWebSocket } from './mockWebSocket'
import * as api from '../api'

const profile: ChatProfile = { clientId: 'my-client-id', displayName: 'ทดสอบ', avatarId: 'cat' }
const PEER = 'peer-client-id'

function setToken() {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
}

// Explicit ChatMessage return type (not inferred) - otherwise `type:
// 'message'` widens to `string`, and callers passing this into anything
// typed ChatMessage[] (e.g. mocking getChatHistory's response) fail to
// typecheck even though the value itself is perfectly valid at runtime.
function chatMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    type: 'message',
    id: 1,
    username: 'alice',
    role: 'viewer',
    text: 'hi',
    created_at: '2026-01-01T00:00:00Z',
    display_name: 'Alice',
    avatar: 'fox',
    client_id: PEER,
    recipient_client_id: profile.clientId,
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

  it('connects with client_id/display_name/avatar as query params and applies online_users pushes', async () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    expect(ws.url).toContain('client_id=my-client-id')
    expect(ws.url).toContain('display_name=%E0%B8%97%E0%B8%94%E0%B8%AA%E0%B8%AD%E0%B8%9A')
    expect(ws.url).toContain('avatar=cat')
    act(() => ws.open())

    act(() =>
      ws.emit({
        type: 'online_users',
        users: [{ client_id: PEER, display_name: 'Alice', avatar: 'fox', role: 'viewer' }],
      }),
    )
    await waitFor(() => expect(result.current.contacts).toHaveLength(1))
    expect(result.current.contacts[0]).toMatchObject({ clientId: PEER, displayName: 'Alice', online: true })
  })

  it('a live message from a peer opens/updates that peer conversation and remembers them as a contact', async () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    act(() => ws.emit(chatMessage({ id: 2, text: 'hello there' })))
    await waitFor(() => expect(result.current.conversations[PEER]?.messages).toHaveLength(1))
    expect(result.current.conversations[PEER].messages[0].text).toBe('hello there')
    // Even though this peer was never in an online_users push, receiving a
    // message from them is enough to remember them as a contact so the
    // conversation doesn't disappear from the list if they go offline.
    expect(result.current.contacts.map((c) => c.clientId)).toContain(PEER)
  })

  it('sendMessage addresses the peer via recipient_client_id and sends the caller-supplied profile once the socket is open', () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]

    result.current.sendMessage(PEER, 'too early')
    expect(ws.sent).toHaveLength(0)

    act(() => ws.open())
    result.current.sendMessage(PEER, '  hello there  ')
    expect(ws.sent).toEqual([
      JSON.stringify({ text: 'hello there', recipient_client_id: PEER, display_name: 'ทดสอบ', avatar: 'cat' }),
    ])
  })

  it('does not send a blank message or one with no recipient', () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    result.current.sendMessage(PEER, '   ')
    result.current.sendMessage('', 'hello')
    expect(ws.sent).toHaveLength(0)
  })

  it('updateProfile sends a type: update_profile message once the socket is open', () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    result.current.updateProfile('New Name', 'fox')
    expect(ws.sent).toEqual([JSON.stringify({ type: 'update_profile', display_name: 'New Name', avatar: 'fox' })])
  })

  it('a message from another peer does not leak into an unrelated conversation', async () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    act(() => ws.emit(chatMessage({ id: 1, client_id: PEER, text: 'from peer' })))
    act(() => ws.emit(chatMessage({ id: 2, client_id: 'someone-else', text: 'from someone else' })))
    await waitFor(() => expect(result.current.conversations['someone-else']?.messages).toHaveLength(1))

    expect(result.current.conversations[PEER].messages).toHaveLength(1)
    expect(result.current.conversations[PEER].messages[0].text).toBe('from peer')
  })

  it('counts an incoming message from a peer as unread while its thread is not the active one', async () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    act(() => ws.emit(chatMessage({ id: 5, client_id: PEER })))
    await waitFor(() => expect(result.current.totalUnreadCount).toBe(1))
    expect(result.current.conversations[PEER].unreadCount).toBe(1)
  })

  it('does not count its own message (matched by client_id) as unread', async () => {
    setToken()
    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    act(() => ws.emit(chatMessage({ id: 5, client_id: profile.clientId, recipient_client_id: PEER })))
    await waitFor(() => expect(result.current.conversations[PEER]?.messages).toHaveLength(1))
    expect(result.current.totalUnreadCount).toBe(0)
  })

  it('does not accumulate unread for the active peer thread, and clears any existing unread on becoming active', async () => {
    setToken()
    const { result, rerender } = renderHook(
      ({ active, peer }: { active: boolean; peer: string | null }) => useChatSocket(profile, peer, active),
      { wrapper: AuthProvider, initialProps: { active: false, peer: null as string | null } },
    )
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit(chatMessage({ id: 5, client_id: PEER })))
    await waitFor(() => expect(result.current.totalUnreadCount).toBe(1))

    rerender({ active: true, peer: PEER })
    await waitFor(() => expect(result.current.totalUnreadCount).toBe(0))

    act(() => ws.emit(chatMessage({ id: 6, client_id: PEER, text: 'while viewing' })))
    await waitFor(() => expect(result.current.conversations[PEER].messages).toHaveLength(2))
    expect(result.current.totalUnreadCount).toBe(0)
  })

  it('openConversation fetches the peer-scoped history and marks messages up to the last-read id as unread', async () => {
    setToken()
    const initialHistory = [chatMessage({ id: 1, text: 'old 1' }), chatMessage({ id: 2, text: 'old 2' })]
    vi.spyOn(api, 'getChatHistory').mockResolvedValue({ messages: initialHistory })

    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    await act(async () => {
      result.current.openConversation(PEER)
      await Promise.resolve()
    })

    await waitFor(() => expect(result.current.conversations[PEER]?.loaded).toBe(true))
    expect(api.getChatHistory).toHaveBeenCalledWith(profile.clientId, PEER, expect.any(String), undefined, 50)
    expect(result.current.conversations[PEER].messages).toHaveLength(2)
  })

  it('does not lose a just-sent message to a slower, already-in-flight openConversation history fetch (race reported live 2026-07-18: message visibly sent, then vanished)', async () => {
    setToken()
    // The history GET is still "in flight" (unresolved) when the WS echo of
    // the visitor's own send arrives - exactly the ordering a screen
    // recording showed live: opening a thread kicks off `getChatHistory()`,
    // but the visitor types and hits send before that slower HTTP round
    // trip comes back, so its response reflects the DB from *before* the
    // send was persisted.
    let resolveHistory: (value: { messages: ChatMessage[] }) => void
    const historyPromise = new Promise<{ messages: ChatMessage[] }>((resolve) => {
      resolveHistory = resolve
    })
    vi.spyOn(api, 'getChatHistory').mockReturnValue(historyPromise)

    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    act(() => {
      result.current.openConversation(PEER)
    })

    // The visitor's own message gets WS-echoed back before the history GET
    // resolves.
    act(() => ws.emit(chatMessage({ id: 7, client_id: profile.clientId, recipient_client_id: PEER, text: 'just sent' })))
    await waitFor(() => expect(result.current.conversations[PEER]?.messages).toHaveLength(1))

    // The history GET finally resolves - stale, from before the send was
    // committed, so it doesn't include the new message.
    await act(async () => {
      resolveHistory({ messages: [chatMessage({ id: 3, text: 'older message' })] })
      await Promise.resolve()
    })

    const texts = result.current.conversations[PEER].messages.map((m) => m.text)
    expect(texts).toContain('just sent')
    expect(texts).toContain('older message')
    expect(result.current.conversations[PEER].loaded).toBe(true)
  })

  it('loadOlder prepends a page fetched from GET /chat/history for that peer and flags when there is nothing further back', async () => {
    setToken()
    const initialHistory = Array.from({ length: 50 }, (_, i) => chatMessage({ id: 100 + i, text: `msg ${i}` }))
    const older = [chatMessage({ id: 1, text: 'oldest' })]
    vi.spyOn(api, 'getChatHistory').mockResolvedValueOnce({ messages: initialHistory }).mockResolvedValueOnce({ messages: older })

    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    await act(async () => {
      result.current.openConversation(PEER)
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.conversations[PEER]?.messages).toHaveLength(50))
    expect(result.current.conversations[PEER].hasMoreOlder).toBe(true)

    await act(async () => {
      result.current.loadOlder(PEER)
      await Promise.resolve()
    })

    await waitFor(() => expect(result.current.conversations[PEER].messages).toHaveLength(51))
    expect(result.current.conversations[PEER].messages[0].text).toBe('oldest')
    expect(api.getChatHistory).toHaveBeenLastCalledWith(profile.clientId, PEER, expect.any(String), 100, 50)
    expect(result.current.conversations[PEER].hasMoreOlder).toBe(false) // fewer than PAGE_SIZE returned
  })

  it('a contact seen in online_users survives going offline once a conversation with them has been opened', async () => {
    setToken()
    vi.spyOn(api, 'getChatHistory').mockResolvedValue({ messages: [] })
    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())

    act(() => ws.emit({ type: 'online_users', users: [{ client_id: PEER, display_name: 'Alice', avatar: 'fox', role: 'viewer' }] }))
    await waitFor(() => expect(result.current.contacts).toHaveLength(1))

    await act(async () => {
      result.current.openConversation(PEER)
      await Promise.resolve()
    })

    act(() => ws.emit({ type: 'online_users', users: [] }))
    await waitFor(() => expect(result.current.contacts).toHaveLength(1))
    expect(result.current.contacts[0]).toMatchObject({ clientId: PEER, online: false })
  })

  it('probes the token via an authenticated REST call when the WS handshake is rejected before it ever opens', async () => {
    // A pre-accept 403 (stale/expired token after a redeploy) - the browser
    // can't read its status, so the close-before-open must trigger verifyToken,
    // whose 401 handling logs the user out instead of looping forever.
    setToken()
    const verify = vi.spyOn(api, 'verifyToken').mockResolvedValue({} as never)
    renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.close()) // never opened
    expect(verify).toHaveBeenCalledTimes(1)
  })

  it('does NOT probe the token when a socket that had opened later closes (an ordinary reconnect)', async () => {
    setToken()
    const verify = vi.spyOn(api, 'verifyToken').mockResolvedValue({} as never)
    renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.close())
    expect(verify).not.toHaveBeenCalled()
  })
})
