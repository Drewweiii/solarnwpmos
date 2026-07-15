import { useMemo, useState } from 'react'
import { Area, Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ZoneSelector } from '../components/ZoneSelector'
import { ApiError } from '../lib/api'
import { useSimulate } from '../lib/queries'
import { formatHourUtc } from '../lib/timeScrub'
import type { SimulateRequest } from '../lib/types'
import './SimulationPlaygroundPage.css'

const REAL_ZONE_IDS = ['GIS', 'ISB', 'Jetty'] as const

const DEFAULT_REQUEST: Required<SimulateRequest> = {
  extra_cloud_attenuation_pct: 0,
  curtailment_pct: 0,
  degradation_pct_per_year: 0,
  years_since_commissioning: 0,
  extra_cloud_attenuation_std_pct: 0,
  curtailment_std_pct: 0,
  degradation_std_pct_per_year: 0,
  monte_carlo_n_samples: 1000,
}

const LOSS_LABELS: Record<string, string> = {
  soiling_pct: 'Soiling',
  shading_pct: 'Shading',
  mismatch_pct: 'Mismatch',
  dc_wiring_pct: 'DC wiring',
  connections_pct: 'Connections',
  availability_pct: 'Availability',
  inverter_loss_pct: 'Inverter',
  total_system_loss_pct: 'Total system loss',
}

export function SimulationPlaygroundPage() {
  const [zone, setZone] = useState<string>(REAL_ZONE_IDS[0])
  const [request, setRequest] = useState<Required<SimulateRequest>>(DEFAULT_REQUEST)
  const simulate = useSimulate()

  const set = <K extends keyof SimulateRequest>(key: K, value: number) => setRequest((r) => ({ ...r, [key]: value }))

  const runSimulation = () => simulate.mutate({ zone, request })

  const chartRows = useMemo(() => {
    if (!simulate.data) return []
    return simulate.data.points.map((p) => ({
      timestamp: p.timestamp,
      baseline: p.baseline_ac_kw,
      adjusted: p.adjusted_ac_kw,
      lower: p.lower,
      band: p.lower != null && p.upper != null ? p.upper - p.lower : null,
    }))
  }, [simulate.data])

  const forbidden = simulate.error instanceof ApiError && simulate.error.status === 403

  return (
    <div className="sim-playground-page">
      <div className="sim-playground-controls">
        <ZoneSelector value={zone} onChange={setZone} includeAll={false} />
      </div>

      <div className="sim-playground-form">
        <h2>What-if scenario</h2>
        <div className="sim-playground-sliders">
          <SliderField
            label="Extra cloud attenuation"
            unit="%"
            min={0}
            max={100}
            value={request.extra_cloud_attenuation_pct}
            onChange={(v) => set('extra_cloud_attenuation_pct', v)}
          />
          <SliderField
            label="Curtailment"
            unit="%"
            min={0}
            max={100}
            value={request.curtailment_pct}
            onChange={(v) => set('curtailment_pct', v)}
          />
          <SliderField
            label="Degradation"
            unit="%/yr"
            min={0}
            max={5}
            step={0.1}
            value={request.degradation_pct_per_year}
            onChange={(v) => set('degradation_pct_per_year', v)}
          />
          <SliderField
            label="Years since commissioning"
            unit="yr"
            min={0}
            max={30}
            value={request.years_since_commissioning}
            onChange={(v) => set('years_since_commissioning', v)}
          />
        </div>

        <h2>Monte Carlo uncertainty (optional)</h2>
        <p className="sim-playground-note">
          Leave all three at 0 to skip Monte Carlo entirely - the chart then shows a single adjusted line, no interval band.
        </p>
        <div className="sim-playground-sliders">
          <SliderField
            label="Cloud attenuation std"
            unit="%"
            min={0}
            max={30}
            value={request.extra_cloud_attenuation_std_pct}
            onChange={(v) => set('extra_cloud_attenuation_std_pct', v)}
          />
          <SliderField
            label="Curtailment std"
            unit="%"
            min={0}
            max={30}
            value={request.curtailment_std_pct}
            onChange={(v) => set('curtailment_std_pct', v)}
          />
          <SliderField
            label="Degradation std"
            unit="%/yr"
            min={0}
            max={2}
            step={0.1}
            value={request.degradation_std_pct_per_year}
            onChange={(v) => set('degradation_std_pct_per_year', v)}
          />
        </div>

        <button type="button" onClick={runSimulation} disabled={simulate.isPending}>
          {simulate.isPending ? 'Running…' : 'Run simulation'}
        </button>
      </div>

      {simulate.isError && (
        <p className="forecast-status forecast-status-warn">
          {forbidden
            ? 'Simulation requires an operator or admin account (viewer accounts can browse, not run scenarios).'
            : 'Simulation failed - check the scenario parameters and try again.'}
        </p>
      )}

      {simulate.data && (
        <>
          <section className="forecast-chart-section" aria-label="Simulation result chart">
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={chartRows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="timestamp" tickFormatter={formatHourUtc} minTickGap={24} />
                <YAxis unit=" kW" width={80} />
                <Tooltip
                  labelFormatter={(label) => (typeof label === 'string' ? formatHourUtc(label) : String(label))}
                  formatter={(value) => (typeof value === 'number' ? value.toFixed(1) : String(value))}
                />
                <Legend />
                <Bar dataKey="baseline" name="Baseline" fill="var(--accent)" fillOpacity={0.35} barSize={14} />
                <Area dataKey="lower" name="lower" stackId="pi" stroke="none" fill="transparent" legendType="none" />
                <Area
                  dataKey="band"
                  name="Monte Carlo interval"
                  stackId="pi"
                  stroke="none"
                  fill="var(--chart-forecast)"
                  fillOpacity={0.2}
                />
                <Line dataKey="adjusted" name="Adjusted (scenario)" stroke="var(--chart-forecast)" strokeWidth={2} dot={{ r: 2 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </section>

          <section className="sim-playground-loss-section" aria-label="Loss breakdown">
            <h2>Loss breakdown</h2>
            <ul className="sim-playground-loss-list">
              {Object.entries(simulate.data.loss_breakdown).map(([key, value]) => (
                <li key={key} className="sim-playground-loss-item">
                  <span>{LOSS_LABELS[key] ?? key}</span>
                  <strong>{value.toFixed(2)}%</strong>
                </li>
              ))}
            </ul>
            {simulate.data.simulated_zone && (
              <p className="sim-playground-simulated-badge">Simulated zone - no panels installed yet</p>
            )}
          </section>
        </>
      )}
    </div>
  )
}

interface SliderFieldProps {
  label: string
  unit: string
  min: number
  max: number
  step?: number
  value: number
  onChange: (value: number) => void
}

function SliderField({ label, unit, min, max, step = 1, value, onChange }: SliderFieldProps) {
  const id = `sim-field-${label.toLowerCase().replace(/\s+/g, '-')}`
  return (
    <div className="sim-playground-slider-field">
      <label htmlFor={id}>
        {label} <span className="sim-playground-slider-value">{value.toFixed(step < 1 ? 1 : 0)}{unit}</span>
      </label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  )
}
