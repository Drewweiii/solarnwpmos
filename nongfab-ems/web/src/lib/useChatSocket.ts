import { useCallback, useEffect, useRef, useState } from 'react'
import { chatSocketUrl, getChatHistory } from './api'
import { useAuth } from './auth'
import type { ChatEvent, ChatMessage } from './types'
import type { ChatProfile } from './chatProfile'

const RECONNECT_DELAY_MS = 3000
const MAX_MESSAGES_KEPT = 200
const LAST_READ_ID_KEY = 'nongfab_chat_last_read_id'
// Matches ws_chat.py's HISTORY_LIMIT - both the initial `history` push and
// `GET /chat/history` return at most this many rows per page, so getting
// back fewer than this is how we know there's nothing older left to load.
const PAGE_SIZE = 50

export interface ChatSocketState {
  messages: ChatMessage[]
  onlineCount: number
  connected: boolean
  unreadCount: number
  hasMoreOlder: boolean
  loadingOlder: boolean
  sendMessage: (text: string) => void
  loadOlder: () => void
}

function loadLastReadId(): number {
  return Number(localStorage.getItem(LAST_READ_ID_KEY) ?? 0)
}

/** Owns the single site-wide `/ws/chat` connection: reconnects with a fixed
 * delay if the socket drops (a Railway redeploy, a flaky mobile connection),
 * and re-derives `messages`/`onlineCount` from the server's own `history`/
 * `message`/`presence` event types (see ws_chat.py) rather than trying to
 * track connect/disconnect state itself - the server is the source of truth
 * for who's online.
 *
 * `profile` (display name/avatar/client id - see chatProfile.ts) is sent
 * with every outgoing message so the server can persist and re-broadcast it
 * - the server still forces the admin identity itself regardless of what's
 * sent (ws_chat.py), so this is safe to pass even before a viewer/operator
 * has set up a profile (falls back to their raw username).
 *
 * `isActiveView` tells this hook whether the chat is actually being looked
 * at right now (panel open AND on the chat tab) - unread counting and
 * "mark read" both key off it, LINE/Messenger-style: a message that arrives
 * while the user is looking straight at the chat is never "unread".
 *
 * `onLiveMessage` (optional) fires only for messages that arrive via a live
 * `message` WebSocket event - never for the bulk `history` replay on
 * connect/scroll-back. This is what lets VisitorNetwork.tsx play a
 * sticker's voice line exactly once, right when it actually arrives,
 * instead of replaying every old sticker's sound on every history load.
 */
export function useChatSocket(profile: ChatProfile, isActiveView: boolean, onLiveMessage?: (message: ChatMessage) => void): ChatSocketState {
  const { token } = useAuth()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [onlineCount, setOnlineCount] = useState(0)
  const [connected, setConnected] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)
  const [hasMoreOlder, setHasMoreOlder] = useState(true)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)
  const profileRef = useRef(profile)
  profileRef.current = profile
  const isActiveViewRef = useRef(isActiveView)
  isActiveViewRef.current = isActiveView
  const onLiveMessageRef = useRef(onLiveMessage)
  onLiveMessageRef.current = onLiveMessage
  const lastReadIdRef = useRef(loadLastReadId())

  const markRead = useCallback((upToId: number) => {
    if (upToId > lastReadIdRef.current) {
      lastReadIdRef.current = upToId
      localStorage.setItem(LAST_READ_ID_KEY, String(upToId))
    }
    setUnreadCount(0)
  }, [])

  // Viewing the chat tab clears any unread badge immediately, and keeps
  // clearing it as further messages arrive while still being viewed (the
  // `messages`-keyed effect below handles that ongoing case).
  useEffect(() => {
    if (isActiveView && messages.length > 0) markRead(messages[messages.length - 1].id)
  }, [isActiveView, messages, markRead])

  useEffect(() => {
    if (!token) return undefined
    let cancelled = false
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined

    function connect() {
      if (cancelled) return
      const ws = new WebSocket(chatSocketUrl(token!))
      socketRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!cancelled) reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data as string) as ChatEvent
        if (data.type === 'history') {
          setMessages(data.messages)
          setHasMoreOlder(data.messages.length >= PAGE_SIZE)
        } else if (data.type === 'message') {
          setMessages((prev) => [...prev, data].slice(-MAX_MESSAGES_KEPT))
          onLiveMessageRef.current?.(data)
          const isOwn = data.client_id != null && data.client_id === profileRef.current.clientId
          if (isActiveViewRef.current) {
            markRead(data.id)
          } else if (!isOwn) {
            setUnreadCount((n) => n + 1)
          }
        } else if (data.type === 'presence') {
          setOnlineCount(data.count)
        }
      }
    }

    connect()
    return () => {
      cancelled = true
      clearTimeout(reconnectTimer)
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [token, markRead])

  const sendMessage = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || socketRef.current?.readyState !== WebSocket.OPEN) return
      const p = profileRef.current
      socketRef.current.send(JSON.stringify({ text: trimmed, display_name: p.displayName, avatar: p.avatarId, client_id: p.clientId }))
    },
    [],
  )

  const loadOlder = useCallback(() => {
    if (!token || loadingOlder || !hasMoreOlder || messages.length === 0) return
    setLoadingOlder(true)
    const oldestId = messages[0].id
    getChatHistory(oldestId, token, PAGE_SIZE)
      .then(({ messages: older }) => {
        setHasMoreOlder(older.length >= PAGE_SIZE)
        if (older.length > 0) setMessages((prev) => [...older, ...prev])
      })
      .finally(() => setLoadingOlder(false))
  }, [token, loadingOlder, hasMoreOlder, messages])

  return { messages, onlineCount, connected, unreadCount, hasMoreOlder, loadingOlder, sendMessage, loadOlder }
}
