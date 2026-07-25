import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { SoilingResponse } from '../../lib/types'
import { SoilingAdvisorPanel } from '../SoilingAdvisorPanel'

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <SoilingAdvisorPanel zone="Jetty" />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

const base: SoilingResponse = {
  available: true,
  zone: 'Jetty',
  reason: null,
  days_assessed: 90,
  current_loss_pct: 1.2,
  average_loss_pct: 0.95,
  current_daily_rate_pct: 0.24,
  days_since_cleaning_rain: 5,
  cleaning_events: 12,
  days_until_trigger: 8,
  cleaning_trigger_pct: 3,
  max_loss_pct: 12,
  annual_energy_lost_kwh: 4200,
  annual_cost_lost_thb: 10500,
  loss_model_soiling_source: 'measured-airquality-rainfall',
  loss_model_soiling_pct: 0.95,
  series_days: ['2026-07-23', '2026-07-24', '2026-07-25'],
  series_loss_pct: [0.8, 1.0, 1.2],
}

describe('SoilingAdvisorPanel', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows the server-provided reason (never a zero) when no assessment is possible', async () => {
    vi.spyOn(api, 'getSoiling').mockResolvedValue({
      ...base,
      available: false,
      reason: 'ยังไม่มีข้อมูลคุณภาพอากาศ (CAMS)',
      loss_model_soiling_source: 'literature-default',
      loss_model_soiling_pct: null,
      series_days: [],
      series_loss_pct: [],
    })
    renderPanel()
    expect(await screen.findByText(/ยังไม่มีข้อมูลคุณภาพอากาศ/)).toBeInTheDocument()
    // Must NOT claim a measured soiling figure is in use.
    expect(screen.queryByText(/ใช้ค่าที่คำนวณจากข้อมูลจริง/)).not.toBeInTheDocument()
  })

  it('reports the current soiling level, accumulation rate and last cleaning rain', async () => {
    vi.spyOn(api, 'getSoiling').mockResolvedValue(base)
    renderPanel()
    expect(await screen.findByText('1.20%')).toBeInTheDocument()
    expect(screen.getByText('0.240%/วัน')).toBeInTheDocument()
    expect(screen.getByText('5 วันก่อน')).toBeInTheDocument()
    expect(screen.getByText(/10.5 พันบาท/)).toBeInTheDocument()
  })

  it('recommends washing soon once the trigger level is reached', async () => {
    vi.spyOn(api, 'getSoiling').mockResolvedValue({ ...base, current_loss_pct: 3.4, days_until_trigger: null })
    renderPanel()
    expect(await screen.findByText(/ควรล้างแผงเร็วๆ นี้/)).toBeInTheDocument()
  })

  it('says rain just washed it when a cleaning rain is fresh', async () => {
    vi.spyOn(api, 'getSoiling').mockResolvedValue({ ...base, days_since_cleaning_rain: 0, days_until_trigger: 30 })
    renderPanel()
    expect(await screen.findByText(/ฝนเพิ่งล้างแผงให้/)).toBeInTheDocument()
    expect(screen.getByText('วันนี้')).toBeInTheDocument()
  })

  it('says "unknown" rather than 0 days when no cleaning rain fell in the window', async () => {
    vi.spyOn(api, 'getSoiling').mockResolvedValue({ ...base, days_since_cleaning_rain: null, cleaning_events: 0 })
    renderPanel()
    expect(await screen.findByText(/ไม่พบฝนที่ล้างแผงในช่วง 90 วัน/)).toBeInTheDocument()
  })

  it('states plainly when the loss model is still on the literature default', async () => {
    vi.spyOn(api, 'getSoiling').mockResolvedValue({
      ...base,
      loss_model_soiling_source: 'literature-default',
      loss_model_soiling_pct: null,
    })
    renderPanel()
    expect(await screen.findByText(/ยังใช้ค่าอ้างอิงจากงานวิจัยอยู่/)).toBeInTheDocument()
  })
})
