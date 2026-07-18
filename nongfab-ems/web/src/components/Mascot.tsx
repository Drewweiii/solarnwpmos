import { MascotFace, type MascotMood } from './MascotFace'
import './Mascot.css'

interface MascotProps {
  isOpen: boolean
  onToggle: () => void
  hasUnread?: boolean
  mood?: MascotMood
  /** Speech-bubble text from a "เล่นกับน้อง Solar" play interaction (see
   * AssistantPanel.tsx / useMascotReaction.ts) - null/undefined shows no
   * bubble. Rendered next to the mascot itself (not inside the chat panel)
   * so the reaction is visible right on the character being played with. */
  speech?: string | null
}

/** The floating sun mascot, bottom-right on every page - "น้อง Solar"
 * (he/him), and doubles as the AI assistant's open/close button (clicking
 * the character toggles the panel), rather than a separate icon button next
 * to it, since a mascot that does nothing when clicked would just be
 * confusing. `mood` (see MascotFace.tsx) is driven by AIAssistant.tsx based
 * on whether his last answer actually matched something, or by a play
 * interaction. */
export function Mascot({ isOpen, onToggle, hasUnread, mood, speech }: MascotProps) {
  return (
    <div className="mascot-wrap">
      {speech && (
        <div className="mascot-speech-bubble" role="status" aria-live="polite">
          {speech}
        </div>
      )}
      <button
        type="button"
        className="mascot-button"
        onClick={onToggle}
        aria-label={isOpen ? 'ปิดผู้ช่วย AI น้อง Solar' : 'เปิดผู้ช่วย AI น้อง Solar'}
        aria-expanded={isOpen}
      >
        <MascotFace mood={mood} />
        {hasUnread && <span className="mascot-badge" aria-hidden="true" />}
      </button>
    </div>
  )
}
