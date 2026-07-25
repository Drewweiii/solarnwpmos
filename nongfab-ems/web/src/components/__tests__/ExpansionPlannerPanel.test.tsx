import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { ExpansionResponse } from '../../lib/types'
import { ExpansionPlannerPanel } from '../ExpansionPlannerPanel'

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ExpansionPlannerPanel />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

const base: ExpansionResponse = {
  available: true,
  reason: null,
  facility_load_kw: 13500,
  implied_tariff_thb_per_kwh: 2.54,
  capex_per_kwp_thb: 30000,
  scenarios: [
    {
      label: 'ปัจจุบัน',
      phase: null,
      ac_capacity_kw: 400,
      dc_capacity_kwp: 429,
      annual_energy_kwh: 600_000,
      solar_offset_pct: 0.507,
      annual_bill_saving_thb: 1_524_000,
      marginal_ac_capacity_kw: null,
      marginal_annual_energy_kwh: null,
      marginal_bill_saving_thb: null,
      marginal_energy_per_kwp: null,
      capex_estimate_thb: null,
      simple_payback_years: null,
    },
    {
      label: 'เฟส 2',
      phase: '2',
      ac_capacity_kw: 800,
      dc_capacity_kwp: 858,
      annual_energy_kwh: 1_200_000,
      solar_offset_pct: 1.014,
      annual_bill_saving_thb: 3_048_000,
      marginal_ac_capacity_kw: 400,
      marginal_annual_energy_kwh: 600_000,
      marginal_bill_saving_thb: 1_524_000,
      marginal_energy_per_kwp: 1398,
      capex_estimate_thb: 12_870_000,
      simple_payback_years: 8.4,
    },
  ],
  targets: [{ target_offset_pct: 10, required_dc_capacity_kwp: 8456, times_current_capacity: 19.7 }],
  capex_note: 'ค่า CAPEX ฿30,000/kWp เป็นค่าประมาณ (placeholder)',
  method_note: 'พลังงานของแต่ละเฟสประมาณโดยขยายตามสัดส่วนกำลังติดตั้ง',
}

describe('ExpansionPlannerPanel', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows the server reason when there is no expansion plan to report', async () => {
    vi.spyOn(api, 'getExpansion').mockResolvedValue({
      ...base,
      available: false,
      reason: 'ยังไม่มีข้อมูลเฟสขยาย',
      scenarios: [],
      targets: [],
    })
    renderPanel()
    expect(await screen.findByText(/ยังไม่มีข้อมูลเฟสขยาย/)).toBeInTheDocument()
  })

  it('reports each phase with its own marginal contribution', async () => {
    vi.spyOn(api, 'getExpansion').mockResolvedValue(base)
    renderPanel()
    expect(await screen.findByText('เฟส 2')).toBeInTheDocument()
    expect(screen.getByText('800')).toBeInTheDocument()
    // The marginal energy-per-kWp column - the "is this phase still worth it" figure.
    expect(screen.getByText('1398')).toBeInTheDocument()
    expect(screen.getByText('8.4')).toBeInTheDocument()
  })

  it('puts the offset in context: even the end state is ~1% of the load', async () => {
    vi.spyOn(api, 'getExpansion').mockResolvedValue(base)
    renderPanel()
    // Once in the headline sentence, once in the table's own offset column.
    expect(await screen.findAllByText(/1\.01%/)).toHaveLength(2)
    expect(screen.getByText(/13.5 MW/)).toBeInTheDocument()
  })

  it('shows what a meaningful offset would actually require', async () => {
    vi.spyOn(api, 'getExpansion').mockResolvedValue(base)
    renderPanel()
    expect(await screen.findByText('8456')).toBeInTheDocument()
    expect(screen.getByText('19.7×')).toBeInTheDocument()
  })

  it('flags the CAPEX placeholder and names the real tariff it used', async () => {
    vi.spyOn(api, 'getExpansion').mockResolvedValue(base)
    renderPanel()
    expect(await screen.findByText(/placeholder/)).toBeInTheDocument()
    expect(screen.getByText(/2.54 บาท\/kWh/)).toBeInTheDocument()
    expect(screen.getByText(/ขยายตามสัดส่วน/)).toBeInTheDocument()
  })
})
