import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { IrradianceMapResponse } from '../../lib/types'
import { IrradianceMapPage } from '../IrradianceMapPage'

// IrradianceMapView renders a real WebGL MapLibre canvas, which jsdom can't
// provide a context for - mock it so this test exercises the surrounding
// controls/data-wiring only. The canvas itself is verified live (see
// web/README.md "Verified live"), same pattern as Solar3DScene/Solar3DPage.
vi.mock('../../components/IrradianceMapView', () => ({
  IrradianceMapView: ({ grid, zones }: { grid: unknown[]; zones: unknown[] }) => (
    <div data-testid="mock-map">
      {grid.length} points, {zones.length} zones
    </div>
  ),
}))

function makeMap(elevationDeg: number): IrradianceMapResponse {
  return {
    at: '2026-07-14T05:00:00Z',
    sun: { azimuth_deg: 90, elevation_deg: elevationDeg },
    clearsky_ghi_w_m2: elevationDeg > 0 ? 850 : 0,
    grid: Array.from({ length: 25 }, (_, i) => ({
      lat: 12.68 + i * 0.001,
      lon: 101.12 + i * 0.001,
      ghi_w_m2: elevationDeg > 0 ? 700 : 0,
      cloud_factor: 0.8,
    })),
    zones: [
      { id: 'GIS', name_full: 'Grid Integrated Substation', lat: 12.6834, lon: 101.1199, ac_capacity_kw: 50, simulated: false },
      { id: 'ISB', name_full: 'Instrument Substation Building', lat: 12.6813, lon: 101.1183, ac_capacity_kw: 150, simulated: false },
      { id: 'Jetty', name_full: 'ท่าเรือ', lat: 12.6728, lon: 101.1159, ac_capacity_kw: 200, simulated: true },
    ],
  }
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <IrradianceMapPage />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('IrradianceMapPage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(api, 'getIrradianceMap').mockResolvedValue(makeMap(38))
  })

  it('loads the map with grid points and zone pins', async () => {
    renderPage()
    expect(await screen.findByText(/25 points, 3 zones/)).toBeInTheDocument()
    await waitFor(() => expect(api.getIrradianceMap).toHaveBeenCalledWith(expect.any(String), expect.any(String)))
  })

  it('shows clear-sky GHI readout', async () => {
    renderPage()
    expect(await screen.findByText(/850 W\/m²/)).toBeInTheDocument()
  })

  it('shows a night badge when sun elevation is non-positive', async () => {
    vi.spyOn(api, 'getIrradianceMap').mockResolvedValue(makeMap(-10))
    renderPage()
    expect(await screen.findByText(/night/i)).toBeInTheDocument()
  })

  it('has layer toggle checkboxes for irradiance overlay and zone pins', async () => {
    renderPage()
    await screen.findByTestId('mock-map')
    expect(screen.getByRole('checkbox', { name: /irradiance overlay/i })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /zone pins/i })).toBeChecked()
  })

  it('toggling a layer checkbox unchecks it', async () => {
    const user = userEvent.setup()
    renderPage()
    const checkbox = await screen.findByRole('checkbox', { name: /irradiance overlay/i })
    await user.click(checkbox)
    expect(checkbox).not.toBeChecked()
  })

  it('moving the time slider re-fetches the map with the new time', async () => {
    renderPage()
    const slider = await screen.findByLabelText(/time/i)
    await waitFor(() => expect(api.getIrradianceMap).toHaveBeenCalled())
    const callsBefore = vi.mocked(api.getIrradianceMap).mock.calls.length

    slider.dispatchEvent(new Event('focus'))
    Object.defineProperty(slider, 'value', { value: '360', configurable: true })
    slider.dispatchEvent(new Event('input', { bubbles: true }))
    slider.dispatchEvent(new Event('change', { bubbles: true }))

    await waitFor(() => expect(vi.mocked(api.getIrradianceMap).mock.calls.length).toBeGreaterThan(callsBefore))
  })

  it('toggles play/pause', async () => {
    const user = userEvent.setup()
    renderPage()
    const playButton = await screen.findByRole('button', { name: /play/i })
    await user.click(playButton)
    expect(await screen.findByRole('button', { name: /pause/i })).toBeInTheDocument()
  })
})
