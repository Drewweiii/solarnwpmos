import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { GridTodayResponse } from '../../lib/types'
import { buildChartRows, GridContextPanel } from '../GridContextPanel'

// Values are the real EGAT SysGen response captured on 2026-07-25, so these
// assert against what the panel will actually be handed.
function makeGrid(overrides: Partial<GridTodayResponse> = {}): GridTodayResponse {
  return {
    available: true,
    reason: null,
    day: '2026-07-25',
    actual: [
      { at: '2026-07-25T00:00:00+07:00', mw: 28539.4, ambient_c: 28.83 },
      { at: '2026-07-25T13:19:00+07:00', mw: 26093.0, ambient_c: 34.82 },
    ],
    plan: [
      { at: '2026-07-25T00:00:00+07:00', mw: 28412.2, ambient_c: null },
      { at: '2026-07-25T13:19:00+07:00', mw: 25707.7, ambient_c: null },
    ],
    peaks: [
      { label: 'สูงสุดปีนี้', mw: 35991.6, at: '2026-04-22T20:50:00+07:00', ambient_c: 31.7 },
      { label: 'สูงสุดปีที่แล้ว', mw: 34568.3, at: '2025-04-25T22:18:00+07:00', ambient_c: 31.3 },
      { label: 'สูงสุดตลอดกาล', mw: 36477.8, at: '2024-04-29T20:56:00+07:00', ambient_c: 31.8 },
    ],
    latest_mw: 26093.0,
    latest_at: '2026-07-25T13:19:00+07:00',
    latest_ambient_c: 34.82,
    peak_so_far_mw: 28539.4,
    peak_so_far_at: '2026-07-25T00:00:00+07:00',
    plan_deviation_mw: 385.3,
    solar_window_start: '2026-07-25T06:30:00+07:00',
    solar_window_end: '2026-07-25T18:15:00+07:00',
    annual_peak_after_sunset: true,
    site_dc_capacity_kwp: 429.0,
    site_share_of_system_pct: 0.0016441,
    source_note: 'ข้อมูลระบบไฟฟ้าทั้งประเทศจาก EGAT SysGen (กฟผ.)',
    comparison_note: 'กำลังผลิตของหนองแฟบเทียบกับทั้งประเทศ',
    ...overrides,
  }
}

function renderPanel() {
  // The query is `enabled: Boolean(token)`, so without a token in storage it
  // never fires and the panel would render its no-data branch for every case.
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <GridContextPanel />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('buildChartRows', () => {
  it('lines actual and plan up on one minute-of-day axis', () => {
    const d = makeGrid()
    const rows = buildChartRows(d.actual, d.plan)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({ minutes: 0, clock: '00:00', actual: 28539.4, plan: 28412.2 })
    expect(rows[1]).toMatchObject({ minutes: 799, clock: '13:19', actual: 26093.0, plan: 25707.7 })
  })

  it('leaves actual null where only a plan exists, rather than inventing the future', () => {
    // EGAT plans the whole day but has only published actuals up to now; a
    // zero or a carried-forward value here would draw a fake evening curve.
    const rows = buildChartRows(
      [{ at: '2026-07-25T00:00:00+07:00', mw: 28539.4, ambient_c: null }],
      [
        { at: '2026-07-25T00:00:00+07:00', mw: 28412.2, ambient_c: null },
        { at: '2026-07-25T21:00:00+07:00', mw: 33000.0, ambient_c: null },
      ],
    )
    expect(rows).toHaveLength(2)
    expect(rows[1].actual).toBeNull()
    expect(rows[1].plan).toBe(33000.0)
  })

  it('sorts by time even when the feeds arrive out of order', () => {
    const rows = buildChartRows(
      [
        { at: '2026-07-25T13:00:00+07:00', mw: 2, ambient_c: null },
        { at: '2026-07-25T01:00:00+07:00', mw: 1, ambient_c: null },
      ],
      [],
    )
    expect(rows.map((r) => r.clock)).toEqual(['01:00', '13:00'])
  })
})

describe('GridContextPanel', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows the live national figure and this site’s share of it', async () => {
    vi.spyOn(api, 'getGridToday').mockResolvedValue(makeGrid())
    renderPanel()
    expect(await screen.findByText(/26,093 MW/)).toBeInTheDocument()
    expect(screen.getByText('0.0016%')).toBeInTheDocument()
    expect(screen.getByText(/429 kWp ต่อทั้งระบบ/)).toBeInTheDocument()
  })

  it('states the finding: the national peak happens after the sun is down', async () => {
    vi.spyOn(api, 'getGridToday').mockResolvedValue(makeGrid())
    renderPanel()
    const finding = await screen.findByText(/ความต้องการไฟสูงสุดของประเทศเกิดตอนกลางคืน/)
    expect(finding).toBeInTheDocument()
    // Both halves of the comparison must be on screen for the claim to stand up.
    expect(screen.getByText('20:50 น.')).toBeInTheDocument()
    expect(screen.getByText('18:15 น.')).toBeInTheDocument()
  })

  it('does NOT make that claim when the peak is not after sunset', async () => {
    vi.spyOn(api, 'getGridToday').mockResolvedValue(makeGrid({ annual_peak_after_sunset: false }))
    renderPanel()
    await screen.findByText(/26,093 MW/)
    expect(screen.queryByText(/เกิดตอนกลางคืน/)).not.toBeInTheDocument()
  })

  it('renders ICT clock times without re-interpreting them in the viewer’s timezone', async () => {
    // A viewer in London must still see EGAT's 20:50, not 14:50.
    vi.spyOn(api, 'getGridToday').mockResolvedValue(makeGrid())
    renderPanel()
    expect(await screen.findByText('13:19 น. · 34.8°C')).toBeInTheDocument()
  })

  it('marks a deviation above plan as over-consumption', async () => {
    vi.spyOn(api, 'getGridToday').mockResolvedValue(makeGrid())
    renderPanel()
    expect(await screen.findByText('+385 MW')).toBeInTheDocument()
    expect(screen.getByText('ใช้ไฟมากกว่าแผน')).toBeInTheDocument()
  })

  it('lists all three peak records', async () => {
    vi.spyOn(api, 'getGridToday').mockResolvedValue(makeGrid())
    renderPanel()
    expect(await screen.findByText('สูงสุดปีนี้')).toBeInTheDocument()
    expect(screen.getByText('สูงสุดปีที่แล้ว')).toBeInTheDocument()
    expect(screen.getByText('สูงสุดตลอดกาล')).toBeInTheDocument()
    expect(screen.getByText('36,478 MW')).toBeInTheDocument()
  })

  it('shows an honest empty state instead of a fabricated curve when EGAT is unreachable', async () => {
    vi.spyOn(api, 'getGridToday').mockResolvedValue(
      makeGrid({ available: false, reason: 'ยังดึงข้อมูลระบบไฟฟ้าของประเทศจาก กฟผ. ไม่ได้ในขณะนี้' }),
    )
    renderPanel()
    expect(await screen.findByText(/ยังดึงข้อมูลระบบไฟฟ้าของประเทศจาก กฟผ\. ไม่ได้/)).toBeInTheDocument()
    expect(screen.queryByText(/MW/)).not.toBeInTheDocument()
  })
})
