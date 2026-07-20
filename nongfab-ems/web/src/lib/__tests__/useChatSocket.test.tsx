import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import { AuthProvider } from '../auth'
import type { ChatProfile } from '../chatProfile'
import type { ChatMessage } from '../types'
import { useChatSocket } from '../useChatSocket'

const profile: ChatProfile = { clientId: 'my-client-id', displayName: 'ทดสอบ', avatarId: 'cat' }
const PEER = 'peer-client-id'

function setToken() {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
}

// Explicit ChatMessage return type so `type: 'message'` doesn't widen to string.
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

// Default the polled endpoints to "nothing happening" so each test only has to
// override the one it cares about.
function stubIdle() {
  vi.spyOn(api, 'chatPresence').mockResolvedValue({ users: [] })
  vi.spyOn(api, 'chatInbox').mockResolvedValue({ messages: [] })
  vi.spyOn(api, 'getChatHistory').mockResolvedValue({ messages: [] })
}

describe('useChatSocket (REST transport)', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('heartbeats presence and turns the online list into contacts + connected', async () => {
    setToken()
    vi.spyOn(api, 'chatInbox').mockResolvedValue({ messages: [] })
    vi.spyOn(api, 'getChatHistory').mockResolvedValue({ messages: [] })
    vi.spyOn(api, 'chatPresence').mockResolvedValue({
      users: [{ client_id: PEER, display_name: 'Alice', avatar: 'fox', role: 'viewer' }],
    })

    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.connected).toBe(true))
    expect(result.current.contacts).toHaveLength(1)
    expect(result.current.contacts[0]).toMatchObject({ clientId: PEER, displayName: 'Alice', online: true })
    expect(api.chatPresence).toHaveBeenCalledWith(
      { clientId: profile.clientId, displayName: profile.displayName, avatarId: profile.avatarId },
      expect.any(String),
    )
  })

  it('shows an own message optimistically as pending, then reconciles it to the confirmed server copy', async () => {
    setToken()
    stubIdle()
    const send = vi.spyOn(api, 'chatSend').mockResolvedValue({
      message: chatMessage({ id: 42, client_id: profile.clientId, recipient_client_id: PEER, text: 'hello there' }),
    })

    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    act(() => {
      result.current.sendMessage(PEER, 'hello there')
    })
    // Instant optimistic bubble, pending, before the POST resolves.
    expect(result.current.conversations[PEER].messages[0].pending).toBe(true)
    expect(send).toHaveBeenCalledWith(
      { clientId: profile.clientId, displayName: profile.displayName, avatarId: profile.avatarId },
      PEER,
      'hello there',
      expect.any(String),
    )

    await waitFor(() => expect(result.current.conversations[PEER].messages[0].id).toBe(42))
    expect(result.current.conversations[PEER].messages).toHaveLength(1)
    expect(result.current.conversations[PEER].messages[0].pending).toBeFalsy()
  })

  it('flags an own message as failed when the send POST rejects', async () => {
    setToken()
    stubIdle()
    vi.spyOn(api, 'chatSend').mockRejectedValue(new Error('boom'))

    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    act(() => {
      result.current.sendMessage(PEER, 'will fail')
    })
    await waitFor(() => expect(result.current.conversations[PEER].messages[0].failed).toBe(true))
    expect(result.current.conversations[PEER].messages[0].pending).toBe(false)
  })

  it('delivers an incoming message from the inbox poll and fires onLiveMessage (after the first catch-up)', async () => {
    vi.useFakeTimers()
    try {
      setToken()
      vi.spyOn(api, 'chatPresence').mockResolvedValue({ users: [] })
      vi.spyOn(api, 'getChatHistory').mockResolvedValue({ messages: [] })
      // First poll (prime): empty. Second poll: a new incoming message.
      vi.spyOn(api, 'chatInbox')
        .mockResolvedValueOnce({ messages: [] })
        .mockResolvedValue({ messages: [chatMessage({ id: 7, client_id: PEER, text: 'hello there' })] })
      const onLive = vi.fn()

      const { result } = renderHook(() => useChatSocket(profile, null, false, onLive), { wrapper: AuthProvider })
      // Flush the immediate prime poll, then advance past one inbox interval so
      // the second poll (the new message) runs.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2600)
      })

      expect(result.current.conversations[PEER]?.messages?.[0]?.text).toBe('hello there')
      expect(result.current.totalUnreadCount).toBe(1)
      expect(onLive).toHaveBeenCalledTimes(1)
      expect(result.current.contacts.map((c) => c.clientId)).toContain(PEER)
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not fire notifications or count unread for messages already present on the first catch-up poll', async () => {
    setToken()
    vi.spyOn(api, 'chatPresence').mockResolvedValue({ users: [] })
    vi.spyOn(api, 'getChatHistory').mockResolvedValue({ messages: [] })
    vi.spyOn(api, 'chatInbox').mockResolvedValue({ messages: [chatMessage({ id: 3, client_id: PEER, text: 'old unread' })] })
    const onLive = vi.fn()

    const { result } = renderHook(() => useChatSocket(profile, null, false, onLive), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.conversations[PEER]?.messages).toHaveLength(1))
    expect(result.current.totalUnreadCount).toBe(0) // pre-existing, not "new since you looked"
    expect(onLive).not.toHaveBeenCalled()
  })

  it('openConversation fetches the peer-scoped history', async () => {
    setToken()
    stubIdle()
    vi.spyOn(api, 'getChatHistory').mockResolvedValue({ messages: [chatMessage({ id: 1, text: 'old 1' }), chatMessage({ id: 2, text: 'old 2' })] })

    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    await act(async () => {
      result.current.openConversation(PEER)
      await Promise.resolve()
    })
    await waitFor(() => expect(result.current.conversations[PEER]?.loaded).toBe(true))
    expect(api.getChatHistory).toHaveBeenCalledWith(profile.clientId, PEER, expect.any(String), undefined, 50)
    expect(result.current.conversations[PEER].messages).toHaveLength(2)
  })

  it('retrySend drops the failed bubble and sends the text again as a fresh optimistic message', async () => {
    setToken()
    stubIdle()
    vi.spyOn(api, 'chatSend').mockRejectedValue(new Error('nope'))

    const { result } = renderHook(() => useChatSocket(profile, null, false), { wrapper: AuthProvider })
    act(() => {
      result.current.sendMessage(PEER, 'retry me')
    })
    await waitFor(() => expect(result.current.conversations[PEER].messages[0].failed).toBe(true))
    const firstTempId = result.current.conversations[PEER].messages[0].clientTempId!

    act(() => {
      result.current.retrySend(PEER, firstTempId)
    })
    await waitFor(() => expect(result.current.conversations[PEER].messages[0].pending === true || result.current.conversations[PEER].messages[0].failed === true).toBe(true))
    expect(result.current.conversations[PEER].messages).toHaveLength(1)
    expect(result.current.conversations[PEER].messages[0].clientTempId).not.toBe(firstTempId)
    expect(result.current.conversations[PEER].messages[0].text).toBe('retry me')
  })
})
