import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { BifacialResponse } from '../../lib/types'
import { BifacialPanel } from '../BifacialPanel'

/** This panel reports a 3-15% uplift that is NOT in any published figure. The
 * tests guard the two things that keep that honest: the disclaimer, and the two
 * assumed inputs travelling in the same row as the number they produced.
 */
function makeBifacial(overrides: Partial<BifacialResponse> = {}): BifacialResponse {
  return {
    zones: [
      {
        zone_id: 'GIS',
        ground_kind: 'ground',
        ground_label: 'พื้นลานโล่ง',
        gain_pct: 10.93,
        gain_pct_low: 10.25,
        gain_pct_high: 11.62,
        albedo_assumed: 0.25,
        height_m_assumed: 1.5,
        ground_cover_ratio: 0.43,
      },
      {
        zone_id: 'Jetty',
        ground_kind: 'water',
        ground_label: 'เหนือผิวน้ำทะเล',
        gain_pct: 3.33,
        gain_pct_low: 3.12,
        gain_pct_high: 3.54,
        albedo_assumed: 0.07,
        height_m_assumed: 4.0,
        ground_cover_ratio: 0.43,
      },
    ],
    bifaciality: 0.8,
    module_note: 'แผงที่ติดตั้งจริงคือ Trina Vertex N TSM-NEG21C.20 แบบ bifacial',
    not_applied_note: '⚠️ ตัวเลขนี้ยังไม่ได้ถูกนำไปบวกในพลังงานที่เว็บเผยแพร่ เพราะขึ้นกับ albedo และความสูงที่ไม่ได้วัด',
    method_note: 'ใช้แบบจำลอง infinite_sheds ของ pvlib',
    unlock_note: 'ถ้าวัด albedo และความสูงจริงมาได้ ตัวเลขนี้จะนำไปบวกได้',
    ...overrides,
  }
}

function renderPanel() {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <BifacialPanel />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('BifacialPanel', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('says the gain is not included in the published figures', async () => {
    // Without this the panel reads as free energy the payback already counts.
    vi.spyOn(api, 'getBifacial').mockResolvedValue(makeBifacial())
    renderPanel()

    expect(await screen.findByText(/ยังไม่ได้ถูกนำไปบวก/)).toBeInTheDocument()
  })

  it('puts the assumed albedo and height in the same row as the number', async () => {
    vi.spyOn(api, 'getBifacial').mockResolvedValue(makeBifacial())
    renderPanel()

    await screen.findByText('GIS')
    const cells = screen.getAllByRole('cell').map((c) => c.textContent?.trim())
    expect(cells).toContain('0.25')
    expect(cells).toContain('1.5 ม.')
  })

  it('shows the jetty as the low-albedo case rather than a site-wide average', async () => {
    // A single uplift across the site would overstate the jetty several times.
    vi.spyOn(api, 'getBifacial').mockResolvedValue(makeBifacial())
    renderPanel()

    expect(await screen.findByText(/เหนือผิวน้ำทะเล/)).toBeInTheDocument()
    expect(screen.getByText(/3.1–3.5%/)).toBeInTheDocument()
  })

  it('shows the band, not just a single number', async () => {
    // The datasheet's bifaciality is 80 +/- 5%, so the answer cannot be exact.
    vi.spyOn(api, 'getBifacial').mockResolvedValue(makeBifacial())
    renderPanel()

    expect(await screen.findByText(/10.3–11.6%/)).toBeInTheDocument()
  })
})
