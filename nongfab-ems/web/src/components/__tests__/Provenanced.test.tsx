import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { ProvenanceResponse } from '../../lib/types'
import { Provenanced } from '../Provenanced'

/** Project O. The point of this component is that a reader can find out a
 * published number rests on a guess. The tests that matter are therefore about
 * the popover telling the truth loudly, not about it opening. */

function makeChain(overrides: Partial<ProvenanceResponse> = {}): ProvenanceResponse {
  return {
    key: 'financial.payback_years',
    label: 'ระยะเวลาคืนทุน',
    unit: 'ปี',
    steps: [
      {
        kind: 'setting',
        label: 'เงินลงทุนต่อกำลังติดตั้ง (CAPEX)',
        detail: 'ยังเป็นค่าประมาณ',
        setting_key: 'financial.capex_per_kwp_thb',
        origin: 'placeholder',
        origin_label: 'ค่าประมาณ',
        registry_note: 'ยังไม่ได้ราคาจริงของโครงการ',
        default_value: 30000,
        unit: 'บาท/kWp',
      },
      {
        kind: 'model',
        label: 'กระแสเงินสดรายปี',
        detail: 'ใช้อัตราเสื่อมตามใบรับประกันจริง',
        setting_key: null,
        origin: 'as-built',
        origin_label: 'ตามที่ติดตั้งจริง',
        registry_note: '',
        default_value: null,
        unit: '',
      },
    ],
    caveat: 'ระยะคืนทุนที่เห็นน่าจะมองแง่ร้ายเกินจริง',
    shown_on: ['หน้า Financial'],
    weakest_origin: 'placeholder',
    weakest_origin_label: 'ค่าประมาณ',
    weakest_note: 'ระดับความน่าเชื่อถือที่แสดงคือขั้นที่อ่อนที่สุดในสาย ไม่ใช่ค่าเฉลี่ย',
    ...overrides,
  }
}

function renderWrapped(key = 'financial.payback_years') {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Provenanced valueKey={key}>Simple payback</Provenanced>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('Provenanced', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('fetches nothing until the reader asks', async () => {
    const spy = vi.spyOn(api, 'getProvenance').mockResolvedValue(makeChain())
    renderWrapped()
    // A page can carry half a dozen of these. If merely rendering one cost a
    // request, the feature would tax every page that uses it.
    expect(spy).not.toHaveBeenCalled()
    expect(screen.getByText('Simple payback')).toBeInTheDocument()
  })

  it('shows the whole chain, and the weakest link as the headline', async () => {
    vi.spyOn(api, 'getProvenance').mockResolvedValue(makeChain())
    renderWrapped()
    await userEvent.click(screen.getByRole('button', { name: 'ตัวเลขนี้มาจากไหน' }))

    // The chain contains a stronger link too - the headline must still be the
    // weakest one, or a number resting on a guess would read as sound.
    expect(await screen.findByText('ตามที่ติดตั้งจริง')).toBeInTheDocument()
    const headline = screen.getByText('ขั้นที่อ่อนที่สุดในสาย').closest('div')
    expect(headline).toHaveClass('prov-origin-placeholder')
    expect(headline).toHaveTextContent('ค่าประมาณ')
  })

  it("prints the setting's live registry note and current value", async () => {
    vi.spyOn(api, 'getProvenance').mockResolvedValue(makeChain())
    renderWrapped()
    await userEvent.click(screen.getByRole('button', { name: 'ตัวเลขนี้มาจากไหน' }))

    expect(await screen.findByText('financial.capex_per_kwp_thb')).toBeInTheDocument()
    expect(screen.getByText(/30,000 บาท\/kWp/)).toBeInTheDocument()
    expect(screen.getByText(/ยังไม่ได้ราคาจริงของโครงการ/)).toBeInTheDocument()
  })

  it('always shows the caveat', async () => {
    vi.spyOn(api, 'getProvenance').mockResolvedValue(makeChain())
    renderWrapped()
    await userEvent.click(screen.getByRole('button', { name: 'ตัวเลขนี้มาจากไหน' }))
    expect(await screen.findByText(/มองแง่ร้ายเกินจริง/)).toBeInTheDocument()
  })

  it('says it could not trace the number rather than rendering an empty chain', async () => {
    vi.spyOn(api, 'getProvenance').mockRejectedValue(new Error('boom'))
    renderWrapped()
    await userEvent.click(screen.getByRole('button', { name: 'ตัวเลขนี้มาจากไหน' }))
    expect(await screen.findByText(/ยังดึงที่มาของตัวเลขนี้ไม่ได้/)).toBeInTheDocument()
  })

  it('closes on Escape', async () => {
    vi.spyOn(api, 'getProvenance').mockResolvedValue(makeChain())
    renderWrapped()
    await userEvent.click(screen.getByRole('button', { name: 'ตัวเลขนี้มาจากไหน' }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
