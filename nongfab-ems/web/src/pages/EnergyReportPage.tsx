import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { SLDViewer } from '../components/SLDViewer'
import { ZoneSelector } from '../components/ZoneSelector'
import { useEnergyReport } from '../lib/queries'
import type { MonthlyEnergyEstimate } from '../lib/types'
import './EnergyReportPage.css'

const REAL_ZONE_IDS = ['GIS', 'ISB', 'Jetty'] as const

const MONTH_LABELS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']

const LOSS_LABELS: Record<string, string> = {
  temperature_pct: 'Temperature',
  soiling_pct: 'Soiling',
  shading_pct: 'Shading',
  mismatch_pct: 'Mismatch',
  dc_wiring_pct: 'DC wiring',
  connections_pct: 'Connections',
  availability_pct: 'Availability',
  inverter_loss_pct: 'Inverter',
}
const LOSS_ORDER = Object.keys(LOSS_LABELS)

export function EnergyReportPage() {
  const [zone, setZone] = useState<string>(REAL_ZONE_IDS[0])
  const report = useEnergyReport(zone)

  return (
    <div className="energy-report-page">
      <div className="energy-report-controls">
        <ZoneSelector value={zone} onChange={setZone} includeAll={false} />
      </div>

      {report.isLoading && <p className="forecast-status">Loading energy report…</p>}
      {report.error && <p className="forecast-status forecast-status-warn">Failed to load energy report.</p>}

      {report.data && (
        <>
          {report.data.simulated_zone && (
            <p className="energy-report-simulated-badge">Simulated zone - no panels installed yet</p>
          )}

          <section className="energy-report-section" aria-label="System summary">
            <h2>System summary</h2>
            <div className="energy-report-cards">
              <SummaryCard label="AC capacity" value={report.data.system_summary.ac_capacity_kw.toFixed(1)} unit="kW" />
              <SummaryCard label="DC capacity" value={report.data.system_summary.dc_capacity_kwp.toFixed(2)} unit="kWp" />
              <SummaryCard label="DC/AC ratio" value={report.data.system_summary.dc_ac_ratio.toFixed(2)} unit="" />
              <SummaryCard label="Modules" value={String(report.data.system_summary.module_count)} unit="panels" />
              <SummaryCard
                label="Array area"
                value={report.data.system_summary.array_area_m2 ? report.data.system_summary.array_area_m2.toFixed(0) : 'n/a'}
                unit={report.data.system_summary.array_area_m2 ? 'm²' : ''}
              />
              <SummaryCard
                label="Inverter"
                value={`${report.data.system_summary.inverter_count}x`}
                unit={report.data.system_summary.inverter_model}
              />
            </div>
          </section>

          <section className="energy-report-section" aria-label="Annual generation">
            <h2>Annual generation (estimated)</h2>
            <div className="energy-report-cards">
              <SummaryCard label="Annual energy" value={report.data.annual.ac_energy_kwh.toFixed(0)} unit="kWh/yr" />
              <SummaryCard
                label="Specific yield"
                value={report.data.annual.specific_yield_kwh_per_kwp.toFixed(0)}
                unit="kWh/kWp/yr"
              />
              <SummaryCard
                label="Performance ratio"
                value={(report.data.annual.performance_ratio * 100).toFixed(1)}
                unit="%"
              />
            </div>
            <p className="energy-report-note">
              Extrapolated from one synthetic clear-sky day - not a real annual simulation with weather variability
              (no accumulated generation history exists yet).
            </p>
          </section>

          <section className="energy-report-section" aria-label="Monthly generation">
            <h2>Monthly generation (estimated)</h2>
            <div className="energy-report-chart">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={report.data.monthly}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="month" tickFormatter={(m: number) => MONTH_LABELS[m - 1]} stroke="var(--text)" fontSize={12} />
                  <YAxis stroke="var(--text)" fontSize={12} />
                  <Tooltip
                    contentStyle={{ background: 'var(--card-bg)', border: '1px solid var(--border)', borderRadius: 8 }}
                    labelFormatter={(m) => (typeof m === 'number' ? MONTH_LABELS[m - 1] : String(m))}
                    formatter={(value) => [typeof value === 'number' ? `${value.toFixed(0)} kWh` : String(value), 'AC energy']}
                  />
                  <Bar dataKey="ac_energy_kwh" name="AC energy" radius={[4, 4, 0, 0]}>
                    {report.data.monthly.map((m: MonthlyEnergyEstimate) => (
                      <Cell key={m.month} fill={m.is_rainy_season ? 'var(--chart-rainy)' : 'var(--chart-forecast)'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div className="energy-report-chart-legend">
                <span className="energy-report-legend-item">
                  <span className="energy-report-legend-swatch" style={{ background: 'var(--chart-forecast)' }} />
                  Normal season
                </span>
                <span className="energy-report-legend-item">
                  <span className="energy-report-legend-swatch" style={{ background: 'var(--chart-rainy)' }} />
                  Rainy season (Jun-Oct)
                </span>
              </div>
            </div>
            <p className="energy-report-note">
              Each month's real solar geometry (day length, sun angle) at Nong Fab's coordinates, from one
              representative day scaled to that month's day count - plus an approximate rainy-season cloud
              derate (not measured cloud climatology).
            </p>
          </section>

          <section className="energy-report-section" aria-label="Losses breakdown">
            <h2>Losses breakdown</h2>
            <ul className="energy-report-loss-list">
              {LOSS_ORDER.map((key) => {
                const value = report.data!.loss_breakdown_pct[key]
                if (value === undefined) return null
                return (
                  <li key={key} className="energy-report-loss-item">
                    <span className="energy-report-loss-label">{LOSS_LABELS[key]}</span>
                    <div className="energy-report-loss-bar-track">
                      <div className="energy-report-loss-bar-fill" style={{ width: `${Math.min(100, value * 5)}%` }} />
                    </div>
                    <span className="energy-report-loss-value">{value.toFixed(2)}%</span>
                  </li>
                )
              })}
            </ul>
            <p className="energy-report-total-loss">
              Total system loss: <strong>{report.data.loss_breakdown_pct.total_system_loss_pct?.toFixed(1)}%</strong>
            </p>
          </section>

          <section className="energy-report-section" aria-label="Sun exposure">
            <h2>Sun exposure</h2>
            <div className="energy-report-sun-exposure">
              <span className="energy-report-sun-exposure-value">{report.data.avg_solar_access_pct.toFixed(0)}%</span>
              <p className="energy-report-note energy-report-sun-exposure-note">
                Average unshaded fraction across all panels at local solar noon today - real per-panel row-to-row
                self-shading geometry, not a measured value.
              </p>
            </div>
          </section>

          <section className="energy-report-section" aria-label="Environmental impact">
            <h2>Environmental impact</h2>
            <div className="energy-report-cards">
              <SummaryCard label="CO₂ saved" value={(report.data.co2_saved_kg_per_year / 1000).toFixed(1)} unit="tonnes/yr" />
              <SummaryCard label="Trees equivalent" value={report.data.trees_equivalent_per_year.toFixed(0)} unit="trees/yr" />
            </div>
          </section>

          <section className="energy-report-section" aria-label="25-year estimate">
            <h2>25-year estimate</h2>
            <div className="energy-report-cards">
              <SummaryCard
                label="Lifetime generation"
                value={(report.data.lifecycle.lifetime_ac_energy_kwh / 1000).toFixed(1)}
                unit="MWh"
              />
              <SummaryCard
                label="Year 25 output"
                value={`${(report.data.lifecycle.year_25_ac_energy_kwh / 1000).toFixed(1)} MWh`}
                unit={`(${report.data.lifecycle.year_25_pct_of_year_1.toFixed(0)}% of year 1)`}
              />
            </div>
            <p className="energy-report-note">
              Linear panel degradation assumed at {report.data.lifecycle.degradation_pct_per_year_assumed.toFixed(2)}%/year
              (typical crystalline-silicon warranty range - not a Trina Vertex N-specific measured value).
            </p>
          </section>

          <section className="energy-report-section" aria-label="Single line diagram">
            <h2>Single line diagram</h2>
            <SLDViewer sld={report.data.sld} />
          </section>
        </>
      )}
    </div>
  )
}

interface SummaryCardProps {
  label: string
  value: string
  unit: string
}

function SummaryCard({ label, value, unit }: SummaryCardProps) {
  return (
    <div className="energy-report-card">
      <span className="energy-report-card-label">{label}</span>
      <span className="energy-report-card-value">
        {value}
        {unit && <span className="energy-report-card-unit"> {unit}</span>}
      </span>
    </div>
  )
}
