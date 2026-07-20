import { useEffect, useRef, useState, type CSSProperties, type ReactElement } from 'react'
import { CloudFace } from './CloudFace'
import type { MascotMood } from './MascotFace'
import { MascotFace } from './MascotFace'
import { MoonFace } from './MoonFace'
import './LoginMascotDecor.css'

export type LoginFocusedField = 'username' | 'password' | null

type CharacterKey = 'sun' | 'moon' | 'cloud'

// How long a poked character stays in its shy "dart away then come back"
// animation - must match the login-mascot-flee keyframe duration in the CSS so
// the class is removed exactly when the character has settled back.
const FLEE_DURATION_MS = 1250

interface LoginMascotDecorProps {
  focusedField: LoginFocusedField
}

/** Login screen's left-side decoration (2026-07-18) - replaces what used to
 * be a symmetric solar-system motif (LoginSolarDecor.tsx, still used
 * unchanged on the right side) with น้อง Solar, a moon, and a cloud that
 * react to which field the visitor is filling in, based on a reference clip
 * the user shared: characters "watch" the username field while it's being
 * typed and look away (closed eyes) while the password field is focused, so
 * it never reads as if they're peeking at a password. Approved live by the
 * user, including the specific approach: React state via onFocus/onBlur
 * (lifted in Login.tsx, passed down as `focusedField`) + CSS/SVG transforms
 * only - no physics engine, no canvas. The idle "randomized angle/position"
 * flourish the user also asked for is a continuous gentle per-character
 * wobble (`--wobble-*` CSS custom properties randomized once on mount, see
 * LoginMascotDecor.css) rather than a literal "knocked over into a pile"
 * animation from the reference clip - that would need a real trigger design
 * and risks looking janky without an actual physics engine, which was
 * explicitly the thing being avoided here.
 *
 * Purely decorative - `aria-hidden`, `pointer-events: none` throughout,
 * hidden below the same 1020px breakpoint as LoginSolarDecor (no spare
 * margin to decorate on a narrow screen, and this must never reintroduce
 * the horizontal-overflow bug fixed 2026-07-18 in App.css/index.css).
 */
export function LoginMascotDecor({ focusedField }: LoginMascotDecorProps) {
  // Randomized once per mount (not per render) so each character's idle
  // wobble looks distinct but stays stable while the page is open - re-
  // rolling on every render would fight the CSS animation and look jittery
  // instead of "gently alive".
  const [wobble] = useState(() => ({
    sun: randomWobble(),
    moon: randomWobble(),
    cloud: randomWobble(),
  }))

  // Which characters are mid-"poked, darting away shyly" right now. Poking one
  // (a click/tap - they're a playful easter egg, so they stay decorative/
  // aria-hidden rather than becoming real controls) makes it act embarrassed
  // and flee, then float back to keep watching. Per-character timers so poking
  // one doesn't reset another's, and a burst of pokes on the same one just
  // restarts its own clock (never stacks).
  const [fleeing, setFleeing] = useState<Record<CharacterKey, boolean>>({ sun: false, moon: false, cloud: false })
  const timersRef = useRef<Record<CharacterKey, ReturnType<typeof setTimeout> | undefined>>({
    sun: undefined,
    moon: undefined,
    cloud: undefined,
  })
  useEffect(() => {
    const timers = timersRef.current
    return () => Object.values(timers).forEach((t) => t && clearTimeout(t))
  }, [])

  function poke(character: CharacterKey) {
    clearTimeout(timersRef.current[character])
    setFleeing((prev) => ({ ...prev, [character]: true }))
    timersRef.current[character] = setTimeout(
      () => setFleeing((prev) => ({ ...prev, [character]: false })),
      FLEE_DURATION_MS,
    )
  }

  const baseMood = moodFor(focusedField)
  const stateClass =
    focusedField === 'username' ? 'login-mascot-decor-watching' : focusedField === 'password' ? 'login-mascot-decor-shy' : ''

  // A poked character overrides the focus-driven mood with a shy blush; its
  // key forces the SVG to remount so the blush re-triggers even on a repeat
  // poke of the character already blushing.
  const renderCharacter = (character: CharacterKey, faceFor: (mood: MascotMood) => ReactElement, style: CSSProperties) => {
    const mood = fleeing[character] ? 'blush' : baseMood
    return (
      <div
        className={`login-mascot-character login-mascot-${character}${fleeing[character] ? ' login-mascot-fleeing' : ''}`}
        style={style}
        onClick={() => poke(character)}
      >
        {faceFor(mood)}
      </div>
    )
  }

  return (
    <div className={`login-mascot-decor ${stateClass}`.trim()} aria-hidden="true">
      {renderCharacter('cloud', (mood) => <CloudFace mood={mood} />, wobble.cloud)}
      {renderCharacter('sun', (mood) => <MascotFace mood={mood} />, wobble.sun)}
      {renderCharacter('moon', (mood) => <MoonFace mood={mood} />, wobble.moon)}
    </div>
  )
}

/** Exported for the unit test - the mood-mapping logic is the one part of
 * this component worth asserting on directly rather than through rendered
 * SVG (jsdom can't usefully assert on SVG path shapes anyway). */
export function moodFor(focusedField: LoginFocusedField): MascotMood {
  if (focusedField === 'password') return 'blush' // closed eyes - "not peeking" at the password
  if (focusedField === 'username') return 'surprised' // wide, attentive eyes - "watching" what's typed
  return 'idle'
}

// CSS custom properties aren't part of CSSProperties' known keys - this
// cast is the standard, narrowly-scoped way to pass them through style.
function randomWobble(): CSSProperties {
  const rot = (Math.random() * 6 - 3).toFixed(1) // -3..3deg
  const x = (Math.random() * 6 - 3).toFixed(1) // -3..3px
  const duration = (5 + Math.random() * 3).toFixed(1) // 5..8s
  const delay = (Math.random() * -8).toFixed(1) // negative delay -> starts mid-cycle, staggering the three characters
  return {
    '--wobble-rot': `${rot}deg`,
    '--wobble-x': `${x}px`,
    '--wobble-duration': `${duration}s`,
    '--wobble-delay': `${delay}s`,
  } as CSSProperties
}
