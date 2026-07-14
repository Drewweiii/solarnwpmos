import { compassLabel } from '../lib/solar3d'

interface CompassProps {
  azimuthDeg: number
  elevationDeg: number
}

export function Compass({ azimuthDeg, elevationDeg }: CompassProps) {
  return (
    <div className="compass" role="img" aria-label={`Sun azimuth ${Math.round(azimuthDeg)} degrees, altitude ${Math.round(elevationDeg)} degrees`}>
      <svg viewBox="0 0 100 100" className="compass-dial" aria-hidden="true">
        <circle cx="50" cy="50" r="46" fill="none" stroke="currentColor" strokeOpacity="0.3" strokeWidth="2" />
        <text x="50" y="14" textAnchor="middle" fontSize="10" fill="currentColor" opacity="0.6">
          N
        </text>
        <g transform={`rotate(${azimuthDeg} 50 50)`}>
          <line x1="50" y1="50" x2="50" y2="12" stroke="#f59e0b" strokeWidth="3" strokeLinecap="round" />
          <circle cx="50" cy="10" r="4" fill="#f59e0b" />
        </g>
      </svg>
      <div className="compass-readout">
        <span className="compass-azimuth">
          {Math.round(azimuthDeg)}&deg; {compassLabel(azimuthDeg)}
        </span>
        <span className="compass-elevation">Alt: {Math.round(elevationDeg)}&deg;</span>
      </div>
    </div>
  )
}
