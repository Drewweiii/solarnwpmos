import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { GridCarbonResponse } from '../../lib/types'
import { buildCarbonRows, GridCarbonPanel } from '../GridCarbonPanel'

/** The panel's job is to say an uncomfortable thing accurately: the fuel split
 * driving its shape is a placeholder, the site profile is clear-sky rather than
 * metered, and the headline factor differs from the one the Energy Report
 * publishes. These tests pin those labels, because losing one of them would
 * turn an honest model into a fabricated measurement.
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
    mix_origin: 'placeholder',
    mix_note: 'สัดส่วนเชื้อเพลิงชุดนี้เป็นค่าประมาณ ยังไม่ได้ยืนยันกับตารางรายเดือนของ EPPO/กฟผ.',
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

  it('warns on screen that the fuel split is a placeholder, not an EPPO table', async () => {
    vi.spyOn(api, 'getGridCarbon').mockResolvedValue(makeCarbon())
    renderPanel()

    expect(await screen.findByText(/EPPO/)).toBeInTheDocument()
  })

  it('drops the placeholder warning once a real mix has been entered', async () => {
    // The warning is the only thing gated on origin - the mix itself is always
    // listed, so a published deployment still shows what it is running on, just
    // without the caveat.
    vi.spyOn(api, 'getGridCarbon').mockResolvedValue(
      makeCarbon({ mix_origin: 'published', mix_note: 'สัดส่วนเชื้อเพลิงชุดนี้ถูกกรอกไว้ในระบบแล้ว' }),
    )
    renderPanel()

    expect(await screen.findByText(/สัดส่วนเชื้อเพลิงที่ใช้จำลอง/)).toBeInTheDocument()
    expect(screen.queryByText(/EPPO/)).not.toBeInTheDocument()
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
