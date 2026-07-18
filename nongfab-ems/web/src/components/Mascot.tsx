import './Mascot.css'

interface MascotProps {
  isOpen: boolean
  onToggle: () => void
  hasUnread?: boolean
}

/** The floating sun mascot, bottom-right on every page - doubles as the AI
 * assistant's open/close button (clicking the character toggles the panel),
 * rather than a separate icon button next to it, since a mascot that does
 * nothing when clicked would just be confusing. Original character (not a
 * copy of any reference image) in the same kawaii-sun spirit the user asked
 * for: round gradient body, spiky rays, simple round eyes + smile, a soft
 * pulsing glow, and a slow side-to-side "looking around" idle animation
 * (kept gentle/slow on purpose - the same "don't make it dizzying"
 * sensibility as the weather strip's scroll speed). */
export function Mascot({ isOpen, onToggle, hasUnread }: MascotProps) {
  return (
    <button
      type="button"
      className="mascot-button"
      onClick={onToggle}
      aria-label={isOpen ? 'ปิดผู้ช่วย AI' : 'เปิดผู้ช่วย AI'}
      aria-expanded={isOpen}
    >
      <svg className="mascot-svg" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <defs>
          <radialGradient id="mascot-body-grad" cx="38%" cy="32%" r="75%">
            <stop offset="0%" stopColor="#ffe17d" />
            <stop offset="55%" stopColor="#ffc93d" />
            <stop offset="100%" stopColor="#ff9f1c" />
          </radialGradient>
          <radialGradient id="mascot-glow-grad" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ffd166" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#ffd166" stopOpacity="0" />
          </radialGradient>
        </defs>

        <circle className="mascot-glow" cx="60" cy="60" r="46" fill="url(#mascot-glow-grad)" />

        <g className="mascot-rotate">
          <g className="mascot-rays" fill="#ffc93d">
            <path d="M60 2 L66 22 L54 22 Z" />
            <path d="M60 118 L66 98 L54 98 Z" />
            <path d="M2 60 L22 66 L22 54 Z" />
            <path d="M118 60 L98 66 L98 54 Z" />
            <path d="M17 17 L33 27 L27 33 Z" />
            <path d="M103 103 L87 93 L93 87 Z" />
            <path d="M103 17 L87 27 L93 33 Z" />
            <path d="M17 103 L33 93 L27 87 Z" />
          </g>

          <circle cx="60" cy="60" r="34" fill="url(#mascot-body-grad)" stroke="#8a4b12" strokeWidth="2.2" />

          {/* shine highlight */}
          <ellipse cx="47" cy="47" rx="9" ry="6" fill="#fff5d6" opacity="0.75" transform="rotate(-25 47 47)" />

          <g className="mascot-blush" opacity="0.55">
            <ellipse cx="41" cy="70" rx="6" ry="3.4" fill="#ff7a52" />
            <ellipse cx="79" cy="70" rx="6" ry="3.4" fill="#ff7a52" />
          </g>

          <g className="mascot-eyes">
            <circle cx="49" cy="60" r="4.6" fill="#5b3210" />
            <circle cx="50.6" cy="58.4" r="1.4" fill="#fff" />
            <circle cx="71" cy="60" r="4.6" fill="#5b3210" />
            <circle cx="72.6" cy="58.4" r="1.4" fill="#fff" />
          </g>

          <path className="mascot-mouth" d="M52 71 Q60 78 68 71" fill="none" stroke="#8a4b12" strokeWidth="2.4" strokeLinecap="round" />
        </g>
      </svg>
      {hasUnread && <span className="mascot-badge" aria-hidden="true" />}
    </button>
  )
}
