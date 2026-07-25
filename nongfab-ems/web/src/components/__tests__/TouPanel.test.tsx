import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { TouResponse } from '../../lib/types'
import { TouPanel } from '../TouPanel'

/** The panel must not imply the Savings page has been corrected. It has not -
 * the off-peak rate ships equal to the peak rate, so nothing has moved. Until a
 * real rate is entered the overstatement is unknowable, and saying "+0.0%"
 * would read as "there is no overstatement", which is a different claim.
 */
function makeTou(overrides: Partial<TouResponse> = {}): TouResponse {
  return {
    zones: [
      { zone_id: 'GIS', peak_kwh: 77_700, offpeak_kwh: 37_900, peak_share_pct: 67.2, offpeak_share_pct: 32.8 },
      { zone_id: 'Jetty', peak_kwh: 279_400, offpeak_kwh: 130_800, peak_share_pct: 68.1, offpeak_share_pct: 31.9 },
    ],
    total_peak_kwh: 575_390,
    total_offpeak_kwh: 274_719,
    offpeak_share_pct: 32.3,
    peak_rate_thb_per_kwh: 4.1025,
    offpeak_rate_thb_per_kwh: 4.1025,
    blended_rate_thb_per_kwh: 4.1025,
    overstatement_pct: 0,
    offpeak_rate_is_set: false,
    offpeak_holiday_days: 0,
    window_note: 'ช่วง On Peak คือ 09:00–22:00 เฉพาะวันจันทร์–ศุกร์',
    finding_note: 'เสาร์-อาทิตย์ผลิตเป็น Off-Peak ทั้งวัน และช่วง 06:00–09:00 ก็เป็น Off-Peak',
    holiday_note: 'ยังไม่ได้นับวันหยุด สัดส่วน Peak ที่เห็นจึงเป็นเพดานบน',
    ...overrides,
  }
}

function renderPanel() {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <TouPanel />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('TouPanel', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('leads with the share falling outside the peak window', async () => {
    vi.spyOn(api, 'getTou').mockResolvedValue(makeTou())
    renderPanel()

    expect(await screen.findByText('32.3%')).toBeInTheDocument()
  })

  it('refuses to quote an overstatement before the real rate is entered', async () => {
    // "+0.0%" would read as "there is no overstatement" - a claim the data
    // cannot support while both rates are the same placeholder.
    vi.spyOn(api, 'getTou').mockResolvedValue(makeTou())
    renderPanel()

    expect(await screen.findByText('ยังบอกไม่ได้')).toBeInTheDocument()
    expect(screen.getByText(/เท่าเดิมทุกประการ/)).toBeInTheDocument()
  })

  it('shows the gap once a real off-peak rate is in place', async () => {
    vi.spyOn(api, 'getTou').mockResolvedValue(
      makeTou({ offpeak_rate_is_set: true, offpeak_rate_thb_per_kwh: 2.6, blended_rate_thb_per_kwh: 3.617, overstatement_pct: 13.4 }),
    )
    renderPanel()

    expect(await screen.findByText('+13.4%')).toBeInTheDocument()
    expect(screen.queryByText(/เท่าเดิมทุกประการ/)).not.toBeInTheDocument()
  })

  it('says the peak share is a ceiling because holidays are not counted', async () => {
    vi.spyOn(api, 'getTou').mockResolvedValue(makeTou())
    renderPanel()

    expect(await screen.findByText(/เพดานบน/)).toBeInTheDocument()
  })
})
