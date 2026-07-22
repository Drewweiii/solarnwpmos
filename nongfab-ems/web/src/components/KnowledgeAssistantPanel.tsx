import { useEffect, useId, useRef, useState } from 'react'
import { answerFromKnowledge, type KnowledgePersona } from '../lib/knowledgeAssistant'
import type { MascotInteraction } from '../lib/mascotInteractions'
import { speakText } from '../lib/tts'
import './AssistantPanel.css'
import './KnowledgeAssistantPanel.css'

// The panel's own menu options - a flatter version of น้อง Solar's (personas
// have a single level of groups, no top-level categories): 'group' reveals a
// group's questions, 'question' asks it, 'groups' jumps back to the group
// list. All client-side, no network (knowledgeAssistant.ts is pure).
type PanelOption =
  | { kind: 'question'; label: string; question: string }
  | { kind: 'group'; label: string; groupId: string }
  | { kind: 'groups'; label: string }

interface PanelMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  options?: PanelOption[]
}

const GROUPS_MENU_ID = 'groups-menu'
const GROUP_MENU_PREFIX = 'grp-'

function isMenuId(id: string): boolean {
  return id === GROUPS_MENU_ID || id.startsWith(GROUP_MENU_PREFIX)
}

function groupsOption(): PanelOption {
  return { kind: 'groups', label: '📚 ดูหมวดอื่น' }
}

function groupChips(persona: KnowledgePersona): PanelOption[] {
  return persona.groups.map((g) => ({ kind: 'group', label: g.title, groupId: g.id }))
}

function greetingMessage(persona: KnowledgePersona): PanelMessage {
  return { id: 'greeting', role: 'assistant', text: persona.greeting, options: groupChips(persona) }
}

function groupsMenuMessage(persona: KnowledgePersona): PanelMessage {
  return { id: GROUPS_MENU_ID, role: 'assistant', text: 'อยากรู้หมวดไหนดีครับ 🤔 เลือกได้เลย:', options: groupChips(persona) }
}

function groupMenuMessage(persona: KnowledgePersona, groupId: string): PanelMessage | null {
  const group = persona.groups.find((g) => g.id === groupId)
  if (!group) return null
  return {
    id: `${GROUP_MENU_PREFIX}${groupId}`,
    role: 'assistant',
    text: `หมวด "${group.title}" อยากรู้เรื่องไหนครับ ❓:`,
    options: [...group.subQuestions.map((sq): PanelOption => ({ kind: 'question', label: sq.label, question: sq.question })), groupsOption()],
  }
}

interface KnowledgeAssistantPanelProps {
  persona: KnowledgePersona
  isOpen: boolean
  onClose: () => void
  /** Fired when a play button is tapped - the parent turns it into the
   * floating character's mood + speech-bubble reaction (same pattern as
   * น้อง Solar's AIAssistant.tsx). */
  onInteract?: (interaction: MascotInteraction) => void
}

export function KnowledgeAssistantPanel({ persona, isOpen, onClose, onInteract }: KnowledgeAssistantPanelProps) {
  const [messages, setMessages] = useState<PanelMessage[]>([greetingMessage(persona)])
  const [input, setInput] = useState('')
  const [showPlay, setShowPlay] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  // Reset the thread whenever we switch which persona this panel is showing,
  // so opening น้อง Cloud never shows น้อง Moon's leftover greeting/answers.
  useEffect(() => {
    setMessages([greetingMessage(persona)])
    setShowPlay(false)
  }, [persona])

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages])

  function send(question: string) {
    const trimmed = question.trim()
    if (!trimmed) return
    const reply = answerFromKnowledge(persona, trimmed)
    const suggestions: PanelOption[] = [
      ...reply.suggestions.map((sq): PanelOption => ({ kind: 'question', label: sq.label, question: sq.question })),
      groupsOption(),
    ]
    setMessages((prev) => [
      ...prev,
      { id: `${Date.now()}-u`, role: 'user', text: trimmed },
      { id: `${Date.now()}-a`, role: 'assistant', text: reply.text, options: suggestions },
    ])
    setInput('')
  }

  // Same in-place menu replacement as น้อง Solar's panel: bouncing between
  // group menus replaces the trailing menu bubble instead of stacking a new
  // one each tap (see AssistantPanel.tsx's pushOrReplaceMenu for the bug this
  // avoids).
  function pushOrReplaceMenu(menu: PanelMessage) {
    setMessages((prev) => {
      const last = prev[prev.length - 1]
      if (last && isMenuId(last.id)) return last.id === menu.id ? prev : [...prev.slice(0, -1), menu]
      return [...prev, menu]
    })
  }

  function handleOption(option: PanelOption) {
    if (option.kind === 'question') {
      send(option.question)
      return
    }
    if (option.kind === 'groups') {
      pushOrReplaceMenu(groupsMenuMessage(persona))
      return
    }
    const menu = groupMenuMessage(persona, option.groupId)
    if (menu) pushOrReplaceMenu(menu)
  }

  if (!isOpen) return null

  const lastId = messages[messages.length - 1]?.id

  return (
    <section
      className={`assistant-panel knowledge-assistant-panel knowledge-assistant-panel-${persona.id}`}
      role="dialog"
      aria-labelledby={titleId}
      aria-label={`ผู้ช่วย ${persona.name}`}
    >
      <header className="assistant-panel-header">
        <span id={titleId} className="assistant-panel-title">
          {persona.name} {persona.emoji}
        </span>
        <button
          type="button"
          className={showPlay ? 'assistant-panel-menu-button active' : 'assistant-panel-menu-button'}
          onClick={() => setShowPlay((v) => !v)}
          aria-label={showPlay ? `ปิดแผงเล่นกับ${persona.name}` : `เล่นกับ${persona.name}`}
          aria-pressed={showPlay}
          title={`เล่นกับ${persona.name}`}
        >
          🎮
        </button>
        <button type="button" className="assistant-panel-close" onClick={onClose} aria-label="ปิดหน้าต่างผู้ช่วย">
          ×
        </button>
      </header>

      {showPlay && (
        <div className="assistant-play-panel" role="group" aria-label={`เล่นกับ${persona.name}`}>
          <p className="assistant-play-note">แกล้ง{persona.name}เล่นได้เลยครับ กดได้ไม่จำกัด!</p>
          <div className="assistant-play-grid">
            {persona.play.map((interaction) => (
              <button key={interaction.id} type="button" className="assistant-play-option" onClick={() => onInteract?.(interaction)}>
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
              {m.text.split('\n').map((line, i, arr) => (
                <span key={i}>
                  {line}
                  {i < arr.length - 1 && <br />}
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
            {m.id === lastId && m.options && m.options.length > 0 && (
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
      </div>

      <form
        className="assistant-panel-input-row"
        onSubmit={(e) => {
          e.preventDefault()
          send(input)
        }}
      >
        <input
          type="text"
          className="assistant-panel-input"
          placeholder={`ถาม${persona.name}...`}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          aria-label={`พิมพ์คำถามถึง ${persona.name}`}
        />
        <button type="submit" className="assistant-panel-send" disabled={!input.trim()}>
          ส่ง
        </button>
      </form>
      <p className="assistant-panel-note">{persona.note}</p>
    </section>
  )
}
