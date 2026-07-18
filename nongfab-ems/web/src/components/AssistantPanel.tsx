import { useEffect, useId, useRef, useState } from 'react'
import {
  answerQuestionWithMood,
  ASSISTANT_INTENTS,
  TOP_LEVEL_OPTIONS,
  type AssistantMood,
  type AssistantOption,
} from '../lib/assistant'
import { findCategoryById, findGroupById } from '../lib/assistantTopics'
import { useAuth } from '../lib/auth'
import './AssistantPanel.css'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  /** Follow-up buttons shown under this message - only rendered for the
   * most recent message so old history doesn't clutter up with stale menus. */
  options?: AssistantOption[]
}

// A handful of one-tap starting points so a first-time visitor doesn't stare
// at a blank input not knowing what this thing can even answer - each maps
// to a real assistant.ts intent, not a decorative label. Shown alongside the
// 3 top-level browse categories so a visitor can either jump straight to a
// live-data answer or browse by topic.
const QUICK_REPLY_QUESTIONS = ['ตอนนี้ผลิตไฟเท่าไหร่', 'พยากรณ์พรุ่งนี้เป็นยังไง', 'หน้านี้ใช้งานยังไง', 'kWp คืออะไร']

function greeting(): ChatMessage {
  return {
    id: 'greeting',
    role: 'assistant',
    text: 'สวัสดีครับ ☀️ ผมชื่อ "น้อง Solar" ผู้ช่วย AI ของเว็บนี้ครับ ถามได้เลยว่าเว็บนี้ใช้งานยังไง หรือถามข้อมูลจริงในระบบ เช่น "ตอนนี้ผลิตไฟเท่าไหร่" ก็ได้ ' +
      'หรือกดเลือกหมวดคำถามด้านล่างนี้ก็ได้ครับ ถามได้เรื่อยๆ ไม่ต้องปิดหน้าต่างนี้เลย',
    options: [
      ...QUICK_REPLY_QUESTIONS.map((q): AssistantOption => ({ kind: 'question', label: q, question: q })),
      ...TOP_LEVEL_OPTIONS,
    ],
  }
}

function categoryMenuMessage(): ChatMessage {
  return {
    id: `${Date.now()}-cat`,
    role: 'assistant',
    text: 'อยากถามเรื่องอะไรดีครับ เลือกหมวดได้เลย:',
    options: TOP_LEVEL_OPTIONS,
  }
}

function groupMenuMessage(categoryId: string): ChatMessage | null {
  const category = findCategoryById(categoryId)
  if (!category) return null
  return {
    id: `${Date.now()}-grp`,
    role: 'assistant',
    text: `หมวด "${category.title}" มีหัวข้ออะไรบ้าง เลือกได้เลยครับ:`,
    options: category.groups.map((g): AssistantOption => ({ kind: 'group', label: g.title, groupId: g.id })),
  }
}

function subQuestionMenuMessage(groupId: string): ChatMessage | null {
  const group = findGroupById(groupId)
  if (!group) return null
  return {
    id: `${Date.now()}-sub`,
    role: 'assistant',
    text: `"${group.title}" อยากรู้เรื่องไหนครับ:`,
    options: group.subQuestions.map((sq): AssistantOption => ({ kind: 'question', label: sq.label, question: sq.question })),
  }
}

interface AssistantPanelProps {
  isOpen: boolean
  onClose: () => void
  /** Called with 'happy'/'sad' after every answer so AIAssistant.tsx can
   * make the mascot's face react (see MascotFace.tsx). */
  onAnswered?: (mood: AssistantMood) => void
}

export function AssistantPanel({ isOpen, onClose, onAnswered }: AssistantPanelProps) {
  const { token } = useAuth()
  const [messages, setMessages] = useState<ChatMessage[]>([greeting()])
  const [input, setInput] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const titleId = useId()

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, isThinking])

  // Keep the panel (and its input) above the on-screen keyboard on mobile -
  // without this, a fixed `bottom` offset stays put while the visual
  // viewport shrinks when the keyboard opens, which can push the input row
  // fully behind the keyboard. That reads exactly like "I can only ask one
  // question" (the bug reported 2026-07-18): after answering, the keyboard
  // re-opens on tapping the input, but now the send button is hidden behind
  // it with no obvious way to reach it again short of closing and reopening.
  useEffect(() => {
    if (!isOpen) return undefined
    const vv = window.visualViewport
    const panel = panelRef.current
    if (!vv || !panel) return undefined

    function updateKeyboardInset() {
      if (!panel || !vv) return
      const inset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop)
      panel.style.setProperty('--assistant-keyboard-inset', `${inset}px`)
    }

    updateKeyboardInset()
    vv.addEventListener('resize', updateKeyboardInset)
    vv.addEventListener('scroll', updateKeyboardInset)
    return () => {
      vv.removeEventListener('resize', updateKeyboardInset)
      vv.removeEventListener('scroll', updateKeyboardInset)
    }
  }, [isOpen])

  async function send(question: string) {
    const trimmed = question.trim()
    if (!trimmed || !token || isThinking) return

    setMessages((prev) => [...prev, { id: `${Date.now()}-u`, role: 'user', text: trimmed }])
    setInput('')
    setIsThinking(true)
    try {
      const { text, mood, options } = await answerQuestionWithMood(trimmed, { token })
      setMessages((prev) => [...prev, { id: `${Date.now()}-a`, role: 'assistant', text, options }])
      onAnswered?.(mood)
    } finally {
      setIsThinking(false)
    }
  }

  function handleOption(option: AssistantOption) {
    if (isThinking) return
    if (option.kind === 'question') {
      void send(option.question)
      return
    }
    if (option.kind === 'categories') {
      setMessages((prev) => [...prev, categoryMenuMessage()])
      return
    }
    if (option.kind === 'category') {
      const menu = groupMenuMessage(option.categoryId)
      if (menu) setMessages((prev) => [...prev, menu])
      return
    }
    const menu = subQuestionMenuMessage(option.groupId)
    if (menu) setMessages((prev) => [...prev, menu])
  }

  if (!isOpen) return null

  const lastMessageId = messages[messages.length - 1]?.id

  return (
    <section className="assistant-panel" role="dialog" aria-labelledby={titleId} aria-label="ผู้ช่วย AI น้อง Solar" ref={panelRef}>
      <header className="assistant-panel-header">
        <span id={titleId} className="assistant-panel-title">
          น้อง Solar - ผู้ช่วย AI 🤖
        </span>
        <button
          type="button"
          className="assistant-panel-menu-button"
          onClick={() => setMessages((prev) => [...prev, categoryMenuMessage()])}
          aria-label="เปิดหมวดคำถาม"
          title="หมวดคำถาม"
        >
          📚
        </button>
        <button type="button" className="assistant-panel-close" onClick={onClose} aria-label="ปิดหน้าต่างผู้ช่วย">
          ×
        </button>
      </header>

      <div className="assistant-panel-messages" ref={listRef}>
        {messages.map((m) => (
          <div key={m.id}>
            <div className={m.role === 'user' ? 'assistant-bubble assistant-bubble-user' : 'assistant-bubble assistant-bubble-bot'}>
              {m.text.split('\n').map((line, i) => (
                <span key={i}>
                  {line}
                  {i < m.text.split('\n').length - 1 && <br />}
                </span>
              ))}
            </div>
            {m.id === lastMessageId && m.options && m.options.length > 0 && !isThinking && (
              <div className="assistant-quick-replies">
                {m.options.map((opt, i) => (
                  <button key={`${opt.label}-${i}`} type="button" className="assistant-quick-reply" onClick={() => handleOption(opt)}>
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {isThinking && (
          <div className="assistant-bubble assistant-bubble-bot assistant-bubble-typing" aria-live="polite">
            กำลังพิมพ์…
          </div>
        )}
      </div>

      <form
        className="assistant-panel-input-row"
        onSubmit={(e) => {
          e.preventDefault()
          void send(input)
        }}
      >
        <input
          type="text"
          className="assistant-panel-input"
          placeholder="พิมพ์คำถาม..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          aria-label="พิมพ์คำถามถึงผู้ช่วย AI"
        />
        <button type="submit" className="assistant-panel-send" disabled={!input.trim() || isThinking}>
          ส่ง
        </button>
      </form>
      <p className="assistant-panel-note">
        ผู้ช่วยนี้ตอบจากชุดคำถามที่กำหนดไว้ล่วงหน้า ({ASSISTANT_INTENTS.length} หัวข้อ) ไม่ใช่ AI สนทนาอิสระ - ถามต่อเนื่องได้เรื่อยๆ
        กด 📚 เพื่อดูหมวดคำถามได้ทุกเมื่อครับ
      </p>
    </section>
  )
}
