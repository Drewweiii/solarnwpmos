import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ForecastPage } from '../ForecastPage'
import { AuthProvider } from '../../lib/auth'
import * as api from '../../lib/api'
import type { AssetRegistry, ForecastResponse, PerformanceResponse, WeatherStripResponse, Zone } from '../../lib/types'

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
    latitude: 12.68,
    longitude: 101.12,
    ac_energy_kwh_today: hourly.reduce((sum, p) => sum + p.ac_kw, 0),
    poa_irradiance_kwh_per_m2_today: 7.5,
    performance_ratio: 0.84,
    specific_yield_kwh_per_kwp_today: 6.4,
    loss_breakdown: { soiling_pct: 2.5 },
    hourly,
    // 2 previous days of persisted actual power (2026-07-18) - lets tests
    // verify the "before today" tier actually has data to render, not just
    // today's own `hourly`.
    history: [
      { timestamp: '2026-07-12T10:00:00Z', ac_kw: peakKw * 0.5, estimated: false },
      { timestamp: '2026-07-13T10:00:00Z', ac_kw: peakKw * 0.6, estimated: false },
    ],
    cloud_factor: 0.75,
  }
}

function makeForecast(zone: string, horizon: ForecastResponse['horizon'] = 'day'): ForecastResponse {
  const algorithm = horizon === 'hour' ? 'lightgbm' : horizon === 'minute' ? 'cnn_lstm' : 'neuralprophet'
  const candidateErrors = horizon === 'hour' ? { lightgbm: 3.2, random_forest: 4.1, sum_k_lstm: 3.8 } : null
  return {
    zone,
    horizon,
    issued_at: '2026-07-14T00:00:00Z',
    model_version: 1,
    points: [
      {
        timestamp: '2026-07-14T12:00:00Z',
        pred: 40,
        lower: 32,
        upper: 48,
        algorithm,
        error: horizon === 'hour' ? 3.2 : null,
        candidate_errors: candidateErrors,
      },
    ],
    data_source: 'real',
    model_type: 'ml',
  }
}

function makeWeatherStrip(hourStartIso: string, hoursEachSide: number): WeatherStripResponse {
  const start = new Date(hourStartIso)
  const points = []
  for (let offset = -hoursEachSide; offset <= hoursEachSide + 1; offset++) {
    points.push({
      timestamp: new Date(start.getTime() + offset * 3600_000).toISOString(),
      temp_c: 30.0,
      ssrd_w_m2: 500,
    })
  }
  return { data_source: 'real', points }
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
    vi.spyOn(api, 'getForecast').mockImplementation((zone, horizon) => Promise.resolve(makeForecast(zone, horizon)))
    vi.spyOn(api, 'getWeatherStrip').mockResolvedValue(makeWeatherStrip('2026-07-14T12:00:00.000Z', 12))
  })

  afterEach(() => {
    vi.useRealTimers()
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

  it('renders a weather strip block for each hour in the +/-4h window around now, continuously centered on the real clock', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-07-14T12:00:00.000Z'))

    renderPage()
    await clickGisTab()
    // Default hoursEachSide=4 on WeatherStrip -> 2*4+2 = 10 blocks (-4..+5),
    // all matched to the mocked 30.0°C real data.
    await waitFor(() => expect(screen.getAllByText(/30\.0°C/).length).toBe(10))
    expect(screen.getByText('Real data')).toBeInTheDocument()
  })

  it('re-fetches forecast when switching Day-ahead / Intra-day', async () => {
    const user = userEvent.setup()
    renderPage()
    await clickGisTab()

    await waitFor(() => expect(api.getForecast).toHaveBeenCalledWith('GIS', 'day', expect.any(String)))

    await user.click(screen.getByRole('tab', { name: /Intra-day/i }))
    await waitFor(() => expect(api.getForecast).toHaveBeenCalledWith('GIS', 'hour', expect.any(String)))
  })

  it('shows the zone info panel (lat/lon/cloud factor) only for a single zone, not All', async () => {
    renderPage()
    await waitFor(() => expect(api.getAssets).toHaveBeenCalled())
    expect(screen.queryByLabelText(/zone info/i)).not.toBeInTheDocument()

    await clickGisTab()
    expect(await screen.findByLabelText(/zone info/i)).toBeInTheDocument()
    expect(screen.getByText('12.68000')).toBeInTheDocument()
    expect(screen.getByText('101.12000')).toBeInTheDocument()
    expect(screen.getByText('75%')).toBeInTheDocument() // cloud factor
  })

  it('always fetches and renders the minute-ahead (CNN-LSTM) panel, not gated by the Day/Intra-day toggle', async () => {
    renderPage()
    await clickGisTab()

    await waitFor(() => expect(api.getForecast).toHaveBeenCalledWith('GIS', 'minute', expect.any(String)))
    expect(await screen.findByLabelText(/minute-ahead power forecast chart/i)).toBeInTheDocument()
  })

  it('shows the LightGBM/Random Forest dot-color legend caption only on the Intra-day (hour) chart', async () => {
    const user = userEvent.setup()
    renderPage()
    await clickGisTab()

    // Day-ahead (NeuralProphet, fixed architecture) - no per-point algorithm
    // to color-code, so the caption (distinct from the always-visible
    // model-info panel's own LightGBM/Random Forest mention) stays hidden.
    expect(screen.queryByText(/ดูสีจุดบนกราฟ/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: /Intra-day/i }))
    expect(await screen.findByText(/ดูสีจุดบนกราฟ/)).toBeInTheDocument()
  })

  it('does not show the model-error-over-time chart on Day-ahead (2026-07-18: split out of the main chart, Intra-day only)', async () => {
    renderPage()
    await clickGisTab()
    await waitFor(() => expect(api.getForecast).toHaveBeenCalledWith('GIS', 'day', expect.any(String)))
    expect(screen.queryByLabelText(/model error over time chart/i)).not.toBeInTheDocument()
  })

  it('shows the model-error-over-time chart with real data once Intra-day is selected', async () => {
    const user = userEvent.setup()
    renderPage()
    await clickGisTab()
    await user.click(screen.getByRole('tab', { name: /Intra-day/i }))
    await waitFor(() => expect(api.getForecast).toHaveBeenCalledWith('GIS', 'hour', expect.any(String)))

    const panel = await screen.findByLabelText(/model error over time chart/i)
    expect(within(panel).queryByText('No data yet.')).not.toBeInTheDocument()
  })

  it('always fetches and renders the Model Competition panel, not gated by the Day/Intra-day toggle', async () => {
    renderPage()
    await clickGisTab()

    await waitFor(() => expect(api.getForecast).toHaveBeenCalledWith('GIS', 'hour', expect.any(String)))
    expect(await screen.findByLabelText(/model competition panel/i)).toBeInTheDocument()
  })

  it('shows the Model Competition chart (not the "no data" placeholder) once the hour-ahead point is within the live window', async () => {
    // jsdom's ResponsiveContainer never gets a real box (see setupTests.ts's
    // ResizeObserver stub), so Recharts renders an empty 0-width SVG rather
    // than actual bar/legend content here - this asserts the data-presence
    // branch was taken (buildCompetitionRows found a row), which is what
    // this test can actually observe in jsdom; buildCompetitionRows' own
    // unit tests (chartData.test.ts) cover the winner/spread computation.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-07-14T12:00:00.000Z')) // matches makeForecast's fixed point timestamp

    renderPage()
    await clickGisTab()

    const panel = await screen.findByLabelText(/model competition panel/i)
    expect(within(panel).queryByText('No data yet.')).not.toBeInTheDocument()
    expect(within(panel).queryByText(/no intra-day forecast model/i)).not.toBeInTheDocument()
  })

  it('shows the 3-tier actual-power caption once any actual-power data is present', async () => {
    // jsdom's ResponsiveContainer never gets a real box (see the Model
    // Competition test above), so this only asserts the data-presence
    // branch was taken, not the rendered SVG's stroke colors - those are
    // covered by chartData.test.ts's own tier-assignment unit tests plus
    // live Playwright verification (see forecast/README.md's dated entry).
    vi.useFakeTimers({ toFake: ['Date'] })
    // Within the fixture's "today" (2026-07-14), matching hourlySeries's own
    // UTC-day timestamps, so `hourly` data qualifies as "today"/"now" tiers
    // and makePerformance's `history` (07-12, 07-13) qualifies as "before
    // today".
    vi.setSystemTime(new Date('2026-07-14T12:00:00.000Z'))

    renderPage()
    await clickGisTab()

    expect(await screen.findByText(/เพื่อให้เทียบกับเส้น Forecast สีน้ำเงินได้ง่ายขึ้น/)).toBeInTheDocument()
  })
})

async function clickGisTab() {
  const user = userEvent.setup()
  const gisTab = await screen.findByRole('tab', { name: /^GIS$/i })
  await user.click(gisTab)
}
