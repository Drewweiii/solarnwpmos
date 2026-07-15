import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { ApiError } from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { AssetRegistry, SimulateResponse, Zone } from '../../lib/types'
import { SimulationPlaygroundPage } from '../SimulationPlaygroundPage'

function makeZone(id: string): Zone {
  return {
    id,
    name_full: id,
    ac_capacity_kw: 50,
    dc_capacity_kwp: 60,
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

function makeSimulateResponse(zone: string): SimulateResponse {
  return {
    zone,
    simulated_zone: zone === 'Jetty',
    points: [
      { timestamp: '2026-07-14T06:00:00Z', baseline_ac_kw: 10, adjusted_ac_kw: 8, lower: null, upper: null },
      { timestamp: '2026-07-14T12:00:00Z', baseline_ac_kw: 50, adjusted_ac_kw: 40, lower: 35, upper: 45 },
    ],
    loss_breakdown: { soiling_pct: 2.5, shading_pct: 3.0, total_system_loss_pct: 13.2 },
  }
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <SimulationPlaygroundPage />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('SimulationPlaygroundPage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(api, 'getAssets').mockResolvedValue(registry)
    vi.spyOn(api, 'postSimulate').mockImplementation((zone) => Promise.resolve(makeSimulateResponse(zone)))
  })

  it('defaults to GIS and has no All-zones tab', async () => {
    renderPage()
    await screen.findByRole('tab', { name: /^GIS$/i })
    expect(screen.queryByRole('tab', { name: /รวม/ })).not.toBeInTheDocument()
  })

  it('runs a simulation with default scenario params and shows results', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /run simulation/i }))

    await waitFor(() =>
      expect(api.postSimulate).toHaveBeenCalledWith(
        'GIS',
        expect.objectContaining({ extra_cloud_attenuation_pct: 0, curtailment_pct: 0, monte_carlo_n_samples: 1000 }),
        expect.any(String),
      ),
    )
    expect(await screen.findByText('Soiling')).toBeInTheDocument()
    expect(screen.getByText('2.50%')).toBeInTheDocument()
  })

  it('adjusting a slider updates its displayed value and is sent in the request', async () => {
    renderPage()
    const slider = screen.getByLabelText(/curtailment(?! std)/i)
    slider.dispatchEvent(new Event('focus'))
    Object.defineProperty(slider, 'value', { value: '25', configurable: true })
    slider.dispatchEvent(new Event('input', { bubbles: true }))
    slider.dispatchEvent(new Event('change', { bubbles: true }))

    expect(await screen.findByText('25%')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /run simulation/i }))
    await waitFor(() =>
      expect(api.postSimulate).toHaveBeenCalledWith('GIS', expect.objectContaining({ curtailment_pct: 25 }), expect.any(String)),
    )
  })

  it('shows the simulated-zone badge only when the result is for Jetty', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('tab', { name: /Jetty/i }))
    await user.click(screen.getByRole('button', { name: /run simulation/i }))
    expect(await screen.findByText(/simulated zone/i)).toBeInTheDocument()
  })

  it('shows a role-specific message on a 403 (viewer running an operator-gated action)', async () => {
    vi.spyOn(api, 'postSimulate').mockRejectedValue(new ApiError(403, 'forbidden'))
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /run simulation/i }))
    expect(await screen.findByText(/operator or admin account/i)).toBeInTheDocument()
  })

  it('shows a generic error message on other failures', async () => {
    vi.spyOn(api, 'postSimulate').mockRejectedValue(new ApiError(422, 'invalid scenario'))
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /run simulation/i }))
    expect(await screen.findByText(/simulation failed/i)).toBeInTheDocument()
  })
})
