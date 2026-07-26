import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { EvolutionResponse } from '../../lib/types'
import { ForecastEvolutionPanel } from '../ForecastEvolutionPanel'

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ForecastEvolutionPanel zone="GIS" />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

// 180 -> 90 -> 175: nets to a placid -5 kW and actually swung 90.
const base: EvolutionResponse = {
  available: true,
  zone: 'GIS',
  horizon: 'day',
  window_days: 7,
  reason: null,
  min_issuances: 3,
  highlight: {
    target_time: '2026-07-26T05:00:00Z',
    n_issuances: 3,
    issuances: [
      { issued_at: '2026-07-23T17:00:00Z', lead_hours: 60, pred_kw: 180, lower_kw: null, upper_kw: null },
      { issued_at: '2026-07-24T23:00:00Z', lead_hours: 30, pred_kw: 90, lower_kw: null, upper_kw: null },
      { issued_at: '2026-07-25T23:00:00Z', lead_hours: 6, pred_kw: 175, lower_kw: null, upper_kw: null },
    ],
    first_pred_kw: 180,
    latest_pred_kw: 175,
    total_revision_kw: -5,
    max_swing_kw: 90,
    is_converging: false,
  },
  n_targets_with_trend: 4,
  collection_note: 'ตารางนี้เริ่มเก็บตั้งแต่ตอน deploy',
  method_note: 'แต่ละจุดคือคำพยากรณ์ 1 รอบ',
}

describe('ForecastEvolutionPanel', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('reports the swing separately from the net revision', async () => {
    // The whole point: -5 kW net looks placid and is the wrong reading.
    vi.spyOn(api, 'getForecastEvolution').mockResolvedValue(base)
    renderPanel()
    expect(await screen.findByText('90')).toBeInTheDocument()
    expect(screen.getByText(/ปรับรวมรอบแรก→ล่าสุด -5 kW/)).toBeInTheDocument()
  })

  it('says plainly that a late-lurching forecast has not settled', async () => {
    vi.spyOn(api, 'getForecastEvolution').mockResolvedValue(base)
    renderPanel()
    expect(await screen.findByText(/ยังแกว่งแรงตอนใกล้เวลาจริง/)).toBeInTheDocument()
  })

  it('credits a forecast that did settle', async () => {
    vi.spyOn(api, 'getForecastEvolution').mockResolvedValue({
      ...base,
      highlight: { ...base.highlight!, is_converging: true },
    })
    renderPanel()
    expect(await screen.findByText(/ค่อยๆ นิ่งลงเมื่อใกล้เวลาจริง/)).toBeInTheDocument()
  })

  it('refuses to judge convergence from too few issuances', async () => {
    vi.spyOn(api, 'getForecastEvolution').mockResolvedValue({
      ...base,
      highlight: { ...base.highlight!, is_converging: null },
    })
    renderPanel()
    expect(await screen.findByText(/ยังบอกไม่ได้ว่าลู่เข้าหรือไม่/)).toBeInTheDocument()
  })

  it('explains that the table is still filling rather than showing an empty chart', async () => {
    vi.spyOn(api, 'getForecastEvolution').mockResolvedValue({
      ...base,
      available: false,
      highlight: null,
      reason: 'ยังไม่มีประวัติคำพยากรณ์หลายรอบ',
    })
    renderPanel()
    expect(await screen.findByText('ยังไม่มีประวัติคำพยากรณ์หลายรอบ')).toBeInTheDocument()
    expect(screen.getByText(/เริ่มเก็บตั้งแต่ตอน deploy/)).toBeInTheDocument()
  })
})
