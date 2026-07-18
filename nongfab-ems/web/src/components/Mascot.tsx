import { MascotFace, type MascotMood } from './MascotFace'
import './Mascot.css'

interface MascotProps {
  isOpen: boolean
  onToggle: () => void
  hasUnread?: boolean
  mood?: MascotMood
}

/** The floating sun mascot, bottom-right on every page - "น้อง Solar"
 * (he/him), and doubles as the AI assistant's open/close button (clicking
 * the character toggles the panel), rather than a separate icon button next
 * to it, since a mascot that does nothing when clicked would just be
 * confusing. `mood` (see MascotFace.tsx) is driven by AIAssistant.tsx based
 * on whether his last answer actually matched something. */
export function Mascot({ isOpen, onToggle, hasUnread, mood }: MascotProps) {
  return (
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
  )
}
