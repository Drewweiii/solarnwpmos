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

// --- Interval verification (2026-07-25, project A) --------------------------

const interval = (over: Partial<NonNullable<VerificationResponse['interval']>> = {}) => ({
  n: 120,
  nominal_pct: 90,
  coverage_pct: 74.2,
  coverage_gap_pct: -15.8,
  mean_width_kw: 6.4,
  pinaw_pct: 12.8,
  pinball_kw: 0.92,
  miss_low_pct: 20.0,
  miss_high_pct: 5.8,
  ...over,
})

describe('ForecastVerificationPanel interval section', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('calls out a band that is narrower than it claims', async () => {
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({
      ...base,
      interval: interval(),
      interval_note: 'ควอนไทล์ 0.05/0.95',
    })
    renderPanel()
    expect(await screen.findByText('74.2%')).toBeInTheDocument()
    expect(screen.getByText(/แถบแคบเกินจริง/)).toBeInTheDocument()
    expect(screen.getByText(/ควอนไทล์ 0.05\/0.95/)).toBeInTheDocument()
  })

  it('calls a well-calibrated band reasonable rather than flagging it', async () => {
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({
      ...base,
      interval: interval({ coverage_pct: 89.1, coverage_gap_pct: -0.9 }),
    })
    renderPanel()
    expect(await screen.findByText(/แถบสมเหตุสมผล/)).toBeInTheDocument()
    expect(screen.queryByText(/แถบแคบเกินจริง/)).not.toBeInTheDocument()
  })

  it('flags an over-wide band as uninformative, not as a success', async () => {
    // Coverage alone can be gamed by widening; the panel must not read 99% as
    // simply "better than 90%".
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({
      ...base,
      interval: interval({ coverage_pct: 99.5, coverage_gap_pct: 9.5 }),
    })
    renderPanel()
    expect(await screen.findByText(/แถบกว้างเกินจำเป็น/)).toBeInTheDocument()
  })

  it('says nothing was published rather than reporting zero coverage', async () => {
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({
      ...base,
      interval: interval({ n: 0, coverage_pct: 0, coverage_gap_pct: -90 }),
    })
    renderPanel()
    expect(await screen.findByText(/ยังไม่มีอะไรให้ตรวจ/)).toBeInTheDocument()
    expect(screen.queryByText(/แถบแคบเกินจริง/)).not.toBeInTheDocument()
  })

  it('renders nothing extra against an older API that omits the block', async () => {
    // A stale backend must not crash the panel - the point metrics still show.
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({ ...base })
    renderPanel()
    // Skill renders in both the headline and the daylight row, hence findAll.
    expect(await screen.findAllByText('0.390')).toHaveLength(2)
    expect(screen.queryByText(/แถบความเชื่อมั่นที่เผยแพร่/)).not.toBeInTheDocument()
  })
})

// --- Sky-condition split (2026-07-25, project C) ----------------------------

describe('ForecastVerificationPanel sky section', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  const bySky = [
    { sky: 'clear', metrics: metrics({ n: 60, rmse_kw: 1.8, mae_kw: 1.1, mbe_kw: 0.2 }) },
    { sky: 'partly_cloudy', metrics: metrics({ n: 40, rmse_kw: 6.4, mae_kw: 4.9, mbe_kw: 1.4 }) },
    { sky: 'overcast', metrics: metrics({ n: 0, rmse_kw: 0, mae_kw: 0, mbe_kw: 0, skill_score: null }) },
  ]

  it('names the hardest sky condition instead of leaving it in the table', async () => {
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({ ...base, by_sky: bySky })
    renderPanel()
    expect(await screen.findByText(/สภาพฟ้าที่ยากที่สุดตอนนี้คือ ⛅ มีเมฆบางส่วน/)).toBeInTheDocument()
  })

  it('keeps an empty condition visible rather than dropping the row', async () => {
    // A missing row reads as "no errors under this sky", the opposite of "no
    // data under this sky".
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({ ...base, by_sky: bySky })
    renderPanel()
    expect(await screen.findByText('☁️ ฟ้าครึ้ม')).toBeInTheDocument()
  })

  it('reports the hours whose sky could not be determined', async () => {
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({
      ...base,
      by_sky: bySky,
      sky_unclassified_n: 7,
    })
    renderPanel()
    expect(await screen.findByText(/อีก 7 ชั่วโมงระบุสภาพฟ้าไม่ได้/)).toBeInTheDocument()
  })

  it('says the split is unavailable when no hour could be classified', async () => {
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({
      ...base,
      by_sky: [
        { sky: 'clear', metrics: metrics({ n: 0 }) },
        { sky: 'partly_cloudy', metrics: metrics({ n: 0 }) },
        { sky: 'overcast', metrics: metrics({ n: 0 }) },
      ],
      sky_unclassified_n: 12,
    })
    renderPanel()
    expect(await screen.findByText(/ยังแยกไม่ได้/)).toBeInTheDocument()
  })

  it('renders nothing extra against an older API that omits the block', async () => {
    vi.spyOn(api, 'getForecastVerification').mockResolvedValue({ ...base })
    renderPanel()
    expect(await screen.findAllByText('0.390')).toHaveLength(2)
    expect(screen.queryByText(/โมเดลพลาดตอนฟ้าเป็นแบบไหน/)).not.toBeInTheDocument()
  })
})
