import './Mascot.css'

export type MascotMood = 'idle' | 'happy' | 'sad'

interface MascotFaceProps {
  mood?: MascotMood
}

/** The pure visual character - "น้อง Solar" (he/him), a kawaii sun. Extracted
 * from the floating toggle button (Mascot.tsx) so the same artwork can be
 * reused anywhere else he needs to show up (the login welcome popup, the
 * chat profile setup form) without dragging along the button/toggle
 * semantics. Sizing is controlled entirely by the parent's CSS (the SVG
 * fills 100% of whatever box it's placed in).
 *
 * `mood` drives the facial expression: 'happy' (a wide grin + sparkles) when
 * the AI assistant just answered a question, 'sad' (a frown + a small tear)
 * when it couldn't, 'idle' (gentle default smile) otherwise.
 */
export function MascotFace({ mood = 'idle' }: MascotFaceProps) {
  const mouthPath =
    mood === 'happy'
      ? 'M45 68 Q60 88 75 68'
      : mood === 'sad'
        ? 'M50 77 Q60 68 70 77'
        : 'M52 71 Q60 78 68 71'

  return (
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

      {mood === 'happy' && (
        <g className="mascot-sparkles" fill="#fff3b0">
          <path d="M20 28 L22.5 35 L29.5 37.5 L22.5 40 L20 47 L17.5 40 L10.5 37.5 L17.5 35 Z" />
          <path d="M100 22 L101.8 27 L106.8 28.8 L101.8 30.6 L100 35.6 L98.2 30.6 L93.2 28.8 L98.2 27 Z" />
        </g>
      )}

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

        <g className="mascot-blush" opacity={mood === 'happy' ? 0.8 : 0.55}>
          <ellipse cx="41" cy="70" rx="6" ry="3.4" fill="#ff7a52" />
          <ellipse cx="79" cy="70" rx="6" ry="3.4" fill="#ff7a52" />
        </g>

        <g className="mascot-eyes">
          <circle cx="49" cy="60" r="4.6" fill="#5b3210" />
          <circle cx="50.6" cy="58.4" r="1.4" fill="#fff" />
          <circle cx="71" cy="60" r="4.6" fill="#5b3210" />
          <circle cx="72.6" cy="58.4" r="1.4" fill="#fff" />
        </g>

        {mood === 'sad' && <path d="M76 58 Q80 66 76 71 Q72 66 76 58 Z" fill="#6ec6ff" opacity="0.9" />}

        <path className="mascot-mouth" d={mouthPath} fill="none" stroke="#8a4b12" strokeWidth="2.4" strokeLinecap="round" />
      </g>
    </svg>
  )
}
