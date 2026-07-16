// Red-yellow-green gradient status bar, modeled on the reslink.org reference
// video's health/status bar in its widget header. Driven by
// average_solar_access_pct - the same metric already shown as plain text
// elsewhere on this page, just given the reference's gauge treatment here.

interface SolarAccessGaugeProps {
  pct: number
}

export function SolarAccessGauge({ pct }: SolarAccessGaugeProps) {
  const clamped = Math.max(0, Math.min(100, pct))
  return (
    <div className="solar-access-gauge" role="img" aria-label={`Average solar access ${Math.round(clamped)} percent`}>
      <div className="solar-access-gauge-track">
        <div className="solar-access-gauge-marker" style={{ left: `${clamped}%` }} />
      </div>
      <span className="solar-access-gauge-value">{Math.round(clamped)}%</span>
    </div>
  )
}
