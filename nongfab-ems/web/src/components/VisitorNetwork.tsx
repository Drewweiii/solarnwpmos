import { useEffect, useId, useRef, useState } from 'react'
import { AVATAR_OPTIONS, avatarById, getOrCreateClientId, loadChatProfile, saveChatProfile, type ChatProfile } from '../lib/chatProfile'
import { useSubmitFeedback } from '../lib/queries'
import { useChatSocket, type ChatSocketState } from '../lib/useChatSocket'
import type { ChatMessage } from '../lib/types'
import './VisitorNetwork.css'

type Tab = 'chat' | 'feedback'

/** Floating bottom-left widget: a single shared site-wide chat room plus a
 * "message admin" feedback form, per the user's explicit "everything -
 * real-time chat, presence, a contact form, and an admin feedback channel"
 * request. Kept as one widget with two tabs (not four separate floating
 * buttons) so it doesn't visually compete with the mascot/AI assistant
 * already living in the opposite corner.
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
 * presence/history events sent to "the" socket weren't reaching the chat
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
  const isActiveView = isOpen && tab === 'chat'
  // Before a profile exists yet, useChatSocket still needs a stable
  // clientId (for its own-message/unread bookkeeping) even though nothing
  // can actually be sent until ProfileSetup is completed - the placeholder
  // name/avatar here are never sent, since the send form only renders once
  // `savedProfile` is non-null.
  const chat = useChatSocket(savedProfile ?? { clientId: getOrCreateClientId(), displayName: '', avatarId: '' }, isActiveView && savedProfile != null)
  const { onlineCount, unreadCount } = chat
  const titleId = useId()

  return (
    <>
      <button
        type="button"
        className="visitor-toggle"
        onClick={() => setIsOpen((v) => !v)}
        aria-label={isOpen ? 'ปิดหน้าต่างเครือข่ายผู้ชม' : 'เปิดหน้าต่างเครือข่ายผู้ชม'}
      >
        <ChatBubbleIcon />
        {unreadCount > 0 && (
          <span className="visitor-unread-badge" aria-hidden="true">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <section className="visitor-panel" role="dialog" aria-labelledby={titleId} aria-label="เครือข่ายผู้ชม">
          <header className="visitor-panel-header">
            <span id={titleId} className="visitor-panel-title">
              เครือข่ายผู้ชม 💬
            </span>
            <button type="button" className="visitor-panel-close" onClick={() => setIsOpen(false)} aria-label="ปิดกล่องเครือข่ายผู้ชม">
              ×
            </button>
          </header>

          <div className="visitor-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={tab === 'chat'} className={tab === 'chat' ? 'visitor-tab active' : 'visitor-tab'} onClick={() => setTab('chat')}>
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
              <ChatTab chat={chat} profile={savedProfile} onEditProfile={() => setIsEditingProfile(true)} />
            ) : (
              <ProfileSetup
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

function ProfileSetup({
  initial,
  onSaved,
  onCancel,
}: {
  initial: ChatProfile | null
  onSaved: (profile: ChatProfile) => void
  onCancel?: () => void
}) {
  const [name, setName] = useState(initial?.displayName ?? '')
  const [avatarId, setAvatarId] = useState(initial?.avatarId ?? AVATAR_OPTIONS[0].id)

  return (
    <form
      className="visitor-profile-setup"
      onSubmit={(e) => {
        e.preventDefault()
        if (!name.trim()) return
        onSaved(saveChatProfile(name, avatarId))
      }}
    >
      <p className="visitor-profile-note">
        {initial
          ? 'แก้ไขชื่อและ avatar ที่จะแสดงในแชทค่ะ'
          : 'ตั้งชื่อและเลือก avatar ที่จะแสดงในแชท (เหมือน LINE) ก่อนเริ่มคุยกันค่ะ'}
      </p>
      <label className="visitor-profile-name-label" htmlFor="visitor-profile-name">
        ชื่อที่แสดง
      </label>
      <input
        id="visitor-profile-name"
        type="text"
        className="visitor-input"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="ชื่อของคุณ"
        maxLength={30}
      />
      <div className="visitor-avatar-grid" role="radiogroup" aria-label="เลือก avatar">
        {AVATAR_OPTIONS.map((a) => (
          <button
            key={a.id}
            type="button"
            role="radio"
            aria-checked={avatarId === a.id}
            aria-label={`avatar ${a.id}`}
            className={avatarId === a.id ? 'visitor-avatar-option selected' : 'visitor-avatar-option'}
            style={{ background: a.color }}
            onClick={() => setAvatarId(a.id)}
          >
            {a.emoji}
          </button>
        ))}
      </div>
      <button type="submit" className="visitor-send" disabled={!name.trim()}>
        {initial ? 'บันทึก' : 'เริ่มแชท'}
      </button>
      {onCancel && (
        <button type="button" className="visitor-profile-cancel" onClick={onCancel}>
          ยกเลิก
        </button>
      )}
    </form>
  )
}

function ChatTab({ chat, profile, onEditProfile }: { chat: ChatSocketState; profile: ChatProfile; onEditProfile?: () => void }) {
  const { messages, sendMessage, connected, hasMoreOlder, loadingOlder, loadOlder } = chat
  const [input, setInput] = useState('')
  const listRef = useRef<HTMLDivElement>(null)
  const prevScrollHeightRef = useRef(0)
  const wasNearBottomRef = useRef(true)

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
      loadOlder()
    }
  }

  return (
    <>
      <div className="visitor-messages" ref={listRef} onScroll={handleScroll}>
        {loadingOlder && <p className="visitor-loading-older">กำลังโหลดข้อความเก่า...</p>}
        {messages.length === 0 && <p className="visitor-empty">ยังไม่มีข้อความ - ทักทายผู้ชมคนอื่นได้เลยค่ะ</p>}
        {messages.map((m) => (
          <ChatBubble key={m.id} message={m} isOwn={m.client_id != null && m.client_id === profile.clientId} />
        ))}
      </div>
      {onEditProfile && (
        <button type="button" className="visitor-edit-profile" onClick={onEditProfile}>
          ✏️ {profile.displayName}
        </button>
      )}
      <form
        className="visitor-input-row"
        onSubmit={(e) => {
          e.preventDefault()
          sendMessage(input)
          setInput('')
        }}
      >
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
  return (
    <div className={isOwn ? 'visitor-bubble-row own' : 'visitor-bubble-row'}>
      {!isOwn && (
        <span className="visitor-avatar-circle" style={{ background: avatar.color }} aria-hidden="true">
          {avatar.emoji}
        </span>
      )}
      <div className={isOwn ? 'visitor-bubble visitor-bubble-own' : 'visitor-bubble'}>
        {!isOwn && <span className="visitor-bubble-author">{message.display_name}</span>}
        <span className="visitor-bubble-text">{message.text}</span>
      </div>
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
