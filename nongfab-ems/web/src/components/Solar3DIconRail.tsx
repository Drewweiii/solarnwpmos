// Vertical icon rail overlaid on the 3D canvas, modeled on the reslink.org
// reference video's left-side toolbar - but mapped onto the controls this
// page actually has (view-mode toggle, play/pause, camera reset) rather
// than reslink's own render-mode-switcher icons, which this app doesn't
// have equivalents for yet (see web/README.md's own note on this). Hand-
// drawn inline SVGs, same pattern as Compass.tsx - no icon library
// dependency for 3 icons.

interface Solar3DIconRailProps {
  viewMode: 'access' | 'string'
  onViewModeChange: (mode: 'access' | 'string') => void
  isPlaying: boolean
  onPlayToggle: () => void
  onResetCamera: () => void
}

export function Solar3DIconRail({ viewMode, onViewModeChange, isPlaying, onPlayToggle, onResetCamera }: Solar3DIconRailProps) {
  return (
    <div className="solar3d-icon-rail" role="tablist" aria-label="3D view controls">
      <button
        type="button"
        role="tab"
        aria-selected={viewMode === 'access'}
        aria-label="Solar access"
        title="Solar access"
        className={viewMode === 'access' ? 'solar3d-icon-btn active' : 'solar3d-icon-btn'}
        onClick={() => onViewModeChange('access')}
      >
        <SunIcon />
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={viewMode === 'string'}
        aria-label="String view"
        title="String view"
        className={viewMode === 'string' ? 'solar3d-icon-btn active' : 'solar3d-icon-btn'}
        onClick={() => onViewModeChange('string')}
      >
        <StringIcon />
      </button>
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

function StringIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <rect x="4" y="5" width="16" height="3.2" rx="1" fill="currentColor" opacity="0.9" />
      <rect x="4" y="10.4" width="16" height="3.2" rx="1" fill="currentColor" opacity="0.6" />
      <rect x="4" y="15.8" width="16" height="3.2" rx="1" fill="currentColor" opacity="0.35" />
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
