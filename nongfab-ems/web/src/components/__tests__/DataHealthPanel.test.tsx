import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { AnomaliesResponse, FeedsResponse } from '../../lib/types'
import { DataHealthPanel } from '../DataHealthPanel'

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <DataHealthPanel zone="GIS" />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

const feeds: FeedsResponse = {
  overall_status: 'stale',
  checked_at: '2026-07-25T06:00:00Z',
  feeds: [
    {
      name: 'nwp_history',
      label: 'พยากรณ์อากาศ GFS',
      kind: 'coverage',
      status: 'ok',
      rows: 5000,
      latest: '2026-07-25T18:00:00Z',
      age_minutes: -720,
      lead_minutes: 720,
      limit_minutes: 360,
      detail: 'ครอบคลุมล่วงหน้าถึงอีก 720 นาที',
    },
    {
      name: 'aerosol_history',
      label: 'คุณภาพอากาศ CAMS',
      kind: 'coverage',
      status: 'stale',
      rows: 2100,
      latest: '2026-07-25T05:00:00Z',
      age_minutes: 60,
      lead_minutes: -60,
      limit_minutes: 180,
      detail: 'ครอบคลุมล่วงหน้าไม่พอ (ถึงอีก -60 นาที, ต้องการ 180 นาที)',
    },
  ],
}

const anomalies: AnomaliesResponse = {
  available: true,
  zone: 'GIS',
  window_days: 45,
  reason: null,
  days_assessed: 40,
  norm_kwh_per_day: 210,
  anomalies: [
    {
      day: '2026-07-22',
      energy_kwh: 60,
      norm_kwh: 210,
      ratio: 0.2857,
      shortfall_kwh: 150,
      likely_cause: 'cloud',
      cause_detail: 'เมฆมากกว่าปกติ (95% vs ปกติ 40%)',
    },
  ],
  basis_note: 'ไซต์นี้ไม่มีมิเตอร์วัดกำลังผลิตจริง ... ไม่ใช่การยืนยันว่าแผงมีปัญหา',
}

describe('DataHealthPanel', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('names a forecast feed that ran out of forward coverage', async () => {
    vi.spyOn(api, 'getFeedHealth').mockResolvedValue(feeds)
    vi.spyOn(api, 'getOutputAnomalies').mockResolvedValue(anomalies)
    renderPanel()
    expect(await screen.findByText('คุณภาพอากาศ CAMS')).toBeInTheDocument()
    expect(screen.getByText(/ครอบคลุมล่วงหน้าไม่พอ/)).toBeInTheDocument()
    // The overall verdict follows the worst feed.
    expect(screen.getByText(/สถานะรวมของแหล่งข้อมูล/)).toBeInTheDocument()
    expect(screen.getAllByText(/ข้อมูลค้าง/).length).toBeGreaterThan(0)
  })

  it('lists a flagged day with its ranked weather cause', async () => {
    vi.spyOn(api, 'getFeedHealth').mockResolvedValue(feeds)
    vi.spyOn(api, 'getOutputAnomalies').mockResolvedValue(anomalies)
    renderPanel()
    expect(await screen.findByText('2026-07-22')).toBeInTheDocument()
    expect(screen.getByText('29%')).toBeInTheDocument()
    expect(screen.getByText(/เมฆมากกว่าปกติ/)).toBeInTheDocument()
  })

  it('always repeats the no-meter caveat so a flagged day is not read as a fault', async () => {
    vi.spyOn(api, 'getFeedHealth').mockResolvedValue(feeds)
    vi.spyOn(api, 'getOutputAnomalies').mockResolvedValue(anomalies)
    renderPanel()
    expect(await screen.findByText(/ไม่มีมิเตอร์วัดกำลังผลิตจริง/)).toBeInTheDocument()
  })

  it('says so explicitly when no day fell below the threshold', async () => {
    vi.spyOn(api, 'getFeedHealth').mockResolvedValue(feeds)
    vi.spyOn(api, 'getOutputAnomalies').mockResolvedValue({ ...anomalies, anomalies: [] })
    renderPanel()
    expect(await screen.findByText(/ไม่พบวันที่ต่ำกว่าเกณฑ์/)).toBeInTheDocument()
  })

  it('shows the server reason when anomalies cannot be assessed', async () => {
    vi.spyOn(api, 'getFeedHealth').mockResolvedValue(feeds)
    vi.spyOn(api, 'getOutputAnomalies').mockResolvedValue({
      ...anomalies,
      available: false,
      reason: 'ยังไม่มีประวัติกำลังผลิตย้อนหลังพอ',
      anomalies: [],
    })
    renderPanel()
    expect(await screen.findByText(/ยังไม่มีประวัติกำลังผลิตย้อนหลังพอ/)).toBeInTheDocument()
  })
})
