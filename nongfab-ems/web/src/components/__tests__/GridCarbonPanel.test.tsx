import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { GridCarbonResponse } from '../../lib/types'
import { buildCarbonRows, GridCarbonPanel } from '../GridCarbonPanel'

/** The panel's job is to say uncomfortable things accurately: the fuel split is
 * a YEARLY average rather than the month on screen, the site profile is
 * clear-sky rather than metered, and the headline factor differs from the one
 * the Energy Report publishes. These tests pin those labels, because losing one
 * of them would turn a caveated model into an apparent measurement.
 */
function makeCarbon(overrides: Partial<GridCarbonResponse> = {}): GridCarbonResponse {
  return {
    available: true,
    reason: null,
    day: '2026-07-25',
    hours: [
      {
        hour: 3,
        load_mw: 23100,
        average_kg_per_kwh: 0.431,
        marginal_kg_per_kwh: 0.502,
        marginal_fuel_key: 'natural_gas',
        marginal_fuel_label: 'ก๊าซธรรมชาติ',
        samples: 60,
        site_generation_kwh: 0,
      },
      {
        hour: 12,
        load_mw: 31800,
        average_kg_per_kwh: 0.468,
        marginal_kg_per_kwh: 0.502,
        marginal_fuel_key: 'natural_gas',
        marginal_fuel_label: 'ก๊าซธรรมชาติ',
        samples: 60,
        site_generation_kwh: 317.4,
      },
      {
        hour: 20,
        load_mw: 34200,
        average_kg_per_kwh: 0.489,
        marginal_kg_per_kwh: 0.502,
        marginal_fuel_key: 'natural_gas',
        marginal_fuel_label: 'ก๊าซธรรมชาติ',
        samples: 60,
        site_generation_kwh: 0,
      },
    ],
    mix: [
      { key: 'natural_gas', label: 'ก๊าซธรรมชาติ', share_pct: 60, ef_kg_per_kwh: 0.49 },
      { key: 'coal_lignite', label: 'ถ่านหิน/ลิกไนต์', share_pct: 16, ef_kg_per_kwh: 0.82 },
    ],
    mix_origin: 'annual',
    mix_note: 'สัดส่วนเชื้อเพลิงเป็นค่าจริงทั้งประเทศปี 2566 จาก สนพ. — แต่เป็นค่าเฉลี่ยทั้งปี ไม่ใช่รายเดือน',
    published_ef_kg_per_kwh: 0.4758,
    solar_weighted_marginal_kg_per_kwh: 0.502,
    solar_weighted_average_kg_per_kwh: 0.468,
    marginal_uplift_pct: 5.5,
    method_note: 'เส้นโหลดของระบบเป็นข้อมูลจริงรายนาทีจาก กฟผ.',
    calibration_note: 'ค่าเฉลี่ยถ่วงน้ำหนักของเส้นนี้ถูกตรึงให้เท่ากับ GEF ที่เผยแพร่จริงเสมอ',
    marginal_note: 'ค่า marginal คือคาร์บอนของโรงไฟฟ้าที่จะลดกำลังลง',
    profile_note: 'รูปการผลิตรายชั่วโมงของไซต์คำนวณจากตำแหน่งดวงอาทิตย์จริงแบบท้องฟ้าใส',
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
        <GridCarbonPanel />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('buildCarbonRows', () => {
  it('labels each hour with a zero-padded ICT clock', () => {
    const rows = buildCarbonRows(makeCarbon().hours)
    expect(rows.map((r) => r.clock)).toEqual(['03:00', '12:00', '20:00'])
  })

  it('keeps hours the array does not produce in, so the bars stay in daylight', () => {
    // Dropping them would make the chart imply the grid only exists by day.
    const rows = buildCarbonRows(makeCarbon().hours)
    expect(rows).toHaveLength(3)
    expect(rows.filter((r) => r.site_generation_kwh > 0)).toHaveLength(1)
  })
})

describe('GridCarbonPanel', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('shows the published factor next to the one this array actually earns', async () => {
    vi.spyOn(api, 'getGridCarbon').mockResolvedValue(makeCarbon())
    renderPanel()

    expect(await screen.findByText('0.476')).toBeInTheDocument()
    expect(screen.getByText('0.502')).toBeInTheDocument()
    expect(screen.getByText('+5.5%')).toBeInTheDocument()
  })

  it('says on screen that the fuel split is a yearly average, not this month', async () => {
    // The figures are real EPPO data, so the caveat is no longer "this is a
    // guess" - it is "this is the wrong time resolution", which is the thing a
    // viewer could otherwise not tell from the chart.
    vi.spyOn(api, 'getGridCarbon').mockResolvedValue(makeCarbon())
    renderPanel()

    expect(await screen.findByText(/ค่าเฉลี่ยทั้งปี/)).toBeInTheDocument()
  })

  it('drops the yearly-average caveat once a real mix has been entered', async () => {
    // The caveat is the only thing gated on origin - the mix itself is always
    // listed, so a configured deployment still shows what it is running on.
    vi.spyOn(api, 'getGridCarbon').mockResolvedValue(
      makeCarbon({ mix_origin: 'published', mix_note: 'สัดส่วนเชื้อเพลิงชุดนี้ถูกกรอกไว้ในระบบเอง' }),
    )
    renderPanel()

    expect(await screen.findByText(/สัดส่วนเชื้อเพลิงที่ใช้จำลอง/)).toBeInTheDocument()
    expect(screen.queryByText(/ค่าเฉลี่ยทั้งปี/)).not.toBeInTheDocument()
  })

  it('names the marginal fuel rather than only charting a number', async () => {
    vi.spyOn(api, 'getGridCarbon').mockResolvedValue(makeCarbon())
    renderPanel()

    expect(await screen.findByText('ก๊าซธรรมชาติ')).toBeInTheDocument()
  })

  it('says why there is nothing to show instead of drawing an empty chart', async () => {
    vi.spyOn(api, 'getGridCarbon').mockResolvedValue(
      makeCarbon({ available: false, reason: 'ยังดึงเส้นโหลดของระบบไฟฟ้าจาก กฟผ. ไม่ได้', hours: [] }),
    )
    renderPanel()

    expect(await screen.findByText(/ยังดึงเส้นโหลด/)).toBeInTheDocument()
  })
})

describe('the marginal fuel it names', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('names the fuel from the hour the array produces most, not the middle row', async () => {
    // EGAT publishes the day SO FAR, so the middle of the array is wherever
    // "now" is - mid-morning at 13:00 - which is neither midday nor when this
    // array generates most. Reading the middle row was the original bug.
    const carbon = makeCarbon()
    carbon.hours = [
      { ...carbon.hours[0], hour: 3, site_generation_kwh: 0, marginal_fuel_label: 'ถ่านหิน/ลิกไนต์' },
      { ...carbon.hours[0], hour: 8, site_generation_kwh: 40, marginal_fuel_label: 'นำเข้า (ส่วนใหญ่พลังน้ำ สปป.ลาว)' },
      { ...carbon.hours[0], hour: 12, site_generation_kwh: 320, marginal_fuel_label: 'ก๊าซธรรมชาติ' },
    ]
    vi.spyOn(api, 'getGridCarbon').mockResolvedValue(carbon)
    renderPanel()

    // Middle row is 08:00; the answer must be the 12:00 one.
    expect(await screen.findByText('ก๊าซธรรมชาติ')).toBeInTheDocument()
    expect(screen.queryByText('นำเข้า (ส่วนใหญ่พลังน้ำ สปป.ลาว)')).not.toBeInTheDocument()
  })

  it('shows a dash rather than a fuel name when the array produced nothing', async () => {
    const carbon = makeCarbon()
    carbon.hours = carbon.hours.map((h) => ({ ...h, site_generation_kwh: 0 }))
    vi.spyOn(api, 'getGridCarbon').mockResolvedValue(carbon)
    renderPanel()

    expect(await screen.findByText('0.476')).toBeInTheDocument()
    expect(screen.queryByText('ก๊าซธรรมชาติ')).not.toBeInTheDocument()
  })
})

describe('the peak-hour spike', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('explains the spike when a second fuel takes the top of the peak', async () => {
    // Under Thailand's mix the marginal line is near-flat, so a visible step is
    // conspicuous. It comes from applying an ANNUAL oil share to a SINGLE day,
    // which over-attributes - leaving it unexplained would look like a bug or,
    // worse, like a measurement.
    const carbon = makeCarbon()
    carbon.hours = [
      { ...carbon.hours[0], hour: 12, site_generation_kwh: 320, marginal_fuel_label: 'ก๊าซธรรมชาติ' },
      { ...carbon.hours[0], hour: 20, site_generation_kwh: 0, marginal_fuel_label: 'น้ำมัน/ดีเซล (เดินเครื่องช่วงพีค)' },
    ]
    vi.spyOn(api, 'getGridCarbon').mockResolvedValue(carbon)
    renderPanel()

    expect(await screen.findByText(/เส้น marginal มีจุดกระโดดช่วงพีค/)).toBeInTheDocument()
    expect(screen.getByText(/น้ำมัน\/ดีเซล/)).toBeInTheDocument()
  })

  it('stays quiet when one fuel is marginal all day', async () => {
    vi.spyOn(api, 'getGridCarbon').mockResolvedValue(makeCarbon())
    renderPanel()

    expect(await screen.findByText('ก๊าซธรรมชาติ')).toBeInTheDocument()
    expect(screen.queryByText(/จุดกระโดดช่วงพีค/)).not.toBeInTheDocument()
  })
})
