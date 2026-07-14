import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ForecastPage } from '../ForecastPage'
import { AuthProvider } from '../../lib/auth'
import * as api from '../../lib/api'
import type { AssetRegistry, ForecastResponse, PerformanceResponse, Zone } from '../../lib/types'

function makeZone(id: string, ac_capacity_kw: number, simulated = false): Zone {
  return {
    id,
    name_full: id,
    ac_capacity_kw,
    dc_capacity_kwp: ac_capacity_kw * 1.2,
    dc_ac_ratio: 1.2,
    module_count: 84,
    module_power_w: 715,
    inverter_model: 'SUN2000-50KTL-M3',
    inverter_count: 1,
    centroid: { lat: 12.68, lon: 101.12, elevation_m: null, note: null },
    simulated,
    module_detail: null,
    inverter_detail: null,
  }
}

function hourlySeries(peakKw: number) {
  return Array.from({ length: 24 }, (_, hour) => {
    const ssrd = Math.max(0, 1000 * Math.sin((Math.PI * (hour - 6)) / 12))
    return {
      timestamp: `2026-07-14T${String(hour).padStart(2, '0')}:00:00Z`,
      ac_kw: (ssrd / 1000) * peakKw,
      ssrd_w_m2: ssrd,
      temp_c: 30,
    }
  })
}

function makePerformance(zone: string, peakKw: number): PerformanceResponse {
  const hourly = hourlySeries(peakKw)
  return {
    zone,
    simulated_zone: false,
    ac_energy_kwh_today: hourly.reduce((sum, p) => sum + p.ac_kw, 0),
    poa_irradiance_kwh_per_m2_today: 7.5,
    performance_ratio: 0.84,
    specific_yield_kwh_per_kwp_today: 6.4,
    loss_breakdown: { soiling_pct: 2.5 },
    hourly,
  }
}

function makeForecast(zone: string): ForecastResponse {
  return {
    zone,
    horizon: 'day',
    issued_at: '2026-07-14T00:00:00Z',
    model_version: 1,
    points: [{ timestamp: '2026-07-14T12:00:00Z', pred: 40, lower: 32, upper: 48 }],
  }
}

const registry: AssetRegistry = { zones: [makeZone('GIS', 50), makeZone('ISB', 120), makeZone('Jetty', 200, true)] }

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ForecastPage />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('ForecastPage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(api, 'getAssets').mockResolvedValue(registry)
    vi.spyOn(api, 'getPerformance').mockImplementation((zone) =>
      Promise.resolve(makePerformance(zone, { GIS: 50, ISB: 120, Jetty: 200 }[zone] ?? 50)),
    )
    vi.spyOn(api, 'getForecast').mockImplementation((zone) => Promise.resolve(makeForecast(zone)))
  })

  it('shows the site-wide (All) KPI totals by default', async () => {
    renderPage()

    await waitFor(() => expect(api.getAssets).toHaveBeenCalled())
    // capacity = 50 + 120 + 200 = 370 kW across all 3 zones
    expect(await screen.findByText('370.0')).toBeInTheDocument()
  })

  it('switches to a single zone KPI total when a zone tab is clicked', async () => {
    const user = userEvent.setup()
    renderPage()

    const gisTab = await screen.findByRole('tab', { name: /^GIS$/i })
    await user.click(gisTab)

    await waitFor(() => expect(screen.getByText('50.0')).toBeInTheDocument())
  })

  it('renders a weather strip entry for each of the 4 target hours', async () => {
    renderPage()
    await clickGisTab()
    await waitFor(() => expect(screen.getAllByText(/30\.0°C/).length).toBe(4))
  })

  it('re-fetches forecast when switching Day-ahead / Intra-day', async () => {
    const user = userEvent.setup()
    renderPage()
    await clickGisTab()

    await waitFor(() => expect(api.getForecast).toHaveBeenCalledWith('GIS', 'day', expect.any(String)))

    await user.click(screen.getByRole('tab', { name: /Intra-day/i }))
    await waitFor(() => expect(api.getForecast).toHaveBeenCalledWith('GIS', 'hour', expect.any(String)))
  })
})

async function clickGisTab() {
  const user = userEvent.setup()
  const gisTab = await screen.findByRole('tab', { name: /^GIS$/i })
  await user.click(gisTab)
}
