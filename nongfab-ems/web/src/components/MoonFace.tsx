import { EyePair, MOUTH_PATH, type MascotMood } from './MascotFace'

interface MoonFaceProps {
  mood?: MascotMood
}

/** A simple moon character sharing น้อง Solar's visual language (same
 * `EyePair`/mouth-path system from MascotFace.tsx) - built for the login
 * screen's reactive illustration (LoginMascotDecor.tsx), not the floating
 * assistant mascot, so it stays intentionally simpler than the sun (no
 * rays/rotation/sparkle overlays) - just a body + face + a couple of
 * crater/crescent markings for "moon" flavor. Drawn on the same
 * 0-0-120-120 viewBox with eyes in the same x=44-76/y=54-66 region as
 * MascotFace so the shared eye/mouth paths line up without extra offsets.
 * A full circular body (not an actually-cut crescent shape) on purpose -
 * keeps the face sitting on solid body regardless of mood/geometry tweaks,
 * same low-risk approach as the sun's own full-circle body.
 */
export function MoonFace({ mood = 'idle' }: MoonFaceProps) {
  return (
    <svg className="mascot-svg" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs>
        <radialGradient id="moon-body-grad" cx="38%" cy="32%" r="75%">
          <stop offset="0%" stopColor="#fdf6e3" />
          <stop offset="60%" stopColor="#f0e0ab" />
          <stop offset="100%" stopColor="#dcc077" />
        </radialGradient>
      </defs>

      <circle cx="60" cy="60" r="34" fill="url(#moon-body-grad)" stroke="#a8874a" strokeWidth="2.2" />

      {/* shine highlight, matching MascotFace's own sun */}
      <ellipse cx="47" cy="47" rx="9" ry="6" fill="#fffdf3" opacity="0.7" transform="rotate(-25 47 47)" />

      {/* craters + a small decorative crescent mark - "moon" flavor without
          actually cutting the body shape */}
      <circle cx="76" cy="42" r="5" fill="#dcc077" opacity="0.55" />
      <circle cx="45" cy="78" r="3.4" fill="#dcc077" opacity="0.5" />
      <path d="M78 76 A9 9 0 1 0 78 94 A7 7 0 1 1 78 76 Z" fill="#dcc077" opacity="0.45" />

      <EyePair style={mood === 'blush' ? 'closed' : mood === 'surprised' ? 'wide' : 'normal'} />
      <path className="mascot-mouth" d={MOUTH_PATH[mood]} fill="none" stroke="#8a4b12" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  )
}
