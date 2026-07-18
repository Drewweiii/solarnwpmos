import { useEffect, useId, useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { useSubmitFeedback } from '../lib/queries'
import { useChatSocket, type ChatSocketState } from '../lib/useChatSocket'
import './VisitorNetwork.css'

type Tab = 'chat' | 'feedback'

/** Floating bottom-left widget: a single shared site-wide chat room plus a
 * "message admin" feedback form, per the user's explicit "everything -
 * real-time chat, presence, a contact form, and an admin feedback channel"
 * request. Kept as one widget with two tabs (not four separate floating
 * buttons) so it doesn't visually compete with the mascot/AI assistant
 * already living in the opposite corner.
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
  const chat = useChatSocket()
  const { onlineCount } = chat
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
        {onlineCount > 0 && (
          <span className="visitor-online-badge" aria-hidden="true">
            {onlineCount}
          </span>
        )}
      </button>

      {isOpen && (
        <section className="visitor-panel" role="dialog" aria-labelledby={titleId} aria-label="เครือข่ายผู้ชม">
          <header className="visitor-panel-header">
            <span id={titleId} className="visitor-panel-title">
              เครือข่ายผู้ชม 💬
            </span>
            <button type="button" className="visitor-panel-close" onClick={() => setIsOpen(false)} aria-label="ปิดหน้าต่างเครือข่ายผู้ชม">
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

          {tab === 'chat' ? <ChatTab chat={chat} /> : <FeedbackTab />}
        </section>
      )}
    </>
  )
}

function ChatTab({ chat }: { chat: ChatSocketState }) {
  const { username } = useAuth()
  const { messages, sendMessage, connected } = chat
  const [input, setInput] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages])

  return (
    <>
      <div className="visitor-messages" ref={listRef}>
        {messages.length === 0 && <p className="visitor-empty">ยังไม่มีข้อความ - ทักทายผู้ชมคนอื่นได้เลยค่ะ</p>}
        {messages.map((m) => (
          <div key={m.id} className={m.username === username ? 'visitor-bubble visitor-bubble-own' : 'visitor-bubble'}>
            <span className="visitor-bubble-author">{m.username}</span>
            <span className="visitor-bubble-text">{m.text}</span>
          </div>
        ))}
      </div>
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
