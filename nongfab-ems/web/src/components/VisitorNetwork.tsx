import { useEffect, useId, useRef, useState } from 'react'
import { avatarById, getOrCreateClientId, loadChatProfile, type ChatProfile } from '../lib/chatProfile'
import { useSubmitFeedback } from '../lib/queries'
import { decodeSticker, encodeSticker, speakSticker, STICKER_OPTIONS } from '../lib/stickers'
import { useChatSocket, type ChatSocketState, type Contact } from '../lib/useChatSocket'
import type { ChatMessage } from '../lib/types'
import { ChatProfileSetup } from './ChatProfileSetup'
import './VisitorNetwork.css'

type Tab = 'chat' | 'feedback'

const NOTIFICATION_AUTO_DISMISS_MS = 6000
const NOTIFICATION_PREVIEW_MAX_LENGTH = 60

interface IncomingNotification {
  /** The message's own id, not just the peer's client id - guarantees a
   * fresh notification always restarts its own auto-dismiss timer even if
   * the previous one was for the exact same peer. */
  messageId: number
  peerClientId: string
  displayName: string
  avatar: string | null
  preview: string
}

function notificationPreview(message: ChatMessage): string {
  const sticker = decodeSticker(message.text)
  if (sticker) return `ส่งสติกเกอร์ ${sticker.emoji} ${sticker.label}`
  return message.text.length > NOTIFICATION_PREVIEW_MAX_LENGTH
    ? `${message.text.slice(0, NOTIFICATION_PREVIEW_MAX_LENGTH)}…`
    : message.text
}

/** Floating bottom-left widget: private 1:1 visitor chat (pick someone from
 * the contact list, then talk - see useChatSocket.ts's docstring for why
 * this replaced the old single shared public room) plus a "message admin"
 * feedback form. Kept as one widget with two tabs (not several separate
 * floating buttons) so it doesn't visually compete with the mascot/AI
 * assistant already living in the opposite corner.
 *
 * Every role (including admin) goes through the same name/avatar picker
 * (chatProfile.ts) - the admin-specific "admin " name prefix is applied
 * server-side (ws_chat.py), not here, so this component doesn't need to
 * know or care which role it's rendering for.
 *
 * `useChatSocket()` is called exactly once, here, and threaded down to
 * `ChatTab` as props - calling it again inside `ChatTab` would open a
 * second, independent `/ws/chat` connection per mounted widget instead of
 * sharing the one this component already holds (caught by a real test:
 * online-user/message events sent to "the" socket weren't reaching the chat
 * tab, because it was listening on a different connection).
 */
export function VisitorNetwork() {
  const [isOpen, setIsOpen] = useState(false)
  const [tab, setTab] = useState<Tab>('chat')
  // Nobody can chat until a profile is saved once per browser (see
  // chatProfile.ts's module docstring for why - shared demo logins can't
  // tell two different real people apart by username alone).
  const [savedProfile, setSavedProfile] = useState<ChatProfile | null>(() => loadChatProfile())
  // Reopening the picker to change name/avatar while still logged in (the
  // pencil button below) must not discard the existing profile the way the
  // very-first-time flow does - it's a separate "currently editing" flag,
  // not a null-out-and-restart, so ProfileSetup can prefill the current
  // values instead of showing a blank form again.
  const [isEditingProfile, setIsEditingProfile] = useState(false)
  // null = showing the contact list ("who do you want to talk to"); a
  // client_id = that private thread is open. Reset whenever the panel is
  // closed so reopening always starts back at the contact list.
  const [selectedPeerClientId, setSelectedPeerClientId] = useState<string | null>(null)
  const isActiveView = isOpen && tab === 'chat'
  // Before a profile exists yet, useChatSocket still needs a stable
  // clientId (for its own-message/unread bookkeeping) even though nothing
  // can actually be sent until ProfileSetup is completed - the placeholder
  // name/avatar here are never sent, since the send form only renders once
  // `savedProfile` is non-null.
  const profileForSocket = savedProfile ?? { clientId: getOrCreateClientId(), displayName: '', avatarId: '' }
  // Who's messaging you, surfaced even while the whole widget is collapsed
  // (not just a badge count) - requested live 2026-07-18 alongside the
  // chat-history bug: a visitor closed on some other tab/page had no way to
  // notice someone had messaged them short of periodically reopening the
  // panel to check. `isOpenRef`/`tabRef`/`selectedPeerRef` mirror the latest
  // render's state into the onLiveMessage callback below without having to
  // recreate `chat` (and thus the whole WS connection setup) on every open/
  // close/tab-switch - `useChatSocket` already keeps its own callback ref
  // fresh the same way (see its `onLiveMessageRef`).
  const [notification, setNotification] = useState<IncomingNotification | null>(null)
  const notificationTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const isOpenRef = useRef(isOpen)
  isOpenRef.current = isOpen
  const tabRef = useRef(tab)
  tabRef.current = tab
  const selectedPeerRef = useRef(selectedPeerClientId)
  selectedPeerRef.current = selectedPeerClientId

  function dismissNotification() {
    clearTimeout(notificationTimerRef.current)
    setNotification(null)
  }

  const chat = useChatSocket(
    profileForSocket,
    selectedPeerClientId,
    isActiveView,
    (message) => {
      const isOwn = message.client_id === profileForSocket.clientId
      const peerClientId = isOwn ? message.recipient_client_id : message.client_id
      if (!peerClientId || isOwn) return

      // Speak a sticker's Thai caption aloud the moment it actually arrives
      // live, and only for the thread currently on screen - never for
      // replayed history, and never for a conversation the user isn't even
      // looking at.
      if (peerClientId === selectedPeerRef.current) {
        const sticker = decodeSticker(message.text)
        if (sticker) speakSticker(sticker)
      }

      // Already looking straight at this exact thread - the message bubble
      // itself is enough, a toast on top would just be noise.
      const alreadyViewing = isOpenRef.current && tabRef.current === 'chat' && selectedPeerRef.current === peerClientId
      if (alreadyViewing) return

      clearTimeout(notificationTimerRef.current)
      setNotification({ messageId: message.id, peerClientId, displayName: message.display_name, avatar: message.avatar, preview: notificationPreview(message) })
      notificationTimerRef.current = setTimeout(() => setNotification(null), NOTIFICATION_AUTO_DISMISS_MS)
    },
  )
  const { totalUnreadCount, contacts } = chat
  const onlineCount = contacts.filter((c) => c.online).length
  const titleId = useId()

  useEffect(() => () => clearTimeout(notificationTimerRef.current), [])

  function closePanel() {
    setIsOpen(false)
    setSelectedPeerClientId(null)
  }

  function openNotificationThread() {
    if (!notification) return
    const peerClientId = notification.peerClientId
    dismissNotification()
    setIsOpen(true)
    setTab('chat')
    setSelectedPeerClientId(peerClientId)
  }

  // Opening a peer's thread directly from the contact list (bypassing the
  // toast entirely) should also clear a still-showing notification for that
  // same peer - it would otherwise linger pointing at a conversation the
  // visitor is now already looking at.
  function selectPeer(peerClientId: string | null) {
    if (notification && peerClientId === notification.peerClientId) dismissNotification()
    setSelectedPeerClientId(peerClientId)
  }

  return (
    <>
      {notification && (
        <NotificationToast notification={notification} onClick={openNotificationThread} onDismiss={dismissNotification} />
      )}
      <button
        type="button"
        className="visitor-toggle"
        onClick={() => setIsOpen((v) => !v)}
        aria-label={isOpen ? 'ปิดหน้าต่างเครือข่ายผู้ชม' : 'เปิดหน้าต่างเครือข่ายผู้ชม'}
      >
        <ChatBubbleIcon />
        {totalUnreadCount > 0 && (
          <span className="visitor-unread-badge" aria-hidden="true">
            {totalUnreadCount > 99 ? '99+' : totalUnreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <section className="visitor-panel" role="dialog" aria-labelledby={titleId} aria-label="เครือข่ายผู้ชม">
          <header className="visitor-panel-header">
            <span id={titleId} className="visitor-panel-title">
              เครือข่ายผู้ชม 💬
            </span>
            <button type="button" className="visitor-panel-close" onClick={closePanel} aria-label="ปิดกล่องเครือข่ายผู้ชม">
              ×
            </button>
          </header>

          <div className="visitor-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'chat'}
              className={tab === 'chat' ? 'visitor-tab active' : 'visitor-tab'}
              onClick={() => setTab('chat')}
            >
              แชท {onlineCount > 0 && `(${onlineCount} ออนไลน์)`}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'feedback'}
              className={tab === 'feedback' ? 'visitor-tab active' : 'visitor-tab'}
              onClick={() => setTab('feedback')}
            >
              ติดต่อแอดมิน
            </button>
          </div>

          {tab === 'chat' ? (
            savedProfile && !isEditingProfile ? (
              <ChatTab
                chat={chat}
                profile={savedProfile}
                selectedPeerClientId={selectedPeerClientId}
                onSelectPeer={selectPeer}
                onEditProfile={() => setIsEditingProfile(true)}
              />
            ) : (
              <ChatProfileSetup
                initial={savedProfile}
                onSaved={(p) => {
                  setSavedProfile(p)
                  setIsEditingProfile(false)
                }}
                onCancel={savedProfile ? () => setIsEditingProfile(false) : undefined}
              />
            )
          ) : (
            <FeedbackTab />
          )}
        </section>
      )}
    </>
  )
}

function ChatTab({
  chat,
  profile,
  selectedPeerClientId,
  onSelectPeer,
  onEditProfile,
}: {
  chat: ChatSocketState
  profile: ChatProfile
  selectedPeerClientId: string | null
  onSelectPeer: (clientId: string | null) => void
  onEditProfile?: () => void
}) {
  const selectedContact = selectedPeerClientId ? chat.contacts.find((c) => c.clientId === selectedPeerClientId) : undefined

  if (selectedPeerClientId) {
    return (
      <ThreadView
        key={selectedPeerClientId}
        chat={chat}
        profile={profile}
        peerClientId={selectedPeerClientId}
        peerName={selectedContact?.displayName ?? 'ผู้ชม'}
        peerOnline={selectedContact?.online ?? false}
        onBack={() => onSelectPeer(null)}
      />
    )
  }

  return (
    <>
      <div className="visitor-contact-list">
        {chat.contacts.length === 0 && (
          <p className="visitor-empty">ยังไม่มีผู้ชมคนอื่นออนไลน์ตอนนี้ - รอสักครู่แล้วลองดูใหม่นะคะ</p>
        )}
        {chat.contacts.map((c) => (
          <ContactRow key={c.clientId} contact={c} unreadCount={chat.conversations[c.clientId]?.unreadCount ?? 0} onClick={() => onSelectPeer(c.clientId)} />
        ))}
      </div>
      {onEditProfile && (
        <button type="button" className="visitor-edit-profile" onClick={onEditProfile}>
          ✏️ {profile.displayName}
        </button>
      )}
    </>
  )
}

function NotificationToast({
  notification,
  onClick,
  onDismiss,
}: {
  notification: IncomingNotification
  onClick: () => void
  onDismiss: () => void
}) {
  const avatar = avatarById(notification.avatar)
  return (
    <div className="visitor-notification-toast" role="status">
      {/* Fixed aria-label (not the sender's name) on purpose - a name-based
          role query elsewhere in the app (e.g. picking a contact row by
          display name) must not accidentally match this toast too, since
          both a contact row and this toast can legitimately be on screen
          for the same sender at once. */}
      <button type="button" className="visitor-notification-body" aria-label="เปิดข้อความแจ้งเตือน" onClick={onClick}>
        <span className="visitor-avatar-circle visitor-notification-avatar" style={{ background: avatar.color }} aria-hidden="true">
          {avatar.emoji}
        </span>
        <span className="visitor-notification-text">
          <span className="visitor-notification-name">💬 {notification.displayName} ทักคุณมา</span>
          <span className="visitor-notification-preview">{notification.preview}</span>
        </span>
      </button>
      <button type="button" className="visitor-notification-close" onClick={onDismiss} aria-label="ปิดการแจ้งเตือน">
        ×
      </button>
    </div>
  )
}

function ContactRow({ contact, unreadCount, onClick }: { contact: Contact; unreadCount: number; onClick: () => void }) {
  const avatar = avatarById(contact.avatar)
  return (
    <button type="button" className="visitor-contact-row" onClick={onClick}>
      <span className="visitor-avatar-circle visitor-contact-avatar" style={{ background: avatar.color }} aria-hidden="true">
        {avatar.emoji}
      </span>
      <span className="visitor-contact-info">
        <span className="visitor-contact-name">{contact.displayName}</span>
        <span className={contact.online ? 'visitor-contact-status online' : 'visitor-contact-status'}>
          {contact.online ? '🟢 ออนไลน์' : 'ออฟไลน์'}
        </span>
      </span>
      {unreadCount > 0 && (
        <span className="visitor-contact-unread" aria-hidden="true">
          {unreadCount > 99 ? '99+' : unreadCount}
        </span>
      )}
    </button>
  )
}

function ThreadView({
  chat,
  profile,
  peerClientId,
  peerName,
  peerOnline,
  onBack,
}: {
  chat: ChatSocketState
  profile: ChatProfile
  peerClientId: string
  peerName: string
  peerOnline: boolean
  onBack: () => void
}) {
  const { conversations, sendMessage, connected, openConversation, loadOlder } = chat
  const conv = conversations[peerClientId]
  const messages = conv?.messages ?? []
  const hasMoreOlder = conv?.hasMoreOlder ?? true
  const loadingOlder = conv?.loadingOlder ?? false
  const [input, setInput] = useState('')
  const [showStickers, setShowStickers] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const prevScrollHeightRef = useRef(0)
  const wasNearBottomRef = useRef(true)

  useEffect(() => {
    openConversation(peerClientId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [peerClientId])

  function sendSticker(stickerId: string) {
    sendMessage(peerClientId, encodeSticker(stickerId))
    setShowStickers(false)
  }

  useEffect(() => {
    const el = listRef.current
    if (!el) return
    if (wasNearBottomRef.current) {
      el.scrollTop = el.scrollHeight
    } else {
      // A page of older messages was just prepended - keep the viewport
      // anchored to the same messages instead of jumping to the top.
      el.scrollTop = el.scrollHeight - prevScrollHeightRef.current
    }
  }, [messages])

  function handleScroll() {
    const el = listRef.current
    if (!el) return
    wasNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (el.scrollTop < 40 && hasMoreOlder && !loadingOlder) {
      prevScrollHeightRef.current = el.scrollHeight
      loadOlder(peerClientId)
    }
  }

  return (
    <>
      <div className="visitor-thread-header">
        <button type="button" className="visitor-thread-back" onClick={onBack} aria-label="กลับไปหน้ารายชื่อผู้ชม">
          ←
        </button>
        <span className="visitor-thread-peer-name">{peerName}</span>
        <span className={peerOnline ? 'visitor-contact-status online' : 'visitor-contact-status'}>{peerOnline ? '🟢 ออนไลน์' : 'ออฟไลน์'}</span>
      </div>
      <div className="visitor-messages" ref={listRef} onScroll={handleScroll}>
        {loadingOlder && <p className="visitor-loading-older">กำลังโหลดข้อความเก่า...</p>}
        {messages.length === 0 && <p className="visitor-empty">ยังไม่มีข้อความ - ทักทายผู้ชมคนนี้ได้เลยค่ะ</p>}
        {messages.map((m) => (
          <ChatBubble key={m.id} message={m} isOwn={m.client_id != null && m.client_id === profile.clientId} />
        ))}
      </div>
      {showStickers && (
        <div className="visitor-sticker-picker" role="group" aria-label="เลือกสติกเกอร์">
          {STICKER_OPTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              className="visitor-sticker-option"
              style={{ background: s.color }}
              disabled={!connected}
              onClick={() => sendSticker(s.id)}
              aria-label={`ส่งสติกเกอร์ ${s.label}`}
              title={s.label}
            >
              {s.emoji}
            </button>
          ))}
        </div>
      )}
      <form
        className="visitor-input-row"
        onSubmit={(e) => {
          e.preventDefault()
          sendMessage(peerClientId, input)
          setInput('')
        }}
      >
        <button
          type="button"
          className={showStickers ? 'visitor-sticker-toggle active' : 'visitor-sticker-toggle'}
          onClick={() => setShowStickers((v) => !v)}
          aria-label={showStickers ? 'ปิดแผงสติกเกอร์' : 'เปิดแผงสติกเกอร์'}
          aria-pressed={showStickers}
        >
          😊
        </button>
        <input
          type="text"
          className="visitor-input"
          placeholder={connected ? 'พิมพ์ข้อความ...' : 'กำลังเชื่อมต่อ...'}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={!connected}
          aria-label="พิมพ์ข้อความแชท"
        />
        <button type="submit" className="visitor-send" disabled={!connected || !input.trim()}>
          ส่ง
        </button>
      </form>
    </>
  )
}

function ChatBubble({ message, isOwn }: { message: ChatMessage; isOwn: boolean }) {
  const avatar = avatarById(message.avatar)
  const sticker = decodeSticker(message.text)

  return (
    <div className={isOwn ? 'visitor-bubble-row own' : 'visitor-bubble-row'}>
      {!isOwn && (
        <span className="visitor-avatar-circle" style={{ background: avatar.color }} aria-hidden="true">
          {avatar.emoji}
        </span>
      )}
      {sticker ? (
        <div className="visitor-sticker-bubble" aria-label={`สติกเกอร์: ${sticker.label}`}>
          {!isOwn && <span className="visitor-bubble-author">{message.display_name}</span>}
          <span className="visitor-sticker-bubble-emoji" style={{ background: sticker.color }}>
            {sticker.emoji}
          </span>
          <span className="visitor-sticker-bubble-caption">{sticker.label}</span>
        </div>
      ) : (
        <div className={isOwn ? 'visitor-bubble visitor-bubble-own' : 'visitor-bubble'}>
          {!isOwn && <span className="visitor-bubble-author">{message.display_name}</span>}
          <span className="visitor-bubble-text">{message.text}</span>
        </div>
      )}
    </div>
  )
}

function FeedbackTab() {
  const [text, setText] = useState('')
  const feedback = useSubmitFeedback()

  return (
    <form
      className="visitor-feedback-form"
      onSubmit={(e) => {
        e.preventDefault()
        if (!text.trim()) return
        feedback.mutate(text, { onSuccess: () => setText('') })
      }}
    >
      <p className="visitor-feedback-note">ส่งคำถามหรือความคิดเห็นถึงแอดมินโดยตรง - แอดมินจะเห็นข้อความนี้ในหน้าจัดการ</p>
      <textarea
        className="visitor-feedback-textarea"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="พิมพ์ข้อความถึงแอดมิน..."
        rows={5}
        aria-label="ข้อความถึงแอดมิน"
      />
      <button type="submit" className="visitor-send" disabled={feedback.isPending || !text.trim()}>
        {feedback.isPending ? 'กำลังส่ง...' : 'ส่งข้อความ'}
      </button>
      {feedback.isSuccess && <p className="visitor-feedback-success">ส่งข้อความเรียบร้อยแล้วค่ะ ขอบคุณค่ะ</p>}
      {feedback.isError && <p className="visitor-feedback-error">ส่งข้อความไม่สำเร็จ ลองใหม่อีกครั้งค่ะ</p>}
    </form>
  )
}

function ChatBubbleIcon() {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" fill="none" aria-hidden="true">
      <path
        d="M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H10l-5 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
        fill="var(--card-bg)"
      />
      <circle cx="8" cy="10" r="1.1" fill="currentColor" />
      <circle cx="12" cy="10" r="1.1" fill="currentColor" />
      <circle cx="16" cy="10" r="1.1" fill="currentColor" />
    </svg>
  )
}
