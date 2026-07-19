import { EyePair, MOUTH_PATH, type MascotMood } from './MascotFace'

interface CloudFaceProps {
  mood?: MascotMood
}

/** A simple fluffy-cloud character sharing น้อง Solar's visual language
 * (same `EyePair`/mouth-path system from MascotFace.tsx) - built for the
 * login screen's reactive illustration (LoginMascotDecor.tsx). The "fluffy"
 * shape is a cluster of overlapping circles (the standard flat-icon cloud
 * technique) rather than a single body shape, but the face still sits on
 * the same 0-0-120-120 coordinate space/eye region as MascotFace so the
 * shared eye/mouth paths line up without extra offsets.
 */
export function CloudFace({ mood = 'idle' }: CloudFaceProps) {
  return (
    <svg className="mascot-svg" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs>
        <radialGradient id="cloud-body-grad" cx="38%" cy="32%" r="75%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="70%" stopColor="#f1f4f9" />
          <stop offset="100%" stopColor="#dde3ee" />
        </radialGradient>
      </defs>

      <g stroke="#aab4c8" strokeWidth="2.2">
        <circle cx="40" cy="68" r="20" fill="url(#cloud-body-grad)" />
        <circle cx="82" cy="68" r="20" fill="url(#cloud-body-grad)" />
        <circle cx="60" cy="52" r="26" fill="url(#cloud-body-grad)" />
        <rect x="34" y="60" width="54" height="28" rx="14" fill="url(#cloud-body-grad)" stroke="none" />
      </g>
      {/* re-stroke just the outer silhouette edge so overlapping circle
          seams don't show through as visible lines across the face */}
      <path
        d="M20 68 A20 20 0 0 1 40 48 A26 26 0 0 1 86 44 A20 20 0 0 1 102 68 A16 16 0 0 1 88 88 L34 88 A16 16 0 0 1 20 68 Z"
        fill="none"
        stroke="#aab4c8"
        strokeWidth="2.2"
      />

      <ellipse cx="47" cy="47" rx="8" ry="5" fill="#fff" opacity="0.85" transform="rotate(-20 47 47)" />

      <EyePair style={mood === 'blush' ? 'closed' : mood === 'surprised' ? 'wide' : 'normal'} />
      <path className="mascot-mouth" d={MOUTH_PATH[mood]} fill="none" stroke="#8a4b12" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  )
}
