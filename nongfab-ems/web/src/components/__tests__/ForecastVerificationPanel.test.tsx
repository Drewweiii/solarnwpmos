import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { VerificationMetrics, VerificationResponse } from '../../lib/types'
import { ForecastVerificationPanel } from '../ForecastVerificationPanel'

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ForecastVerificationPanel zone="GIS" />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

const metrics = (over: Partial<VerificationMetrics> = {}): VerificationMetrics => ({
  n: 120,
  mae_kw: 3.1,
  rmse_kw: 4.25,
  mbe_kw: 0.8,
  nrmse_pct: 8.5,
  persistence_rmse_kw: 7.0,
  skill_score: 0.39,
  ...over,
})

const base: VerificationResponse = {
  available: true,
  zone: 'GIS',
  horizon: 'hour',
  window_days: 30,
  reason: null,
  ac_capacity_kw: 50,
  daylight: metrics(),
  // Every figure distinct from `daylight`'s, so the assertions below can tell the
  // headline + daylight row apart from the all-hours row.
  all_hours: metrics({ n: 300, rmse_kw: 2.1, mae_kw: 1.2, nrmse_pct: 4.2, mbe_kw: 0.35, skill_score: 0.12 }),
  by_lead: [
    { lead_bucket: '0-1h', metrics: metrics({ n: 40, rmse_kw: 2.0 }) },
    { lead_bucket: '1-3h', metrics: metrics({ n: 80, rmse_kw: 5.5 }) },
    { lead_bucket: '24h+', metrics: metrics({ n: 0, rmse_kw: 0 }) },
  ],
  lead_time_note: 'forecast_history เก็บเฉพาะ issuance ล่าสุดของแต่ละชั่วโมง',
  reference_note: 'ไซต์นี้ไม่มีมิเตอร์วัดกำลังผลิตจริง',
}

describe('ForecastVerificationPanel', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders the server reason when the histories do not overlap', async () => {
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({
      ...base,
      available: false,
      reason: 'ยังไม่มีชั่วโมงที่ทับกัน',
      daylight: null,
      all_hours: null,
      by_lead: [],
    })
    renderPanel()
    expect(await screen.findByText(/ยังไม่มีชั่วโมงที่ทับกัน/)).toBeInTheDocument()
  })

  it('headlines the skill score and shows both daylight and all-hours rows', async () => {
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue(base)
    renderPanel()
    // Once in the big headline readout, once in the table's Skill column.
    expect(await screen.findAllByText('0.390')).toHaveLength(2)
    expect(screen.getByText(/ดีกว่าการเดาแบบ/)).toBeInTheDocument()
    expect(screen.getByText('เฉพาะช่วงมีแดด')).toBeInTheDocument()
    expect(screen.getByText('ทุกชั่วโมง (รวมกลางคืน)')).toBeInTheDocument()
    // The bias carries an explicit sign so an optimistic model is obvious.
    expect(screen.getByText('+0.80')).toBeInTheDocument()
  })

  it('flags a model that is worse than doing nothing', async () => {
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({
      ...base,
      daylight: metrics({ skill_score: -0.2 }),
    })
    renderPanel()
    expect(await screen.findByText(/แย่กว่าการเดาแบบ/)).toBeInTheDocument()
  })

  it('renders a dash, not a zero, when the skill score could not be computed', async () => {
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({
      ...base,
      daylight: metrics({ skill_score: null, persistence_rmse_kw: null }),
    })
    renderPanel()
    expect(await screen.findByText(/ยังคำนวณไม่ได้/)).toBeInTheDocument()
  })

  it('states that these are not training errors, and carries the lead-time caveat', async () => {
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue(base)
    renderPanel()
    expect(await screen.findByText(/ค่า error จากการเทรน/)).toBeInTheDocument()
    expect(screen.getByText(/issuance ล่าสุดของแต่ละชั่วโมง/)).toBeInTheDocument()
  })
})
