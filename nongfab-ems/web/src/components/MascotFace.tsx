import './Mascot.css'

export type MascotMood = 'idle' | 'happy' | 'sad' | 'blush' | 'hurt' | 'laugh' | 'wet' | 'love' | 'surprised' | 'excited'

interface MascotFaceProps {
  mood?: MascotMood
}

export const MOUTH_PATH: Record<MascotMood, string> = {
  idle: 'M52 71 Q60 78 68 71',
  happy: 'M45 68 Q60 88 75 68',
  sad: 'M50 77 Q60 68 70 77',
  blush: 'M51 71 Q60 76 69 71',
  hurt: 'M49 74 Q54 70 59 74 Q64 78 69 74',
  laugh: 'M46 67 Q60 90 74 67 Q60 76 46 67',
  wet: 'M51 76 Q60 72 69 76',
  love: 'M47 69 Q60 81 73 69',
  surprised: '', // rendered as a small <circle> instead - see below
  excited: 'M45 68 Q60 88 75 68',
}

// Which "family" of eyes each mood uses - grouped rather than 1:1 with mood
// so the visual language stays consistent (e.g. every shy/happy-ish mood
// gets the same closed "^ ^" eyes) instead of tuning 10 one-off shapes.
export type EyeStyle = 'normal' | 'closed' | 'squint' | 'wide' | 'heart' | 'star'

export const EYE_STYLE: Record<MascotMood, EyeStyle> = {
  idle: 'normal',
  happy: 'normal',
  sad: 'normal',
  blush: 'closed',
  hurt: 'squint',
  laugh: 'closed',
  wet: 'normal',
  love: 'heart',
  surprised: 'wide',
  excited: 'star',
}

/** The pure visual character - "น้อง Solar" (he/him), a kawaii sun. Extracted
 * from the floating toggle button (Mascot.tsx) so the same artwork can be
 * reused anywhere else he needs to show up (the login welcome popup, the
 * chat profile setup form) without dragging along the button/toggle
 * semantics. Sizing is controlled entirely by the parent's CSS (the SVG
 * fills 100% of whatever box it's placed in).
 *
 * `mood` drives the facial expression. Two families:
 * - AI-assistant-driven (unchanged since the original build): 'happy' (a
 *   wide grin + sparkles) after a real answer, 'sad' (a frown + a tear)
 *   after a fallback, 'idle' (gentle default smile) otherwise.
 * - "เล่นกับน้อง Solar" play-interaction-driven (2026-07-18, see
 *   mascotInteractions.ts / useMascotReaction.ts): 'blush' (pet head/hold
 *   hands/pinch cheek/flower - shy closed eyes + strong blush), 'hurt'
 *   (poke - squinty grimace + a little impact burst), 'laugh' (tickle -
 *   eyes squeezed shut, wide open mouth, joy-tears), 'wet' (rain - raindrops
 *   falling, a bit gloomy), 'love' (hug/flower - heart eyes, floating
 *   hearts), 'surprised' (jump-scare - wide eyes, small "o" mouth, motion
 *   burst), 'excited' (feed/cheer/high-five - star eyes, big grin, extra
 *   sparkles).
 */
export function MascotFace({ mood = 'idle' }: MascotFaceProps) {
  const mouthPath = MOUTH_PATH[mood]
  const eyeStyle = EYE_STYLE[mood]
  const blushOpacity = mood === 'blush' ? 1 : mood === 'happy' || mood === 'love' || mood === 'excited' ? 0.8 : 0.55

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

      {(mood === 'happy' || mood === 'excited') && (
        <g className="mascot-sparkles" fill="#fff3b0">
          <path d="M20 28 L22.5 35 L29.5 37.5 L22.5 40 L20 47 L17.5 40 L10.5 37.5 L17.5 35 Z" />
          <path d="M100 22 L101.8 27 L106.8 28.8 L101.8 30.6 L100 35.6 L98.2 30.6 L93.2 28.8 L98.2 27 Z" />
          {mood === 'excited' && <path d="M60 6 L61.6 11 L66.6 12.8 L61.6 14.6 L60 19.6 L58.4 14.6 L53.4 12.8 L58.4 11 Z" />}
        </g>
      )}

      {mood === 'love' && (
        <g className="mascot-floating-hearts" fill="#ff6b81">
          <path d="M24 20 C20 15 12 16 12 23 C12 29 24 37 24 37 C24 37 36 29 36 23 C36 16 28 15 24 20 Z" transform="scale(0.34) translate(10,10)" />
          <path
            d="M24 20 C20 15 12 16 12 23 C12 29 24 37 24 37 C24 37 36 29 36 23 C36 16 28 15 24 20 Z"
            transform="translate(78,10) scale(0.3) translate(10,10)"
          />
          <path
            d="M24 20 C20 15 12 16 12 23 C12 29 24 37 24 37 C24 37 36 29 36 23 C36 16 28 15 24 20 Z"
            transform="translate(46,-6) scale(0.26) translate(10,10)"
          />
        </g>
      )}

      {mood === 'wet' && (
        <g className="mascot-rain" fill="#6ec6ff">
          <path d="M18 8 Q22 16 18 22 Q14 16 18 8 Z" />
          <path d="M46 2 Q50 10 46 16 Q42 10 46 2 Z" />
          <path d="M76 4 Q80 12 76 18 Q72 12 76 4 Z" />
          <path d="M102 10 Q106 18 102 24 Q98 18 102 10 Z" />
        </g>
      )}

      {mood === 'surprised' && (
        <g className="mascot-burst" stroke="#ffb703" strokeWidth="2.4" strokeLinecap="round">
          <path d="M14 30 L22 34" />
          <path d="M106 30 L98 34" />
          <path d="M12 60 L21 60" />
          <path d="M108 60 L99 60" />
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

        <g className="mascot-blush" opacity={blushOpacity}>
          <ellipse cx="41" cy="70" rx="6" ry="3.4" fill="#ff7a52" />
          <ellipse cx="79" cy="70" rx="6" ry="3.4" fill="#ff7a52" />
        </g>

        {mood === 'hurt' && (
          <g className="mascot-impact" fill="none" stroke="#e85d04" strokeWidth="2" strokeLinecap="round">
            <path d="M26 62 L32 58" />
            <path d="M26 70 L32 72" />
            <path d="M22 66 L29 66" />
          </g>
        )}

        <EyePair style={eyeStyle} />

        {mood === 'laugh' && (
          <g className="mascot-joy-tears" fill="#6ec6ff">
            <path d="M45 65 Q47 70 45 74 Q43 70 45 65 Z" />
            <path d="M75 65 Q77 70 75 74 Q73 70 75 65 Z" />
          </g>
        )}

        {mood === 'sad' && <path d="M76 58 Q80 66 76 71 Q72 66 76 58 Z" fill="#6ec6ff" opacity="0.9" />}

        {mood === 'surprised' ? (
          <circle className="mascot-mouth" cx="60" cy="73" r="4.6" fill="#8a4b12" />
        ) : (
          <path className="mascot-mouth" d={mouthPath} fill="none" stroke="#8a4b12" strokeWidth="2.4" strokeLinecap="round" />
        )}
      </g>
    </svg>
  )
}

/** Exported so other characters sharing น้อง Solar's visual language (the
 * moon/cloud on the login screen, LoginMascotDecor.tsx) can draw matching
 * eyes without duplicating these SVG paths - only works out of the box for
 * a body drawn on the same 0-0-120-120 viewBox with eyes expected around
 * x=44-76/y=54-66, same as this file's own sun body. */
export function EyePair({ style }: { style: EyeStyle }) {
  if (style === 'closed') {
    return (
      <g className="mascot-eyes" fill="none" stroke="#5b3210" strokeWidth="2.4" strokeLinecap="round">
        <path d="M44 59 Q49 53 54 59" />
        <path d="M66 59 Q71 53 76 59" />
      </g>
    )
  }
  if (style === 'squint') {
    return (
      <g className="mascot-eyes" stroke="#5b3210" strokeWidth="2.6" strokeLinecap="round">
        <path d="M45 57 L53 61" />
        <path d="M75 57 L67 61" />
      </g>
    )
  }
  if (style === 'wide') {
    return (
      <g className="mascot-eyes">
        <circle cx="49" cy="60" r="6.5" fill="#5b3210" />
        <circle cx="50.8" cy="58" r="1.8" fill="#fff" />
        <circle cx="71" cy="60" r="6.5" fill="#5b3210" />
        <circle cx="72.8" cy="58" r="1.8" fill="#fff" />
      </g>
    )
  }
  if (style === 'heart') {
    return (
      <g className="mascot-eyes" fill="#ff6b81">
        <path d="M49 63.5 C44.5 59.5 44.5 55 49 56.8 C53.5 55 53.5 59.5 49 63.5 Z" />
        <path d="M71 63.5 C66.5 59.5 66.5 55 71 56.8 C75.5 55 75.5 59.5 71 63.5 Z" />
      </g>
    )
  }
  if (style === 'star') {
    return (
      <g className="mascot-eyes" fill="#5b3210">
        <path d="M49 54 L50.6 58.4 L55 60 L50.6 61.6 L49 66 L47.4 61.6 L43 60 L47.4 58.4 Z" />
        <path d="M71 54 L72.6 58.4 L77 60 L72.6 61.6 L71 66 L69.4 61.6 L65 60 L69.4 58.4 Z" />
      </g>
    )
  }
  return (
    <g className="mascot-eyes">
      <circle cx="49" cy="60" r="4.6" fill="#5b3210" />
      <circle cx="50.6" cy="58.4" r="1.4" fill="#fff" />
      <circle cx="71" cy="60" r="4.6" fill="#5b3210" />
      <circle cx="72.6" cy="58.4" r="1.4" fill="#fff" />
    </g>
  )
}
