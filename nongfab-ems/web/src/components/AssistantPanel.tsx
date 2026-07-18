import { useEffect, useId, useRef, useState } from 'react'
import {
  answerQuestionWithMood,
  ASSISTANT_INTENTS,
  TOP_LEVEL_OPTIONS,
  type AssistantMood,
  type AssistantOption,
} from '../lib/assistant'
import { findCategoryById, findGroupById, groupsForRole } from '../lib/assistantTopics'
import { useAuth } from '../lib/auth'
import { MASCOT_INTERACTIONS, type MascotInteraction } from '../lib/mascotInteractions'
import { speakText } from '../lib/tts'
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

// Shared by the greeting *and* every later category menu (see
// categoryMenuMessage below) - previously only the greeting carried these 4
// quick-reply chips, so options rendering only on the trailing message (by
// design, to fix the menu-stacking bug) meant they vanished for good the
// moment the visitor asked anything or picked a menu button, with no way
// back short of closing and reopening the panel (reported live 2026-07-18:
// "มี 4 คำถามตอนเริ่มต้นจะหายนะ"). Folding them into the category menu makes
// them reachable any time via the 📚 button instead of a one-shot greeting
// extra.
function starterOptions(): AssistantOption[] {
  return [
    ...QUICK_REPLY_QUESTIONS.map((q): AssistantOption => ({ kind: 'question', label: q, question: q })),
    ...TOP_LEVEL_OPTIONS,
  ]
}

function greeting(): ChatMessage {
  return {
    id: 'greeting',
    role: 'assistant',
    text: 'สวัสดีครับ ☀️ ผมชื่อ "น้อง Solar" ผู้ช่วย AI ของเว็บนี้ครับ ถามได้เลยว่าเว็บนี้ใช้งานยังไง หรือถามข้อมูลจริงในระบบ เช่น "ตอนนี้ผลิตไฟเท่าไหร่" ก็ได้ ' +
      'หรือกดเลือกหมวดคำถามด้านล่างนี้ก็ได้ครับ ถามได้เรื่อยๆ ไม่ต้องปิดหน้าต่างนี้เลย',
    options: starterOptions(),
  }
}

// Stable (not Date.now()-based) ids for every menu-level message - category,
// group, and sub-question menus alike - so navigating can tell "is this
// already on screen" and, more importantly, "is *some* menu already the
// trailing message" (see pushOrReplaceMenu below and isMenuMessageId).
const CATEGORY_MENU_ID = 'cat-menu'
const GROUP_MENU_ID_PREFIX = 'grp-'
const SUB_MENU_ID_PREFIX = 'sub-'

function isMenuMessageId(id: string): boolean {
  return id === CATEGORY_MENU_ID || id.startsWith(GROUP_MENU_ID_PREFIX) || id.startsWith(SUB_MENU_ID_PREFIX)
}

// Offered on every menu level (not just after a final answer) so a visitor
// is never stuck once they've picked a category or a topic group - reported
// 2026-07-18: picking "ความรู้ระบบ Solar" left no way back to browse other
// topics short of finding the small 📚 header icon.
const BACK_TO_CATEGORIES_OPTION: AssistantOption = { kind: 'categories', label: '📚 ดูหมวดคำถามอื่น' }

function categoryMenuMessage(): ChatMessage {
  return {
    id: CATEGORY_MENU_ID,
    role: 'assistant',
    text: 'อยากถามเรื่องอะไรดีครับ เลือกหมวดได้เลย:',
    options: starterOptions(),
  }
}

function groupMenuMessage(categoryId: string, role: string | null | undefined): ChatMessage | null {
  const category = findCategoryById(categoryId)
  if (!category) return null
  return {
    id: `${GROUP_MENU_ID_PREFIX}${categoryId}`,
    role: 'assistant',
    text: `หมวด "${category.title}" มีหัวข้ออะไรบ้าง เลือกได้เลยครับ:`,
    options: [
      ...groupsForRole(category, role).map((g): AssistantOption => ({ kind: 'group', label: g.title, groupId: g.id })),
      BACK_TO_CATEGORIES_OPTION,
    ],
  }
}

function subQuestionMenuMessage(groupId: string): ChatMessage | null {
  const group = findGroupById(groupId)
  if (!group) return null
  return {
    id: `${SUB_MENU_ID_PREFIX}${groupId}`,
    role: 'assistant',
    text: `"${group.title}" อยากรู้เรื่องไหนครับ:`,
    options: [
      ...group.subQuestions.map((sq): AssistantOption => ({ kind: 'question', label: sq.label, question: sq.question })),
      BACK_TO_CATEGORIES_OPTION,
    ],
  }
}

interface AssistantPanelProps {
  isOpen: boolean
  onClose: () => void
  /** Called with 'happy'/'sad' after every answer so AIAssistant.tsx can
   * make the mascot's face react (see MascotFace.tsx). */
  onAnswered?: (mood: AssistantMood) => void
  /** Called when a "เล่นกับน้อง Solar" button is tapped - AIAssistant.tsx
   * turns this into a mood + speech-bubble reaction on the floating mascot
   * itself (useMascotReaction.ts), not a chat message - playing with the
   * character is a separate, purely visual side-feature from the Q&A log. */
  onInteract?: (interaction: MascotInteraction) => void
}

export function AssistantPanel({ isOpen, onClose, onAnswered, onInteract }: AssistantPanelProps) {
  const { token, role } = useAuth()
  const [messages, setMessages] = useState<ChatMessage[]>([greeting()])
  const [input, setInput] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const [showPlay, setShowPlay] = useState(false)
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
      const { text, mood, options } = await answerQuestionWithMood(trimmed, { token, role })
      setMessages((prev) => [...prev, { id: `${Date.now()}-a`, role: 'assistant', text, options }])
      onAnswered?.(mood)
    } finally {
      setIsThinking(false)
    }
  }

  // Bouncing between "📚 back to categories" and picking a category/topic
  // used to append a brand-new menu bubble to the chat log on every single
  // tap - a burst of taps piled up an ever-growing wall of near-identical
  // menus with no way to remove the old ones (reported 2026-07-18: "กดย้ำๆ
  // ... มันซ้อนกันไปเรื่อยๆ เอาออกไม่ได้", and reported again the same day via
  // screen recording after a first fix that only covered one button tapped
  // repeatedly - not two different menu buttons alternated, which is what
  // the recording actually showed). As long as the visitor hasn't asked a
  // real question since, the trailing menu bubble is replaced in place
  // instead of stacking a new one below it; a real question/answer (or the
  // very first menu shown after one) still starts a fresh bubble as before.
  function pushOrReplaceMenu(menu: ChatMessage) {
    setMessages((prev) => {
      const last = prev[prev.length - 1]
      if (last && isMenuMessageId(last.id)) {
        return last.id === menu.id ? prev : [...prev.slice(0, -1), menu]
      }
      return [...prev, menu]
    })
  }

  function pushCategoryMenu() {
    pushOrReplaceMenu(categoryMenuMessage())
  }

  function handleOption(option: AssistantOption) {
    if (isThinking) return
    if (option.kind === 'question') {
      void send(option.question)
      return
    }
    if (option.kind === 'categories') {
      pushCategoryMenu()
      return
    }
    if (option.kind === 'category') {
      const menu = groupMenuMessage(option.categoryId, role)
      if (menu) pushOrReplaceMenu(menu)
      return
    }
    const menu = subQuestionMenuMessage(option.groupId)
    if (menu) pushOrReplaceMenu(menu)
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
          onClick={pushCategoryMenu}
          aria-label="เปิดหมวดคำถาม"
          title="หมวดคำถาม"
        >
          📚
        </button>
        <button
          type="button"
          className={showPlay ? 'assistant-panel-menu-button active' : 'assistant-panel-menu-button'}
          onClick={() => setShowPlay((v) => !v)}
          aria-label={showPlay ? 'ปิดแผงเล่นกับน้อง Solar' : 'เล่นกับน้อง Solar'}
          aria-pressed={showPlay}
          title="เล่นกับน้อง Solar"
        >
          🎮
        </button>
        <button type="button" className="assistant-panel-close" onClick={onClose} aria-label="ปิดหน้าต่างผู้ช่วย">
          ×
        </button>
      </header>

      {showPlay && (
        <div className="assistant-play-panel" role="group" aria-label="เล่นกับน้อง Solar">
          <p className="assistant-play-note">แกล้งน้อง Solar เล่นได้เลยครับ กดได้ไม่จำกัดเลย!</p>
          <div className="assistant-play-grid">
            {MASCOT_INTERACTIONS.map((interaction) => (
              <button
                key={interaction.id}
                type="button"
                className="assistant-play-option"
                onClick={() => onInteract?.(interaction)}
              >
                {interaction.label}
              </button>
            ))}
          </div>
        </div>
      )}

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
            {m.role === 'assistant' && (
              <button
                type="button"
                className="assistant-speak-button"
                onClick={() => speakText(m.text)}
                aria-label="ฟังเสียงข้อความนี้"
                title="ฟังเสียง"
              >
                🔊
              </button>
            )}
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
