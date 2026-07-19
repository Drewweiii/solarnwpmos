// Vertical icon rail overlaid on the 3D canvas, modeled on the reslink.org
// reference video's left-side toolbar - but mapped onto the controls this
// page actually has (play/pause, camera reset, ground style) rather than
// reslink's own render-mode-switcher icons 1:1 (this app now has a real
// grid/satellite ground toggle - see Solar3DScene.tsx's groundStyle prop -
// but not reslink's full abstract/photorealistic/satellite-map trio).
// Hand-drawn inline SVGs, same pattern as Compass.tsx - no icon library
// dependency for a handful of icons.
//
// The "Solar access" / "String view" toggle that used to live here (two
// separate per-panel coloring modes) was collapsed into one always-on
// sun-reactive gradient 2026-07-19, per the user's own report that having
// two modes was confusing rather than useful - see Solar3DScene.tsx's
// panel `color` prop docstring for what replaced it. The static Sun icon
// button stays as a fixed (non-interactive) legend hint for what the
// gradient means, not a mode switch anymore.

interface Solar3DIconRailProps {
  isPlaying: boolean
  onPlayToggle: () => void
  onResetCamera: () => void
  groundStyle: 'grid' | 'satellite'
  onGroundStyleChange: (style: 'grid' | 'satellite') => void
}

export function Solar3DIconRail({
  isPlaying,
  onPlayToggle,
  onResetCamera,
  groundStyle,
  onGroundStyleChange,
}: Solar3DIconRailProps) {
  return (
    <div className="solar3d-icon-rail" role="tablist" aria-label="3D view controls">
      <div className="solar3d-icon-btn solar3d-icon-btn-static" aria-label="Panel color reacts to the sun" title="Panel color reacts to the sun">
        <SunIcon />
      </div>
      <button
        type="button"
        aria-label={isPlaying ? 'Pause' : 'Play'}
        title={isPlaying ? 'Pause' : 'Play'}
        className="solar3d-icon-btn"
        onClick={onPlayToggle}
      >
        {isPlaying ? <PauseIcon /> : <PlayIcon />}
      </button>
      <button type="button" aria-label="Reset camera view" title="Reset camera view" className="solar3d-icon-btn" onClick={onResetCamera}>
        <ResetIcon />
      </button>
      <button
        type="button"
        aria-pressed={groundStyle === 'satellite'}
        aria-label={groundStyle === 'satellite' ? 'Switch to grid ground' : 'Switch to satellite ground'}
        title={
          groundStyle === 'satellite'
            ? 'Switch to grid ground'
            : 'Switch to satellite ground (real imagery fetch, not verified from every environment)'
        }
        className={groundStyle === 'satellite' ? 'solar3d-icon-btn active' : 'solar3d-icon-btn'}
        onClick={() => onGroundStyleChange(groundStyle === 'satellite' ? 'grid' : 'satellite')}
      >
        <SatelliteIcon />
      </button>
    </div>
  )
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <circle cx="12" cy="12" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
        <line
          key={deg}
          x1="12"
          y1="3"
          x2="12"
          y2="5.5"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          transform={`rotate(${deg} 12 12)`}
        />
      ))}
    </svg>
  )
}

function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path d="M7 4.5v15l13-7.5-13-7.5z" fill="currentColor" />
    </svg>
  )
}

function PauseIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <rect x="6" y="4.5" width="4.5" height="15" rx="1" fill="currentColor" />
      <rect x="13.5" y="4.5" width="4.5" height="15" rx="1" fill="currentColor" />
    </svg>
  )
}

function SatelliteIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <ellipse cx="12" cy="12" rx="8.5" ry="3.2" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.7" />
      <path d="M3.5 12h17" stroke="currentColor" strokeWidth="1.2" opacity="0.7" />
    </svg>
  )
}

function ResetIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path
        d="M19 12a7 7 0 1 1-2.05-4.95"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path d="M19 4v4.5h-4.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
