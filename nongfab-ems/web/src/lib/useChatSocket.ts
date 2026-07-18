import { useCallback, useEffect, useRef, useState } from 'react'
import { chatSocketUrl } from './api'
import { useAuth } from './auth'
import type { ChatEvent, ChatMessage } from './types'

const RECONNECT_DELAY_MS = 3000
const MAX_MESSAGES_KEPT = 200

export interface ChatSocketState {
  messages: ChatMessage[]
  onlineCount: number
  connected: boolean
  sendMessage: (text: string) => void
}

/** Owns the single site-wide `/ws/chat` connection: reconnects with a fixed
 * delay if the socket drops (a Railway redeploy, a flaky mobile connection),
 * and re-derives `messages`/`onlineCount` from the server's own `history`/
 * `message`/`presence` event types (see ws_chat.py) rather than trying to
 * track connect/disconnect state itself - the server is the source of truth
 * for who's online.
 */
export function useChatSocket(): ChatSocketState {
  const { token } = useAuth()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [onlineCount, setOnlineCount] = useState(0)
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)

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
        } else if (data.type === 'message') {
          setMessages((prev) => [...prev, data].slice(-MAX_MESSAGES_KEPT))
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
  }, [token])

  const sendMessage = useCallback((text: string) => {
    const trimmed = text.trim()
    if (!trimmed || socketRef.current?.readyState !== WebSocket.OPEN) return
    socketRef.current.send(JSON.stringify({ text: trimmed }))
  }, [])

  return { messages, onlineCount, connected, sendMessage }
}
