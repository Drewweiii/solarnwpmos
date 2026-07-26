import { useEffect, useMemo, useState } from 'react'
import { CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { FinancialUncertaintyPanel } from '../components/FinancialUncertaintyPanel'
import { PrintReport } from '../components/PrintReport'
import { Provenanced } from '../components/Provenanced'
import { ApiError } from '../lib/api'
import { useFinancial } from '../lib/queries'
import type { FinancialRequest } from '../lib/types'
import './FinancialPage.css'

type Assumptions = Omit<Required<FinancialRequest>, 'capex_thb'>

const DEFAULT_ASSUMPTIONS: Assumptions = {
  opex_pct_of_capex_per_year: 1.2,
  tariff_thb_per_kwh: 4.0,
  tariff_escalation_pct_per_year: 3.0,
  opex_escalation_pct_per_year: 3.0,
  discount_rate_pct: 8.0,
  tax_rate_pct: 20.0,
  boi_tax_holiday_years: 8,
  degradation_pct_per_year: 0.55,
  lifetime_years: 25,
}

const THB = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 0 })

export function FinancialPage() {
  const [assumptions, setAssumptions] = useState<Assumptions>(DEFAULT_ASSUMPTIONS)
  const [useCustomCapex, setUseCustomCapex] = useState(false)
  const [customCapexThb, setCustomCapexThb] = useState(6_000_000)
  const financial = useFinancial()

  const set = <K extends keyof Assumptions>(key: K, value: number) => setAssumptions((a) => ({ ...a, [key]: value }))
  const presets = financial.data?.boi_presets ?? []

  const runAnalysis = () => {
    const request: FinancialRequest = { ...assumptions }
    if (useCustomCapex) request.capex_thb = customCapexThb
    financial.mutate(request)
  }

  useEffect(() => {
    // Run once on mount with the placeholder defaults, so the page isn't
    // empty on first load - the user can then adjust sliders and re-run.
    financial.mutate({})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const chartRows = useMemo(() => {
    if (!financial.data) return []
    return financial.data.cash_flows.map((cf) => ({
      year: cf.year,
      undiscounted: cf.cumulative_undiscounted_cash_flow_thb,
      discounted: cf.cumulative_discounted_cash_flow_thb,
    }))
  }, [financial.data])

  const forbidden = financial.error instanceof ApiError && financial.error.status === 403

  return (
    <div className="financial-page">
      <div className="financial-print-row">
        <PrintReport
          title="รายงานการวิเคราะห์การลงทุน"
          subtitle="NPV · IRR · LCOE · ระยะเวลาคืนทุน"
          valueKeys={['financial.payback_years', 'simulation.annual_energy_kwh', 'tou.blended_rate_thb_per_kwh']}
        />
      </div>
      {/* The placeholder banner is deliberately NOT .print-hide: a printed
          investment analysis that dropped its own caveat would be the most
          misleading page this project could produce. */}
      <div className="financial-placeholder-banner" role="note">
        ⚠ All cost/tariff/rate assumptions below are documented placeholders, not confirmed figures for this project (Thailand's
        20% corporate tax rate, the PEA tariff and the BOI holiday are confirmed) - CAPEX and WACC are still estimates, so adjust
        those sliders with real figures once available, and confirm the tax/BOI treatment with a finance/tax professional before using this for an investment
        decision.
      </div>

      <div className="financial-form">
        <h2>Investment assumptions</h2>
        <div className="financial-sliders">
          <div className="financial-capex-field">
            <label className="financial-capex-toggle">
              <input type="checkbox" checked={useCustomCapex} onChange={(e) => setUseCustomCapex(e.target.checked)} />
              Use a known CAPEX figure
            </label>
            {useCustomCapex ? (
              <input
                type="number"
                className="financial-capex-input"
                value={customCapexThb}
                min={0}
                step={10_000}
                onChange={(e) => setCustomCapexThb(Number(e.target.value))}
                aria-label="CAPEX (THB)"
              />
            ) : (
              <p className="financial-capex-note">Auto-estimated from installed DC capacity (placeholder ฿30,000/kWp)</p>
            )}
          </div>

          <SliderField
            label="OPEX (% of CAPEX/yr)"
            unit="%"
            min={0}
            max={5}
            step={0.1}
            value={assumptions.opex_pct_of_capex_per_year}
            onChange={(v) => set('opex_pct_of_capex_per_year', v)}
          />
          <SliderField
            label="Electricity tariff"
            unit=" ฿/kWh"
            min={0}
            max={10}
            step={0.1}
            value={assumptions.tariff_thb_per_kwh}
            onChange={(v) => set('tariff_thb_per_kwh', v)}
          />
          <SliderField
            label="Tariff escalation"
            unit="%/yr"
            min={0}
            max={10}
            step={0.1}
            value={assumptions.tariff_escalation_pct_per_year}
            onChange={(v) => set('tariff_escalation_pct_per_year', v)}
          />
          <SliderField
            label="OPEX escalation (inflation)"
            unit="%/yr"
            min={0}
            max={10}
            step={0.1}
            value={assumptions.opex_escalation_pct_per_year}
            onChange={(v) => set('opex_escalation_pct_per_year', v)}
          />
          <SliderField
            label="Discount rate (WACC)"
            unit="%"
            min={0}
            max={20}
            step={0.5}
            value={assumptions.discount_rate_pct}
            onChange={(v) => set('discount_rate_pct', v)}
          />
          <SliderField
            label="Corporate tax rate"
            unit="%"
            min={0}
            max={35}
            step={1}
            value={assumptions.tax_rate_pct}
            onChange={(v) => set('tax_rate_pct', v)}
          />
          {/* The 8 vs 12 split is a real, confirmed fact about this project
              (general area vs Jetty, 2026-07-25), not a preference - so both are
              one click away rather than numbers to remember. The list comes from
              the API, which reads it from Settings, so a preset can never
              disagree with the published figure. The slider still reaches 15 for
              what-if work. */}
          <SliderField
            label="BOI tax holiday"
            unit=" yr"
            min={0}
            max={15}
            step={1}
            value={assumptions.boi_tax_holiday_years}
            onChange={(v) => set('boi_tax_holiday_years', v)}
          />
          {presets.length > 0 && (
            <div className="financial-boi-presets">
              {presets.map((preset) => (
                <button
                  key={preset.years}
                  type="button"
                  className={assumptions.boi_tax_holiday_years === preset.years ? 'is-active' : ''}
                  onClick={() => set('boi_tax_holiday_years', preset.years)}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          )}
          <SliderField
            label="Panel degradation"
            unit="%/yr"
            min={0}
            max={2}
            step={0.05}
            value={assumptions.degradation_pct_per_year}
            onChange={(v) => set('degradation_pct_per_year', v)}
          />
          <SliderField
            label="Analysis lifetime"
            unit=" yr"
            min={5}
            max={30}
            step={1}
            value={assumptions.lifetime_years}
            onChange={(v) => set('lifetime_years', v)}
          />
        </div>

        <button type="button" onClick={runAnalysis} disabled={financial.isPending}>
          {financial.isPending ? 'Running…' : 'Run analysis'}
        </button>
      </div>

      {financial.isError && (
        <p className="forecast-status forecast-status-warn">
          {forbidden
            ? 'Financial analysis requires an operator or admin account (viewer accounts can browse, not run scenarios).'
            : 'Financial analysis failed - check the assumptions and try again.'}
        </p>
      )}

      {financial.data && (
        <>
          <div className="kpi-row">
            <KpiCard label="CAPEX" value={THB.format(financial.data.capex_thb)} unit="฿" />
            <KpiCard label="NPV" value={THB.format(financial.data.npv_thb)} unit="฿" />
            <KpiCard label="IRR" value={financial.data.irr_pct != null ? financial.data.irr_pct.toFixed(1) : 'N/A'} unit="%" />
            <KpiCard label="LCOE" value={financial.data.lcoe_thb_per_kwh.toFixed(2)} unit="฿/kWh" />
            <KpiCard
              label="Simple payback"
              value={financial.data.simple_payback_years != null ? financial.data.simple_payback_years.toFixed(1) : 'N/A'}
              unit="yr"
              provenanceKey="financial.payback_years"
            />
            <KpiCard
              label="Discounted payback"
              value={financial.data.discounted_payback_years != null ? financial.data.discounted_payback_years.toFixed(1) : 'N/A'}
              unit="yr"
            />
          </div>

          <section className="forecast-chart-section" aria-label="Cumulative cash flow chart">
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={chartRows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="year" label={{ value: 'Year', position: 'insideBottom', offset: -4 }} />
                <YAxis width={70} tickFormatter={(v) => `฿${(Number(v) / 1_000_000).toFixed(1)}M`} />
                <Tooltip formatter={(value) => (typeof value === 'number' ? `฿${THB.format(value)}` : String(value))} />
                <Legend />
                <ReferenceLine y={0} stroke="var(--border)" strokeWidth={1.5} />
                <Line
                  dataKey="undiscounted"
                  name="Cumulative cash flow"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  dot={false}
                  strokeDasharray="4 3"
                />
                <Line dataKey="discounted" name="Cumulative discounted cash flow" stroke="var(--chart-forecast)" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </section>

          {/* The spread behind the headline numbers above (2026-07-25). Sits
              after the cash-flow chart because it qualifies those figures
              rather than replacing them. */}
          <FinancialUncertaintyPanel uncertainty={financial.data.uncertainty} />
        </>
      )}
    </div>
  )
}

interface KpiCardProps {
  label: string
  value: string
  unit: string
  /** A key from GET /provenance. Set it and the label grows a ⓘ opening the
   * chain behind the figure (project O). Payback carries one because it is the
   * headline number here and it rests on a placeholder CAPEX - the popover is
   * where a reader finds that out. */
  provenanceKey?: string
}

function KpiCard({ label, value, unit, provenanceKey }: KpiCardProps) {
  return (
    <div className="kpi-card">
      <span className="kpi-card-label">
        {provenanceKey ? <Provenanced valueKey={provenanceKey}>{label}</Provenanced> : label}
      </span>
      <span className="kpi-card-value">
        {value}
        {unit && <span className="kpi-card-unit"> {unit}</span>}
      </span>
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
  const id = `financial-field-${label.toLowerCase().replace(/\s+/g, '-')}`
  return (
    <div className="financial-slider-field">
      <label htmlFor={id}>
        {label}{' '}
        <span className="financial-slider-value">
          {value.toFixed(step < 1 ? 2 : 0)}
          {unit}
        </span>
      </label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  )
}
