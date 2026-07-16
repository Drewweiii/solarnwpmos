import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type {
  AssetRegistry,
  ForecastResponse,
  GeometryResponse,
  PerformanceResponse,
  SunPathResponse,
  Zone,
} from '../../lib/types'
import { Solar3DPage } from '../Solar3DPage'

// Solar3DScene renders a real WebGL <Canvas> (react-three-fiber), which
// jsdom can't provide a context for - mock it so this test exercises the
// surrounding controls/data-wiring only. The canvas itself is verified live
// (see web/README.md "Verified live").
vi.mock('../../components/Solar3DScene', () => ({
  Solar3DScene: ({ panels }: { panels: unknown[] }) => <div data-testid="mock-scene">{panels.length} panels</div>,
}))

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

function makeGeometry(zone: string, panelCount: number): GeometryResponse {
  return {
    zone,
    simulated_zone: zone === 'Jetty',
    at: '2026-07-14T05:00:00Z',
    tilt_deg: 10,
    azimuth_deg: 180,
    row_pitch_m: 3,
    sun: { azimuth_deg: 206, elevation_deg: 38 },
    average_solar_access_pct: 95.4,
    panels: Array.from({ length: panelCount }, (_, i) => ({
      block_id: 'b', row: 0, col: i, east_m: i, north_m: 0, width_m: 2.4, slant_height_m: 1.3, solar_access_pct: 100,
    })),
    string_balance: [],
  }
}

const sunPath: SunPathResponse = {
  zone: 'GIS',
  date: '2026-07-14',
  points: [{ time: '2026-07-14T05:00:00Z', azimuth_deg: 206, elevation_deg: 38 }],
}

function makeForecast(zone: string): ForecastResponse {
  return {
    zone,
    horizon: 'day',
    issued_at: '2026-07-14T00:00:00Z',
    model_version: 1,
    points: [{ timestamp: '2026-07-14T10:00:00Z', pred: 42.5, lower: 35, upper: 50 }],
  }
}

function makePerformance(zone: string): PerformanceResponse {
  return {
    zone,
    simulated_zone: zone === 'Jetty',
    latitude: 12.68,
    longitude: 101.12,
    ac_energy_kwh_today: 300,
    poa_irradiance_kwh_per_m2_today: 6,
    performance_ratio: 0.84,
    specific_yield_kwh_per_kwp_today: 5,
    loss_breakdown: { soiling_pct: 2.5 },
    hourly: [{ timestamp: '2026-07-14T10:00:00Z', ac_kw: 38.1, ssrd_w_m2: 700, temp_c: 31 }],
    cloud_factor: 0.8,
  }
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Solar3DPage />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('Solar3DPage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(api, 'getAssets').mockResolvedValue(registry)
    vi.spyOn(api, 'getGeometry').mockImplementation((zone) => Promise.resolve(makeGeometry(zone, 84)))
    vi.spyOn(api, 'getSunPath').mockResolvedValue(sunPath)
    vi.spyOn(api, 'getForecast').mockImplementation((zone) => Promise.resolve(makeForecast(zone)))
    vi.spyOn(api, 'getPerformance').mockImplementation((zone) => Promise.resolve(makePerformance(zone)))
  })

  it('defaults to GIS and has no All-zones tab', async () => {
    renderPage()
    await screen.findByRole('tab', { name: /^GIS$/i })
    expect(screen.queryByRole('tab', { name: /รวม/ })).not.toBeInTheDocument()
    await waitFor(() => expect(api.getGeometry).toHaveBeenCalledWith('GIS', expect.any(String), expect.any(String)))
  })

  it('renders the compass and solar access readout once geometry loads', async () => {
    renderPage()
    expect(await screen.findByText(/95% avg solar access|95%/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /azimuth 206/i })).toBeInTheDocument()
  })

  it('shows the simulated-zone badge only for Jetty', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByTestId('mock-scene')
    expect(screen.queryByText(/simulated zone/i)).not.toBeInTheDocument()

    await user.click(await screen.findByRole('tab', { name: /Jetty/i }))
    expect(await screen.findByText(/simulated zone/i)).toBeInTheDocument()
  })

  it('switches between solar-access and string view modes', async () => {
    const user = userEvent.setup()
    renderPage()
    const stringTab = await screen.findByRole('tab', { name: /string view/i })
    expect(screen.getByRole('tab', { name: /solar access/i })).toHaveAttribute('aria-selected', 'true')
    await user.click(stringTab)
    expect(stringTab).toHaveAttribute('aria-selected', 'true')
  })

  it('toggles play/pause', async () => {
    const user = userEvent.setup()
    renderPage()
    const playButton = await screen.findByRole('button', { name: /play/i })
    await user.click(playButton)
    expect(await screen.findByRole('button', { name: /pause/i })).toBeInTheDocument()
  })

  it('clicking reset camera view does not throw when the scene has no imperative handle attached', async () => {
    // Solar3DScene is mocked above as a plain component (no forwardRef/
    // useImperativeHandle), so sceneRef.current is never populated in this
    // test - the click handler's optional chaining (sceneRef.current?.
    // resetCamera()) must tolerate that silently rather than throw.
    const user = userEvent.setup()
    renderPage()
    const resetButton = await screen.findByRole('button', { name: /reset camera view/i })
    await expect(user.click(resetButton)).resolves.not.toThrow()
  })

  it('shows forecast vs actual readout tied to the scrub time (Feature A<->C)', async () => {
    renderPage()
    expect(await screen.findByText('42.5 kW')).toBeInTheDocument() // forecast
    expect(await screen.findByText('38.1 kW')).toBeInTheDocument() // actual
  })

  it('shows a string-balance warning only when a block exceeds its limit', async () => {
    vi.spyOn(api, 'getGeometry').mockImplementation((zone) =>
      Promise.resolve({
        ...makeGeometry(zone, 84),
        string_balance: [
          {
            block_id: '01A.L',
            strings: [],
            imbalance_kw: 3.2,
            max_allowed_kw: 2.0,
            exceeds_limit: true,
          },
        ],
      }),
    )
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(/01A\.L/)
    expect(screen.getByRole('alert')).toHaveTextContent(/3\.20 kW > 2\.0 kW/)
  })

  it('moving the time slider re-fetches geometry with the new time', async () => {
    renderPage()
    const slider = await screen.findByLabelText(/time/i)
    await waitFor(() => expect(api.getGeometry).toHaveBeenCalled())
    const callsBefore = vi.mocked(api.getGeometry).mock.calls.length

    slider.dispatchEvent(new Event('focus'))
    Object.defineProperty(slider, 'value', { value: '600', configurable: true })
    slider.dispatchEvent(new Event('input', { bubbles: true }))
    slider.dispatchEvent(new Event('change', { bubbles: true }))

    await waitFor(() => expect(vi.mocked(api.getGeometry).mock.calls.length).toBeGreaterThan(callsBefore))
  })
})
