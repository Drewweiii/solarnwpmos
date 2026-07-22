import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { SavingsMetrics, SavingsSummaryResponse, ZoneSavings } from '../../lib/types'
import { EnergySavingsTable } from '../EnergySavingsTable'

function metrics(energyKwh: number, billThb: number): SavingsMetrics {
  return {
    energy_kwh: energyKwh,
    bill_saving_thb: billThb,
    ugt1_units_kwh: energyKwh,
    ugt1_saving_thb: energyKwh * 4.14,
    ugt2_units_kwh: energyKwh,
    ugt2_saving_thb: energyKwh * 4.0423,
    carbon_credit_units: 1.2,
    carbon_credit_value_thb: 120,
    trees_equivalent: 135,
    scope2_co2_avoided_kg: energyKwh * 0.4999,
  }
}

function zone(id: string, label: string, kwp: number, simulated = false): ZoneSavings {
  return {
    zone: id,
    label,
    simulated,
    dc_capacity_kwp: kwp,
    periods: {
      day: metrics(100, 410),
      month: metrics(3000, 12300),
      year: metrics(36000, 147600),
      lifetime: metrics(840000, 3444000),
    },
  }
}

const response: SavingsSummaryResponse = {
  zones: [
    zone('ISB', 'Instrument Substation Building', 140.14),
    zone('GIS', 'Grid Integrated Substation', 60.06),
    zone('Jetty', 'ท่าเรือ', 228.8, true),
    zone('combined', 'รวม 3 กลุ่ม (ISB + GIS + Jetty)', 429.0, true),
  ],
  assumptions: {
    voltage_level: 'HV (≥ 69 kV)',
    normal_tariff: 'TOU – Peak',
    normal_rate_thb_per_kwh: 4.1025,
    ugt1_premium_thb_per_kwh: 0.0375,
    ugt1_rate_thb_per_kwh: 4.14,
    ugt2_portfolio: 'Portfolio A',
    ugt2_rate_thb_per_kwh: 4.0423,
    ef_scope2_kg_per_kwh: 0.4999,
    carbon_credit_unit_per_kwp_year: 0.901,
    trees_per_kwp_year: 101,
    carbon_price_thb_per_tonne: 100,
  },
}

function renderTable() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJwdHRsbmcifQ.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <EnergySavingsTable />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('EnergySavingsTable', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('defaults to the combined tab and shows all four horizon columns', async () => {
    vi.spyOn(api, 'getSavingsSummary').mockResolvedValue(response)
    renderTable()

    expect(await screen.findByText('1 วัน')).toBeInTheDocument()
    expect(screen.getByText('1 เดือน')).toBeInTheDocument()
    expect(screen.getByText('1 ปี')).toBeInTheDocument()
    expect(screen.getByText('25 ปี')).toBeInTheDocument()
    // combined caption visible (full label is unique vs the shorter tab text)
    expect(screen.getByText(/รวม 3 กลุ่ม \(ISB \+ GIS \+ Jetty\)/)).toBeInTheDocument()
  })

  it('switches zone when a tab is clicked', async () => {
    vi.spyOn(api, 'getSavingsSummary').mockResolvedValue(response)
    renderTable()

    const isbTab = await screen.findByRole('tab', { name: /ISB/ })
    await userEvent.click(isbTab)
    await waitFor(() => expect(isbTab).toHaveAttribute('aria-selected', 'true'))
    expect(screen.getByText('Instrument Substation Building')).toBeInTheDocument()
  })

  it('renders a simulated badge for the Jetty zone', async () => {
    vi.spyOn(api, 'getSavingsSummary').mockResolvedValue(response)
    renderTable()

    const jettyTab = await screen.findByRole('tab', { name: /Jetty/ })
    await userEvent.click(jettyTab)
    expect(await screen.findByText(/ยังไม่ติดตั้งจริง/)).toBeInTheDocument()
  })

  it('shows an error state when the request fails', async () => {
    vi.spyOn(api, 'getSavingsSummary').mockRejectedValue(new Error('boom'))
    renderTable()
    expect(await screen.findByText(/โหลดตารางผลประหยัดไม่สำเร็จ/)).toBeInTheDocument()
  })
})
