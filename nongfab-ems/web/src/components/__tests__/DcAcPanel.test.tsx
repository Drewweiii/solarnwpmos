import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { DcAcResponse, ZoneRatio } from '../../lib/types'
import { DcAcPanel, sizingLabel } from '../DcAcPanel'

/** The panel exists to correct an intuition: DC:AC 1.20 looks like it should be
 * clipping badly, and here it is not. Its one recommendation is ISB's free
 * inverter headroom, so these tests guard that it stays visible and correctly
 * labelled.
 */
function zone(overrides: Partial<ZoneRatio> = {}): ZoneRatio {
  return {
    zone_id: 'GIS',
    ac_capacity_kw: 50,
    built: {
      dc_ac_ratio: 1.2,
      dc_capacity_kwp: 60.06,
      delivered_kwh: 123_400,
      clipped_kwh: 122,
      clipping_loss_pct: 0.1,
      specific_yield_kwh_per_kwp: 2054,
    },
    curve: [],
    has_headroom: false,
    headroom_kwp: 0,
    marginal_kwh_per_added_kwp: 1884,
    ...overrides,
  }
}

function makeDcAc(overrides: Partial<DcAcResponse> = {}): DcAcResponse {
  return {
    zones: [
      zone(),
      zone({
        zone_id: 'ISB',
        ac_capacity_kw: 150,
        has_headroom: true,
        headroom_kwp: 9.9,
        marginal_kwh_per_added_kwp: 2056,
        built: {
          dc_ac_ratio: 0.93,
          dc_capacity_kwp: 140.14,
          delivered_kwh: 288_100,
          clipped_kwh: 0,
          clipping_loss_pct: 0,
          specific_yield_kwh_per_kwp: 2056,
        },
      }),
    ],
    total_clipped_kwh: 122,
    total_headroom_kwp: 9.9,
    method_note: 'คำนวณจากวันตัวแทน 12 เดือนด้วยแสงบนระนาบแผง (POA)',
    no_optimum_note: 'จงใจไม่บอกว่าอัตราส่วนที่ดีที่สุดคือเท่าไร เพราะราคาแผงยังเป็นค่าประมาณ ฿30,000/kWp',
    ...overrides,
  }
}

function renderPanel() {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <DcAcPanel />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('sizingLabel', () => {
  it('separates free headroom from over-sizing at the 1.0 boundary', () => {
    // Getting this backwards would invert the panel's only recommendation.
    expect(sizingLabel(zone({ has_headroom: true }))).toMatch(/ใส่แผงเพิ่มได้ฟรี/)
    expect(sizingLabel(zone({ built: { ...zone().built, clipping_loss_pct: 4 } }))).toMatch(/เริ่มมีการตัดยอด/)
  })

  it('calls a high ratio with negligible clipping balanced, not over-sized', () => {
    // GIS's actual case: 1.20 on paper, 0.1% clipping in reality. Labelling it
    // "over-sized" would repeat the very intuition this panel corrects.
    expect(sizingLabel(zone())).toMatch(/สมดุลดี/)
  })
})

describe('DcAcPanel', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('leads with the free inverter headroom and names the zone', async () => {
    vi.spyOn(api, 'getDcAc').mockResolvedValue(makeDcAc())
    renderPanel()

    expect(await screen.findByText('9.9')).toBeInTheDocument()
    expect(screen.getByText(/อยู่ที่ ISB/)).toBeInTheDocument()
  })

  it('says no optimal ratio is claimed while CAPEX is an estimate', async () => {
    vi.spyOn(api, 'getDcAc').mockResolvedValue(makeDcAc())
    renderPanel()

    expect(await screen.findByText(/30,000/)).toBeInTheDocument()
  })

  it('shows what the next kWp is worth, since that is what can be priced', async () => {
    vi.spyOn(api, 'getDcAc').mockResolvedValue(makeDcAc())
    renderPanel()

    expect(await screen.findByText('1,884 kWh/ปี')).toBeInTheDocument()
    expect(screen.getByText('2,056 kWh/ปี')).toBeInTheDocument()
  })

  it('says why there is nothing to show rather than drawing an empty table', async () => {
    vi.spyOn(api, 'getDcAc').mockRejectedValue(new Error('nope'))
    renderPanel()

    expect(await screen.findByText(/ยังคำนวณไม่ได้/)).toBeInTheDocument()
  })
})
