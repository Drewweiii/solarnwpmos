import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { AssetRegistry, EnergyReportResponse, Zone } from '../../lib/types'
import { EnergyReportPage, MONTH_LABELS } from '../EnergyReportPage'

function makeZone(id: string): Zone {
  return {
    id,
    name_full: id,
    ac_capacity_kw: 50,
    dc_capacity_kwp: 60.06,
    dc_ac_ratio: 1.2,
    module_count: 84,
    module_power_w: 715,
    inverter_model: 'SUN2000-50KTL-M3',
    inverter_count: 1,
    centroid: { lat: 12.68, lon: 101.12, elevation_m: null, note: null },
    simulated: id === 'Jetty',
    module_detail: null,
    inverter_detail: null,
  }
}

const registry: AssetRegistry = { zones: [makeZone('GIS'), makeZone('ISB'), makeZone('Jetty')] }

function makeReport(zone: string): EnergyReportResponse {
  return {
    zone,
    simulated_zone: zone === 'Jetty',
    system_summary: {
      ac_capacity_kw: 50,
      dc_capacity_kwp: 60.06,
      dc_ac_ratio: 1.2,
      module_count: 84,
      module_power_w: 715,
      array_area_m2: 261.4,
      inverter_model: 'SUN2000-50KTL-M3',
      inverter_count: 1,
    },
    annual: { ac_energy_kwh: 87600, specific_yield_kwh_per_kwp: 1459, performance_ratio: 0.84 },
    loss_breakdown_pct: {
      temperature_pct: 4.1,
      soiling_pct: zone === 'Jetty' ? 6.0 : 2.5,
      shading_pct: 3.0,
      mismatch_pct: 2.0,
      dc_wiring_pct: 2.0,
      connections_pct: 0.5,
      availability_pct: 3.0,
      inverter_loss_pct: 1.0,
      total_system_loss_pct: 18.5,
    },
    co2_saved_kg_per_year: 45230,
    trees_equivalent_per_year: 5050,
    avg_solar_access_pct: 96.4,
    monthly: Array.from({ length: 12 }, (_, i) => ({
      month: i + 1,
      ac_energy_kwh: 7000 + i * 100,
      is_rainy_season: i + 1 >= 6 && i + 1 <= 10,
    })),
    lifecycle: {
      year_1_ac_energy_kwh: 87600,
      year_25_ac_energy_kwh: 75816,
      year_25_pct_of_year_1: 86.2,
      lifetime_ac_energy_kwh: 2044680,
      degradation_pct_per_year_assumed: 0.55,
    },
    sld: {
      module_model: 'Trina Vertex N TSM-NEG21C.20',
      module_power_w: 715,
      optimizer_model: 'Huawei MERC-1300W-P',
      optimizer_ratio_modules_per_optimizer: 2,
      approximate_string_distribution: zone !== 'Jetty',
      blocks: [
        {
          id: zone === 'Jetty' ? '01A.L' : 'INV-1',
          inverter_model: 'SUN2000-50KTL-M3',
          inverter_ac_kw: 50,
          mppt_count: 4,
          strings: [{ id: 'ST-1', modules: 21 }],
        },
      ],
    },
  }
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <EnergyReportPage />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('EnergyReportPage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(api, 'getAssets').mockResolvedValue(registry)
    vi.spyOn(api, 'getEnergyReport').mockImplementation((zone) => Promise.resolve(makeReport(zone)))
    // Panels added to this page in July 2026 (Soiling Advisor, Expansion
    // Planner, the savings table). Left unmocked they attempt a real fetch,
    // which jsdom stalls on long enough to blow the default findBy* timeout
    // for the assertions below. Each is given its documented "no data yet"
    // shape - the panels render their own graceful empty state, which is all
    // these tests need since they assert on the report body, not the panels.
    vi.spyOn(api, 'getSoiling').mockResolvedValue({
      available: false,
      zone: 'GIS',
      reason: 'no data in test',
      days_assessed: 0,
      current_loss_pct: 0,
      average_loss_pct: 0,
      current_daily_rate_pct: 0,
      days_since_cleaning_rain: null,
      cleaning_events: 0,
      days_until_trigger: null,
      cleaning_trigger_pct: 5,
      max_loss_pct: 0,
      annual_energy_lost_kwh: null,
      annual_cost_lost_thb: null,
      loss_model_soiling_source: 'literature-default',
      loss_model_soiling_pct: null,
      series_days: [],
      series_loss_pct: [],
    })
    vi.spyOn(api, 'getExpansion').mockResolvedValue({
      available: false,
      reason: 'no data in test',
      facility_load_kw: null,
      implied_tariff_thb_per_kwh: null,
      capex_per_kwp_thb: 30000,
      scenarios: [],
      targets: [],
      capex_note: '',
      method_note: '',
    })
    vi.spyOn(api, 'getSavingsSummary').mockResolvedValue({ zones: [], assumptions: {} })
  })

  it('defaults to GIS and shows system summary figures', async () => {
    renderPage()
    await screen.findByRole('tab', { name: /^GIS$/i })
    expect(await screen.findByText('50.0')).toBeInTheDocument() // AC capacity kW
    expect(screen.getByText('84')).toBeInTheDocument() // module count
    await waitFor(() => expect(api.getEnergyReport).toHaveBeenCalledWith('GIS', expect.any(String)))
  })

  it('shows the simulated-zone badge only for Jetty', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText(/annual generation/i)
    expect(screen.queryByText(/simulated zone/i)).not.toBeInTheDocument()

    await user.click(await screen.findByRole('tab', { name: /Jetty/i }))
    expect(await screen.findByText(/simulated zone/i)).toBeInTheDocument()
  })

  it('renders the losses breakdown including temperature, with Thai labels', async () => {
    renderPage()
    expect(await screen.findByText('อุณหภูมิ')).toBeInTheDocument()
    expect(screen.getByText('ฝุ่น/คราบสกปรกบนแผง')).toBeInTheDocument()
    expect(screen.getByText(/total system loss/i)).toBeInTheDocument()
  })

  it('jetty shows higher soiling than gis', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('2.50%')

    await user.click(await screen.findByRole('tab', { name: /Jetty/i }))
    expect(await screen.findByText('6.00%')).toBeInTheDocument()
  })

  it('renders CO2 saved and the SLD viewer', async () => {
    renderPage()
    expect(await screen.findByText(/environmental impact/i)).toBeInTheDocument()
    expect(screen.getByText('45.2')).toBeInTheDocument() // co2 tonnes
    expect(screen.getByText(/single line diagram/i)).toBeInTheDocument()
    expect(screen.getByText('INV-1')).toBeInTheDocument()
  })

  it('renders the monthly generation chart with a rainy-season legend', async () => {
    renderPage()
    expect(await screen.findByText(/monthly generation/i)).toBeInTheDocument()
    expect(screen.getByText('Normal season')).toBeInTheDocument()
    expect(screen.getByText(/rainy season/i)).toBeInTheDocument()
  })

  it('labels the monthly chart with full Thai month names, not abbreviations', () => {
    // recharts' <ResponsiveContainer> never renders tick text in jsdom (zero
    // measured width/height), so this asserts on the same MONTH_LABELS array
    // the chart's tickFormatter/labelFormatter both read from, rather than
    // trying to query rendered SVG text that won't exist in this environment.
    expect(MONTH_LABELS).toHaveLength(12)
    expect(MONTH_LABELS[0]).toBe('มกราคม')
    expect(MONTH_LABELS[11]).toBe('ธันวาคม')
    for (const label of MONTH_LABELS) {
      expect(label.length).toBeGreaterThan(1) // full names, not single-letter abbreviations
    }
  })

  it('renders sun exposure and the 25-year estimate', async () => {
    renderPage()
    expect(await screen.findByText(/sun exposure/i)).toBeInTheDocument()
    expect(screen.getByText('96%')).toBeInTheDocument()
    expect(screen.getByText(/25-year estimate/i)).toBeInTheDocument()
    expect(screen.getByText(/86% of year 1/i)).toBeInTheDocument()
  })
})
