import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { RampResponse, RampStep } from '../../lib/types'
import { RampPanel, severityLabel } from '../RampPanel'

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RampPanel zone="GIS" />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

const step = (over: Partial<RampStep> = {}): RampStep => ({
  from_time: '2026-07-25T06:00:00Z',
  to_time: '2026-07-25T07:00:00Z',
  from_kw: 40,
  to_kw: 10,
  delta_kw: -30,
  rate_kw_per_h: -30,
  pct_of_capacity_per_h: -60,
  direction: 'down',
  severity: 'steep',
  ...over,
})

const base: RampResponse = {
  available: true,
  zone: 'GIS',
  reason: null,
  ac_capacity_kw: 50,
  history_days: 30,
  upcoming: [step()],
  alert: step(),
  history: {
    n_steps: 400,
    n_moderate_down: 12,
    n_steep_down: 3,
    n_moderate_up: 9,
    n_steep_up: 1,
    worst_down_pct_per_h: -78,
    worst_up_pct_per_h: 64,
    busiest_down_hour_ict: 15,
    busiest_down_hour_count: 5,
  },
  moderate_pct_per_h: 20,
  steep_pct_per_h: 40,
  no_action_note: 'ไซต์นี้ต่อเข้ากริดอย่างเดียว ไม่มีแบตเตอรี่',
  method_note: 'คำนวณจากผลต่างของกำลังผลิตระหว่างชั่วโมงที่ติดกัน',
}

describe('severityLabel', () => {
  it('separates a fall from a climb at the same severity', () => {
    expect(severityLabel(step({ severity: 'steep', direction: 'down' }))).toBe('ร่วงแรง')
    expect(severityLabel(step({ severity: 'steep', direction: 'up' }))).toBe('พุ่งแรง')
  })

  it('calls an ordinary step calm', () => {
    expect(severityLabel(step({ severity: 'calm', direction: 'flat' }))).toBe('นิ่ง')
  })
})

describe('RampPanel', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('leads with the size and timing of the coming fall', async () => {
    vi.spyOn(api, 'getForecastRamp').mockResolvedValue(base)
    renderPanel()
    expect(await screen.findByText(/กำลังผลิตจะร่วง 30 kW/)).toBeInTheDocument()
    expect(screen.getByText(/60% ของกำลังติดตั้งต่อชั่วโมง/)).toBeInTheDocument()
  })

  it('says the window is quiet rather than showing an empty warning', async () => {
    vi.spyOn(api, 'getForecastRamp').mockResolvedValue({
      ...base,
      alert: null,
      upcoming: [step({ severity: 'calm', direction: 'flat', delta_kw: -1, pct_of_capacity_per_h: -2 })],
    })
    renderPanel()
    expect(await screen.findByText(/ยังไม่มีการร่วงแรง/)).toBeInTheDocument()
  })

  it('shows the measured history that says whether this is routine', async () => {
    vi.spyOn(api, 'getForecastRamp').mockResolvedValue(base)
    renderPanel()
    expect(await screen.findByText('3')).toBeInTheDocument() // steep falls in 30 days
    expect(screen.getByText('15:00')).toBeInTheDocument()
    expect(screen.getByText(/เกิด 5 ครั้งในช่วงนี้/)).toBeInTheDocument()
  })

  it('states that nothing is expected to be dispatched', async () => {
    // The site has no battery and no curtailment; a ramp panel that implied an
    // operator should act would be selling a product this plant cannot use.
    vi.spyOn(api, 'getForecastRamp').mockResolvedValue(base)
    renderPanel()
    expect(await screen.findByText(/ไม่มีแบตเตอรี่/)).toBeInTheDocument()
  })

  it('renders the server reason when there is nothing to difference', async () => {
    vi.spyOn(api, 'getForecastRamp').mockResolvedValue({
      ...base,
      available: false,
      reason: 'ยังไม่มีข้อมูลมากพอ',
      upcoming: [],
      alert: null,
      history: null,
    })
    renderPanel()
    expect(await screen.findByText('ยังไม่มีข้อมูลมากพอ')).toBeInTheDocument()
  })
})
