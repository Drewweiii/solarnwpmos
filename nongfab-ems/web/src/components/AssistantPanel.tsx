import { useEffect, useId, useRef, useState } from 'react'
import { answerQuestionWithMood, ASSISTANT_INTENTS, type AssistantMood } from '../lib/assistant'
import { useAuth } from '../lib/auth'
import './AssistantPanel.css'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
}

const GREETING: ChatMessage = {
  id: 'greeting',
  role: 'assistant',
  text: 'สวัสดีครับ ☀️ ผมชื่อ "น้อง Solar" ผู้ช่วย AI ของเว็บนี้ครับ ถามได้เลยว่าเว็บนี้ใช้งานยังไง หรือถามข้อมูลจริงในระบบ เช่น "ตอนนี้ผลิตไฟเท่าไหร่" ครับ',
}

// A handful of one-tap starting points so a first-time visitor doesn't stare
// at a blank input not knowing what this thing can even answer - each maps
// to a real assistant.ts intent, not a decorative label.
const QUICK_REPLIES = ['ตอนนี้ผลิตไฟเท่าไหร่', 'พยากรณ์พรุ่งนี้เป็นยังไง', 'หน้านี้ใช้งานยังไง', 'kWp คืออะไร']

interface AssistantPanelProps {
  isOpen: boolean
  onClose: () => void
  /** Called with 'happy'/'sad' after every answer so AIAssistant.tsx can
   * make the mascot's face react (see MascotFace.tsx). */
  onAnswered?: (mood: AssistantMood) => void
}

export function AssistantPanel({ isOpen, onClose, onAnswered }: AssistantPanelProps) {
  const { token } = useAuth()
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING])
  const [input, setInput] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, isThinking])

  async function send(question: string) {
    const trimmed = question.trim()
    if (!trimmed || !token || isThinking) return

    setMessages((prev) => [...prev, { id: `${Date.now()}-u`, role: 'user', text: trimmed }])
    setInput('')
    setIsThinking(true)
    try {
      const { text, mood } = await answerQuestionWithMood(trimmed, { token })
      setMessages((prev) => [...prev, { id: `${Date.now()}-a`, role: 'assistant', text }])
      onAnswered?.(mood)
    } finally {
      setIsThinking(false)
    }
  }

  if (!isOpen) return null

  return (
    <section className="assistant-panel" role="dialog" aria-labelledby={titleId} aria-label="ผู้ช่วย AI น้อง Solar">
      <header className="assistant-panel-header">
        <span id={titleId} className="assistant-panel-title">
          น้อง Solar - ผู้ช่วย AI 🤖
        </span>
        <button type="button" className="assistant-panel-close" onClick={onClose} aria-label="ปิดหน้าต่างผู้ช่วย">
          ×
        </button>
      </header>

      <div className="assistant-panel-messages" ref={listRef}>
        {messages.map((m) => (
          <div key={m.id} className={m.role === 'user' ? 'assistant-bubble assistant-bubble-user' : 'assistant-bubble assistant-bubble-bot'}>
            {m.text.split('\n').map((line, i) => (
              <span key={i}>
                {line}
                {i < m.text.split('\n').length - 1 && <br />}
              </span>
            ))}
          </div>
        ))}
        {isThinking && (
          <div className="assistant-bubble assistant-bubble-bot assistant-bubble-typing" aria-live="polite">
            กำลังพิมพ์…
          </div>
        )}
      </div>

      {messages.length === 1 && (
        <div className="assistant-quick-replies">
          {QUICK_REPLIES.map((q) => (
            <button key={q} type="button" className="assistant-quick-reply" onClick={() => send(q)}>
              {q}
            </button>
          ))}
        </div>
      )}

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
        ผู้ช่วยนี้ตอบจากชุดคำถามที่กำหนดไว้ล่วงหน้า ({ASSISTANT_INTENTS.length} หมวด) ไม่ใช่ AI สนทนาอิสระ - ถ้าถามนอกเหนือจากนี้อาจตอบไม่ได้
      </p>
    </section>
  )
}
