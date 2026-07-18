import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { chatSocketUrl, getChatHistory } from './api'
import { useAuth } from './auth'
import type { ChatEvent, ChatMessage, OnlineUser } from './types'
import type { ChatProfile } from './chatProfile'

const RECONNECT_DELAY_MS = 3000
const MAX_MESSAGES_KEPT = 200
const LAST_READ_ID_KEY_PREFIX = 'nongfab_chat_last_read_id_'
const KNOWN_PEERS_KEY = 'nongfab_chat_known_peers'
// Matches ws_chat.py's HISTORY_LIMIT - both the `GET /chat/history` initial
// load and "load older" page return at most this many rows, so getting back
// fewer than this is how we know there's nothing older left for that pair.
const PAGE_SIZE = 50

/** A visitor this browser can start (or resume) a private conversation with
 * - either currently online (`online: true`, sourced live from the server's
 * online-users list) or someone previously chatted with who has since gone
 * offline (`online: false`, sourced from this browser's own local memory of
 * who it has talked to - the server has no "everyone I've ever messaged"
 * endpoint, only per-pair history once both ids are already known). This is
 * what the contact list (VisitorNetwork.tsx) picks a chat partner from -
 * "who's online" is only half of it, since a conversation shouldn't vanish
 * from the list the moment the other person closes their tab.
 */
export interface Contact {
  clientId: string
  displayName: string
  avatar: string | null
  role: string | null
  online: boolean
}

export interface ConversationState {
  messages: ChatMessage[]
  loaded: boolean
  hasMoreOlder: boolean
  loadingOlder: boolean
  unreadCount: number
}

export interface ChatSocketState {
  contacts: Contact[]
  connected: boolean
  totalUnreadCount: number
  conversations: Record<string, ConversationState>
  openConversation: (peerClientId: string) => void
  sendMessage: (peerClientId: string, text: string) => void
  loadOlder: (peerClientId: string) => void
  updateProfile: (displayName: string, avatarId: string) => void
}

function loadLastReadId(peerClientId: string): number {
  return Number(localStorage.getItem(LAST_READ_ID_KEY_PREFIX + peerClientId) ?? 0)
}
function saveLastReadId(peerClientId: string, id: number): void {
  localStorage.setItem(LAST_READ_ID_KEY_PREFIX + peerClientId, String(id))
}

type KnownPeerInfo = { displayName: string; avatar: string | null; role: string | null }
type KnownPeerRecord = Record<string, KnownPeerInfo>

function loadKnownPeers(): KnownPeerRecord {
  try {
    const raw = localStorage.getItem(KNOWN_PEERS_KEY)
    return raw ? (JSON.parse(raw) as KnownPeerRecord) : {}
  } catch {
    return {}
  }
}
function saveKnownPeers(peers: KnownPeerRecord): void {
  localStorage.setItem(KNOWN_PEERS_KEY, JSON.stringify(peers))
}

const emptyConversation = (): ConversationState => ({ messages: [], loaded: false, hasMoreOlder: true, loadingOlder: false, unreadCount: 0 })

/** De-duplicated union of two message lists, sorted by id (the DB's own
 * autoincrement, globally monotonic across every conversation - safe to sort
 * on directly). Root-caused 2026-07-18 from a screen recording showing a
 * message that visibly got sent (input cleared) but never appeared: opening
 * a thread fires `GET /chat/history` and, in parallel, the visitor's own
 * send gets WS-echoed back almost immediately (same open connection, no
 * HTTP/auth/DB round trip) - if the still-in-flight history fetch resolves
 * *after* that echo already appended the new message to state, its plain
 * `messages: [...history]` overwrite used to wipe the just-sent message
 * straight back out. Merging instead of overwriting keeps whichever source
 * saw a given message first. */
function mergeMessagesById(a: ChatMessage[], b: ChatMessage[]): ChatMessage[] {
  const byId = new Map<number, ChatMessage>()
  for (const m of a) byId.set(m.id, m)
  for (const m of b) byId.set(m.id, m)
  return Array.from(byId.values()).sort((x, y) => x.id - y.id)
}

/** Owns the single site-wide `/ws/chat` connection plus every open private
 * conversation derived from it. This used to be one shared public room
 * (`onlineCount`/`messages` flat arrays) - reworked 2026-07-18 into private
 * 1:1 messaging (see ws_chat.py's module docstring for why: broadcasting
 * every message to every visitor was a real privacy problem, not just a UX
 * one). The server now only ever pushes two event types: `online_users`
 * (who's connected right now) and `message` (addressed to exactly one
 * `recipient_client_id`) - there is no more bulk `history` push on connect,
 * since history only makes sense once a specific conversation pair is known
 * (`openConversation` fetches it via `GET /chat/history`).
 *
 * `profile` (display name/avatar/client id - see chatProfile.ts) is sent as
 * WS query params at connect time and again via `type: "update_profile"` on
 * a live edit - the server still forces the admin identity itself
 * regardless of what's sent (ws_chat.py), so this is safe to pass even
 * before a viewer/operator has set up a profile (falls back to their raw
 * username).
 *
 * `activePeerClientId`/`isActiveView` together tell this hook which
 * conversation (if any) is actually being looked at right now - unread
 * counting and "mark read" both key off that pair, LINE/Messenger-style: a
 * message that arrives while its thread is open on screen is never
 * "unread". `activePeerClientId` is `null` while the contact-list view
 * itself is showing (no thread open yet).
 *
 * `onLiveMessage` (optional) fires only for messages that arrive via a live
 * `message` WebSocket event - never for `GET /chat/history` replay. This is
 * what lets VisitorNetwork.tsx play a sticker's voice line exactly once,
 * right when it actually arrives, instead of replaying every old sticker's
 * sound whenever a thread is (re)opened.
 */
export function useChatSocket(
  profile: ChatProfile,
  activePeerClientId: string | null,
  isActiveView: boolean,
  onLiveMessage?: (message: ChatMessage) => void,
): ChatSocketState {
  const { token } = useAuth()
  const [onlineUsers, setOnlineUsers] = useState<OnlineUser[]>([])
  const [connected, setConnected] = useState(false)
  const [conversations, setConversations] = useState<Record<string, ConversationState>>({})
  const [knownPeers, setKnownPeers] = useState<KnownPeerRecord>(() => loadKnownPeers())
  const socketRef = useRef<WebSocket | null>(null)
  const profileRef = useRef(profile)
  profileRef.current = profile
  const activePeerRef = useRef(activePeerClientId)
  activePeerRef.current = activePeerClientId
  const isActiveViewRef = useRef(isActiveView)
  isActiveViewRef.current = isActiveView
  const onLiveMessageRef = useRef(onLiveMessage)
  onLiveMessageRef.current = onLiveMessage
  const onlineUsersRef = useRef<OnlineUser[]>(onlineUsers)
  onlineUsersRef.current = onlineUsers
  const conversationsRef = useRef(conversations)
  conversationsRef.current = conversations

  const rememberPeer = useCallback((clientId: string, info: KnownPeerInfo) => {
    setKnownPeers((prev) => {
      const existing = prev[clientId]
      if (existing && existing.displayName === info.displayName && existing.avatar === info.avatar && existing.role === info.role) {
        return prev
      }
      const next = { ...prev, [clientId]: info }
      saveKnownPeers(next)
      return next
    })
  }, [])

  const markRead = useCallback((peerClientId: string, upToId: number) => {
    if (upToId > loadLastReadId(peerClientId)) saveLastReadId(peerClientId, upToId)
    setConversations((prev) => {
      const conv = prev[peerClientId]
      if (!conv || conv.unreadCount === 0) return prev
      return { ...prev, [peerClientId]: { ...conv, unreadCount: 0 } }
    })
  }, [])

  // Looking straight at an open thread clears its unread badge immediately,
  // and keeps clearing it as further messages arrive while still open (the
  // `message` handler below covers that ongoing case for new arrivals).
  useEffect(() => {
    if (!isActiveView || !activePeerClientId) return
    const conv = conversations[activePeerClientId]
    if (conv && conv.messages.length > 0) markRead(activePeerClientId, conv.messages[conv.messages.length - 1].id)
  }, [isActiveView, activePeerClientId, conversations, markRead])

  useEffect(() => {
    if (!token) return undefined
    let cancelled = false
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined

    function connect() {
      if (cancelled) return
      const p = profileRef.current
      const ws = new WebSocket(chatSocketUrl(token!, p.clientId, p.displayName, p.avatarId))
      socketRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!cancelled) reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data as string) as ChatEvent
        if (data.type === 'online_users') {
          setOnlineUsers(data.users)
          return
        }
        // data.type === 'message'
        const myClientId = profileRef.current.clientId
        const isOwn = data.client_id === myClientId
        const peerClientId = isOwn ? data.recipient_client_id : data.client_id
        if (!peerClientId) return
        if (!isOwn) rememberPeer(peerClientId, { displayName: data.display_name, avatar: data.avatar, role: data.role })

        const isActiveThread = isActiveViewRef.current && activePeerRef.current === peerClientId
        setConversations((prev) => {
          const conv = prev[peerClientId] ?? emptyConversation()
          return {
            ...prev,
            [peerClientId]: {
              ...conv,
              messages: [...conv.messages, data].slice(-MAX_MESSAGES_KEPT),
              loaded: true,
              unreadCount: isActiveThread || isOwn ? 0 : conv.unreadCount + 1,
            },
          }
        })
        if (isActiveThread || isOwn) saveLastReadId(peerClientId, data.id)
        onLiveMessageRef.current?.(data)
      }
    }

    connect()
    return () => {
      cancelled = true
      clearTimeout(reconnectTimer)
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [token, rememberPeer])

  const openConversation = useCallback(
    (peerClientId: string) => {
      if (!token) return
      const onlineInfo = onlineUsersRef.current.find((u) => u.client_id === peerClientId)
      if (onlineInfo) rememberPeer(peerClientId, { displayName: onlineInfo.display_name, avatar: onlineInfo.avatar, role: onlineInfo.role })

      if (conversationsRef.current[peerClientId]?.loaded) return
      setConversations((prev) => (prev[peerClientId] ? prev : { ...prev, [peerClientId]: emptyConversation() }))
      getChatHistory(profileRef.current.clientId, peerClientId, token, undefined, PAGE_SIZE).then(({ messages }) => {
        const lastRead = loadLastReadId(peerClientId)
        const unreadCount = messages.filter((m) => m.id > lastRead && m.client_id !== profileRef.current.clientId).length
        setConversations((prev) => {
          // Merge, don't overwrite: a live WS echo of the visitor's own just-
          // sent message can land in state *while this fetch is still in
          // flight* (see mergeMessagesById's own comment) - blindly
          // replacing `messages` here would silently erase it again.
          const merged = mergeMessagesById(messages, prev[peerClientId]?.messages ?? [])
          return {
            ...prev,
            [peerClientId]: { messages: merged, loaded: true, hasMoreOlder: messages.length >= PAGE_SIZE, loadingOlder: false, unreadCount },
          }
        })
      })
    },
    [token, rememberPeer],
  )

  const sendMessage = useCallback((peerClientId: string, text: string) => {
    const trimmed = text.trim()
    if (!trimmed || !peerClientId || socketRef.current?.readyState !== WebSocket.OPEN) return
    const p = profileRef.current
    socketRef.current.send(
      JSON.stringify({ text: trimmed, recipient_client_id: peerClientId, display_name: p.displayName, avatar: p.avatarId }),
    )
  }, [])

  const loadOlder = useCallback(
    (peerClientId: string) => {
      const conv = conversationsRef.current[peerClientId]
      if (!token || !conv || conv.loadingOlder || !conv.hasMoreOlder || conv.messages.length === 0) return
      setConversations((prev) => ({ ...prev, [peerClientId]: { ...prev[peerClientId], loadingOlder: true } }))
      const oldestId = conv.messages[0].id
      getChatHistory(profileRef.current.clientId, peerClientId, token, oldestId, PAGE_SIZE)
        .then(({ messages: older }) => {
          setConversations((prev) => {
            const current = prev[peerClientId]
            if (!current) return prev
            return {
              ...prev,
              [peerClientId]: {
                ...current,
                messages: [...older, ...current.messages],
                hasMoreOlder: older.length >= PAGE_SIZE,
                loadingOlder: false,
              },
            }
          })
        })
        .catch(() => {
          setConversations((prev) => (prev[peerClientId] ? { ...prev, [peerClientId]: { ...prev[peerClientId], loadingOlder: false } } : prev))
        })
    },
    [token],
  )

  const updateProfile = useCallback((displayName: string, avatarId: string) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) return
    socketRef.current.send(JSON.stringify({ type: 'update_profile', display_name: displayName, avatar: avatarId }))
  }, [])

  const contacts = useMemo<Contact[]>(() => {
    const myClientId = profile.clientId
    const byId = new Map<string, Contact>()
    for (const u of onlineUsers) {
      if (u.client_id === myClientId) continue
      byId.set(u.client_id, { clientId: u.client_id, displayName: u.display_name, avatar: u.avatar, role: u.role, online: true })
    }
    for (const [clientId, info] of Object.entries(knownPeers)) {
      if (clientId === myClientId || byId.has(clientId)) continue
      byId.set(clientId, { clientId, displayName: info.displayName, avatar: info.avatar, role: info.role, online: false })
    }
    return Array.from(byId.values()).sort((a, b) => {
      if (a.online !== b.online) return a.online ? -1 : 1
      return a.displayName.localeCompare(b.displayName, 'th')
    })
  }, [onlineUsers, knownPeers, profile.clientId])

  const totalUnreadCount = useMemo(
    () => Object.values(conversations).reduce((sum, c) => sum + c.unreadCount, 0),
    [conversations],
  )

  return { contacts, connected, totalUnreadCount, conversations, openConversation, sendMessage, loadOlder, updateProfile }
}
