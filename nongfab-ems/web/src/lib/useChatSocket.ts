import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { chatInbox, chatPresence, chatSend, getChatHistory } from './api'
import { useAuth } from './auth'
import type { ChatMessage, OnlineUser } from './types'
import type { ChatProfile } from './chatProfile'

// REST polling cadences (2026-07-20). The chat used to be a WebSocket, but in
// production its sends kept silently going nowhere (no delivery, no error) -
// reported repeatedly. This hook now drives everything over plain REST, the
// same request/response shape as the feedback flow that provably works: POST a
// heartbeat for presence, POST to send, GET to poll for new messages.
const PRESENCE_POLL_MS = 8000 // heartbeat + who's-online refresh
const INBOX_POLL_MS = 2500 // new-message poll (feels near-instant without hammering)
const MAX_MESSAGES_KEPT = 200
const LAST_READ_ID_KEY_PREFIX = 'nongfab_chat_last_read_id_'
const KNOWN_PEERS_KEY = 'nongfab_chat_known_peers'
// Matches ws_chat.py's HISTORY_LIMIT - both /chat/history and /chat/inbox
// return at most this many rows, so getting back fewer than this is how we
// know there's nothing older left for that pair.
const PAGE_SIZE = 50
// Optimistic messages need an id that sorts *after* every real DB id (small
// autoincrements) so they show at the bottom, yet is obviously not a real id
// (so markRead/unread math can skip them). A value near the top of the safe
// integer range does both.
const OPTIMISTIC_ID_BASE = Number.MAX_SAFE_INTEGER - 1_000_000
let optimisticSeq = 0

/** A message as held in local state: the server `ChatMessage` shape plus the
 * optimistic-send bookkeeping the UI needs. `pending` = shown instantly on
 * send, still waiting for the server's confirmation; `failed` = the send did
 * not go through and can be retried; `clientTempId` = ties an optimistic
 * bubble to its confirmed server copy. Confirmed/history messages carry none
 * of these. */
export interface LocalChatMessage extends ChatMessage {
  pending?: boolean
  failed?: boolean
  clientTempId?: string
}

function isOptimisticId(id: number): boolean {
  return id >= OPTIMISTIC_ID_BASE
}

/** A visitor this browser can start (or resume) a private conversation with
 * - either currently online (sourced from the presence poll) or someone
 * previously chatted with who has since gone offline (from this browser's own
 * local memory of who it has talked to). */
export interface Contact {
  clientId: string
  displayName: string
  avatar: string | null
  role: string | null
  online: boolean
}

export interface ConversationState {
  messages: LocalChatMessage[]
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
  retrySend: (peerClientId: string, clientTempId: string) => void
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

/** De-duplicated union of two message lists, sorted by id. */
function mergeMessagesById(a: LocalChatMessage[], b: LocalChatMessage[]): LocalChatMessage[] {
  const byId = new Map<number, LocalChatMessage>()
  for (const m of a) byId.set(m.id, m)
  for (const m of b) byId.set(m.id, m)
  return Array.from(byId.values()).sort((x, y) => x.id - y.id)
}

/** Owns the visitor's private-chat state, driven entirely by REST polling
 * (see the cadence constants above for why this replaced the WebSocket). The
 * returned interface is unchanged from the WebSocket version, so
 * VisitorNetwork.tsx doesn't care which transport is underneath.
 *
 * `activePeerClientId`/`isActiveView` tell this hook which conversation is
 * actually on screen - unread counting and "mark read" key off that pair,
 * LINE/Messenger-style. `onLiveMessage` fires only for genuinely new incoming
 * messages picked up by the poll (never history replay, never own sends), so
 * VisitorNetwork can play a sticker's voice / show a toast exactly once. */
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
  // Highest inbox id already ingested, and whether the first "catch-up" poll
  // has run - the first poll seeds this without firing notifications for
  // messages that arrived while the browser was closed.
  const lastInboxIdRef = useRef(0)
  const primedRef = useRef(false)

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

  /** Flip the still-pending optimistic bubble with this temp id to "failed"
   * (searches every conversation). No-op if already confirmed. */
  const markSendFailed = useCallback((clientTempId: string) => {
    setConversations((prev) => {
      let changed = false
      const next: Record<string, ConversationState> = {}
      for (const [peer, conv] of Object.entries(prev)) {
        const idx = conv.messages.findIndex((m) => m.clientTempId === clientTempId && m.pending)
        if (idx < 0) {
          next[peer] = conv
          continue
        }
        const messages = conv.messages.slice()
        messages[idx] = { ...messages[idx], pending: false, failed: true }
        next[peer] = { ...conv, messages }
        changed = true
      }
      return changed ? next : prev
    })
  }, [])

  // Looking at an open thread clears its unread badge (up to the newest real
  // message - never an optimistic id, which would poison later unread math).
  useEffect(() => {
    if (!isActiveView || !activePeerClientId) return
    const conv = conversations[activePeerClientId]
    if (!conv) return
    const lastReal = [...conv.messages].reverse().find((m) => !isOptimisticId(m.id))
    if (lastReal) markRead(activePeerClientId, lastReal.id)
  }, [isActiveView, activePeerClientId, conversations, markRead])

  // --- Polling loops (presence + inbox) -----------------------------------
  useEffect(() => {
    if (!token) return undefined
    let cancelled = false
    // Fresh session: re-catch-up from the start without notifying for old rows.
    primedRef.current = false
    lastInboxIdRef.current = 0

    async function pollPresence() {
      const p = profileRef.current
      if (cancelled || !p.clientId) return
      try {
        const { users } = await chatPresence({ clientId: p.clientId, displayName: p.displayName, avatarId: p.avatarId }, token!)
        if (cancelled) return
        setOnlineUsers(users)
        setConnected(true)
      } catch {
        // request() already routes a 401 through the logout handler; a transient
        // network error just means we retry on the next tick, so leave
        // `connected` as-is (never disable the composer over a blip).
      }
    }

    async function pollInbox() {
      const p = profileRef.current
      if (cancelled || !p.clientId) return
      let messages: ChatMessage[]
      try {
        const res = await chatInbox(p.clientId, lastInboxIdRef.current, token!)
        messages = res.messages
      } catch {
        return
      }
      if (cancelled) return
      const wasPrimed = primedRef.current
      primedRef.current = true
      if (messages.length === 0) return
      lastInboxIdRef.current = Math.max(lastInboxIdRef.current, ...messages.map((m) => m.id))

      const myClientId = p.clientId
      setConversations((prev) => {
        const next = { ...prev }
        for (const m of messages) {
          const isOwn = m.client_id === myClientId
          const peer = isOwn ? m.recipient_client_id : m.client_id
          if (!peer) continue
          const conv = next[peer] ?? emptyConversation()
          if (conv.messages.some((x) => x.id === m.id)) continue // already have it
          const isActiveThread = isActiveViewRef.current && activePeerRef.current === peer
          // On the first catch-up poll (wasPrimed=false) never bump unread -
          // those are pre-existing messages, not "new since you looked".
          const bumpUnread = wasPrimed && !isActiveThread && !isOwn
          next[peer] = {
            ...conv,
            messages: [...conv.messages, m].slice(-MAX_MESSAGES_KEPT),
            loaded: true,
            unreadCount: bumpUnread ? conv.unreadCount + 1 : conv.unreadCount,
          }
        }
        return next
      })

      for (const m of messages) {
        const isOwn = m.client_id === myClientId
        const peer = isOwn ? m.recipient_client_id : m.client_id
        if (!peer || isOwn) continue
        rememberPeer(peer, { displayName: m.display_name, avatar: m.avatar, role: m.role })
        if (wasPrimed) onLiveMessageRef.current?.(m)
      }
    }

    pollPresence()
    pollInbox()
    const presenceTimer = setInterval(pollPresence, PRESENCE_POLL_MS)
    const inboxTimer = setInterval(pollInbox, INBOX_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(presenceTimer)
      clearInterval(inboxTimer)
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
          // Merge, don't overwrite: an optimistic send or an inbox poll can land
          // in state while this fetch is in flight.
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

  const sendMessage = useCallback(
    (peerClientId: string, text: string) => {
      const trimmed = text.trim()
      if (!trimmed || !peerClientId) return
      const p = profileRef.current
      const clientTempId = `tmp-${Date.now()}-${optimisticSeq++}`

      // Optimistic bubble shown instantly (LINE/Messenger-style), never waiting
      // on the round-trip to reveal your own message.
      const optimistic: LocalChatMessage = {
        type: 'message',
        id: OPTIMISTIC_ID_BASE + optimisticSeq,
        username: '',
        role: '',
        text: trimmed,
        created_at: new Date().toISOString(),
        display_name: p.displayName,
        avatar: p.avatarId,
        client_id: p.clientId,
        recipient_client_id: peerClientId,
        pending: true,
        clientTempId,
      }
      setConversations((prev) => {
        const conv = prev[peerClientId] ?? emptyConversation()
        return { ...prev, [peerClientId]: { ...conv, messages: [...conv.messages, optimistic].slice(-MAX_MESSAGES_KEPT), loaded: true } }
      })

      if (!token) {
        markSendFailed(clientTempId)
        return
      }
      chatSend({ clientId: p.clientId, displayName: p.displayName, avatarId: p.avatarId }, peerClientId, trimmed, token)
        .then(({ message }) => {
          // Reconcile: swap the optimistic bubble for the confirmed server copy.
          setConversations((prev) => {
            const conv = prev[peerClientId]
            if (!conv) return prev
            let messages = conv.messages.filter((m) => m.clientTempId !== clientTempId)
            if (!messages.some((m) => m.id === message.id)) messages = [...messages, message]
            return { ...prev, [peerClientId]: { ...conv, messages: messages.slice(-MAX_MESSAGES_KEPT) } }
          })
        })
        .catch(() => markSendFailed(clientTempId))
    },
    [token, markSendFailed],
  )

  /** Retry a failed send: drop the failed bubble and send its text afresh. */
  const retrySend = useCallback(
    (peerClientId: string, clientTempId: string) => {
      const conv = conversationsRef.current[peerClientId]
      const failed = conv?.messages.find((m) => m.clientTempId === clientTempId)
      if (!failed) return
      setConversations((prev) => {
        const c = prev[peerClientId]
        if (!c) return prev
        return { ...prev, [peerClientId]: { ...c, messages: c.messages.filter((m) => m.clientTempId !== clientTempId) } }
      })
      sendMessage(peerClientId, failed.text)
    },
    [sendMessage],
  )

  const loadOlder = useCallback(
    (peerClientId: string) => {
      const conv = conversationsRef.current[peerClientId]
      if (!token || !conv || conv.loadingOlder || !conv.hasMoreOlder || conv.messages.length === 0) return
      setConversations((prev) => ({ ...prev, [peerClientId]: { ...prev[peerClientId], loadingOlder: true } }))
      const oldestReal = conv.messages.find((m) => !isOptimisticId(m.id))
      const oldestId = oldestReal ? oldestReal.id : conv.messages[0].id
      getChatHistory(profileRef.current.clientId, peerClientId, token, oldestId, PAGE_SIZE)
        .then(({ messages: older }) => {
          setConversations((prev) => {
            const current = prev[peerClientId]
            if (!current) return prev
            return {
              ...prev,
              [peerClientId]: {
                ...current,
                messages: mergeMessagesById(older, current.messages),
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

  // A live name/avatar edit heartbeats immediately so the rest of the room sees
  // it without waiting for the next presence tick.
  const updateProfile = useCallback(
    (displayName: string, avatarId: string) => {
      if (!token) return
      const p = profileRef.current
      chatPresence({ clientId: p.clientId, displayName, avatarId }, token)
        .then(({ users }) => setOnlineUsers(users))
        .catch(() => {})
    },
    [token],
  )

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

  return { contacts, connected, totalUnreadCount, conversations, openConversation, sendMessage, retrySend, loadOlder, updateProfile }
}
