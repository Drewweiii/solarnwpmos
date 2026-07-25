import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { OrientationResponse } from '../../lib/types'
import { compassLabel, OrientationPanel } from '../OrientationPanel'

/** The panel's hard requirement: never let a reader think somebody measured the
 * array. No zone's tilt was ever surveyed, so the gain column compares against
 * an assumption - and that has to be visible in the row, not just in a note.
 */
function makeOrientation(overrides: Partial<OrientationResponse> = {}): OrientationResponse {
  return {
    zones: [
      {
        zone_id: 'GIS',
        current: { tilt_deg: 10, azimuth_deg: 180, poa_kwh_per_m2: 2428, shading_loss_pct: 0, effective_kwh_per_m2: 2428 },
        optimum: { tilt_deg: 14, azimuth_deg: 180, poa_kwh_per_m2: 2432, shading_loss_pct: 0.01, effective_kwh_per_m2: 2432 },
        current_is_measured: false,
        gain_pct: 0.16,
        gain_kwh_per_m2_year: 4,
        row_pitch_m: 3,
        note: null,
      },
      {
        zone_id: 'Jetty',
        current: { tilt_deg: 10, azimuth_deg: 270, poa_kwh_per_m2: 2345, shading_loss_pct: 0, effective_kwh_per_m2: 2345 },
        optimum: { tilt_deg: 14, azimuth_deg: 180, poa_kwh_per_m2: 2432, shading_loss_pct: 0.01, effective_kwh_per_m2: 2432 },
        current_is_measured: false,
        gain_pct: 3.69,
        gain_kwh_per_m2_year: 87,
        row_pitch_m: 3,
        note: 'Jetty เป็นแผงบนสะพาน ทิศของแผงถูกบังคับด้วยแนวสะพานเป็นหลัก',
      },
    ],
    any_unmeasured: true,
    method_note: 'คำนวณแสงที่ตกบนระนาบแผงด้วยแบบจำลอง Hay-Davies',
    pipeline_note: 'หน้าอื่นของเว็บยังคำนวณจากแสงแนวนอน (GHI) เหมือนเดิม',
    unmeasured_note: '⚠️ มุมเอียงและทิศของแผงจริง ยังไม่เคยวัด',
    expansion_note: 'เฟสขยายที่ยังไม่ได้สร้าง ควรออกแบบที่มุมที่ดีที่สุดตั้งแต่แรก',
    ...overrides,
  }
}

function renderPanel() {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <OrientationPanel />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('compassLabel', () => {
  it('names the cardinal directions', () => {
    expect(compassLabel(0)).toBe('เหนือ')
    expect(compassLabel(90)).toBe('ตะวันออก')
    expect(compassLabel(180)).toBe('ใต้')
    expect(compassLabel(270)).toBe('ตะวันตก')
  })

  it('wraps around rather than falling off the end', () => {
    // 360 and 0 are the same bearing; a naive index would read past the array.
    expect(compassLabel(360)).toBe('เหนือ')
    expect(compassLabel(-90)).toBe('ตะวันตก')
  })
})

describe('OrientationPanel', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('warns that the array was never surveyed, and marks it per row', async () => {
    vi.spyOn(api, 'getOrientation').mockResolvedValue(makeOrientation())
    renderPanel()

    expect(await screen.findByText(/ยังไม่เคยวัด/)).toBeInTheDocument()
    // Once per zone - a single warning at the top is easy to scroll past while
    // reading a row.
    expect(screen.getAllByText(/ค่าสมมติ/)).toHaveLength(2)
  })

  it('reports a zone already at its best as such rather than as a tiny gain', async () => {
    // "+0.0%" reads like a real but negligible loss; it is actually "nothing to
    // do here", which is a different message.
    vi.spyOn(api, 'getOrientation').mockResolvedValue(
      makeOrientation({
        zones: [{ ...makeOrientation().zones[0], gain_pct: 0.0 }],
      }),
    )
    renderPanel()

    expect(await screen.findByText('ตรงจุดที่ดีที่สุดแล้ว')).toBeInTheDocument()
  })

  it('shows the west-facing zone its real gap', async () => {
    vi.spyOn(api, 'getOrientation').mockResolvedValue(makeOrientation())
    renderPanel()

    expect(await screen.findByText('+3.7%')).toBeInTheDocument()
    expect(screen.getByText(/แนวสะพาน/)).toBeInTheDocument()
  })

  it('says the optimum in compass terms, not just degrees', async () => {
    // Queried at cell level: JSX splits "14° / 180° (ใต้)" across several text
    // nodes, so a plain text match only ever sees the fragments.
    vi.spyOn(api, 'getOrientation').mockResolvedValue(makeOrientation())
    renderPanel()

    await screen.findByText('GIS')
    const cells = screen.getAllByRole('cell').map((c) => c.textContent?.replace(/\s+/g, ' ').trim())
    expect(cells).toContain('14° / 180° (ใต้)')
  })
})
