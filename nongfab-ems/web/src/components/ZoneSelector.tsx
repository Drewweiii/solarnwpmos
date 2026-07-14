import { ALL_ZONES_ID, useZones } from '../lib/queries'

interface ZoneSelectorProps {
  value: string
  onChange: (zoneId: string) => void
}

export function ZoneSelector({ value, onChange }: ZoneSelectorProps) {
  const { data, isLoading } = useZones()

  return (
    <div className="zone-selector" role="tablist" aria-label="Zone">
      {isLoading && <span className="zone-selector-loading">Loading zones…</span>}
      <button
        type="button"
        role="tab"
        aria-selected={value === ALL_ZONES_ID}
        className={value === ALL_ZONES_ID ? 'zone-tab active' : 'zone-tab'}
        onClick={() => onChange(ALL_ZONES_ID)}
      >
        รวม (All)
      </button>
      {data?.zones.map((zone) => (
        <button
          key={zone.id}
          type="button"
          role="tab"
          aria-selected={value === zone.id}
          className={value === zone.id ? 'zone-tab active' : 'zone-tab'}
          onClick={() => onChange(zone.id)}
        >
          {zone.id}
          {zone.simulated && <span className="zone-tab-badge">sim</span>}
        </button>
      ))}
    </div>
  )
}
