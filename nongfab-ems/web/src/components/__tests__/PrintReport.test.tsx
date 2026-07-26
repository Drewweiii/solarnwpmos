import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { ProvenanceResponse } from '../../lib/types'
import { PrintReport } from '../PrintReport'

/** Project Q. The button is not the feature - the appendix is. These tests are
 * about the appendix being complete, ordered weakest-first, and honest when it
 * is not complete. */

function chain(key: string, weakest: string, weakestLabel: string): ProvenanceResponse {
  return {
    key,
    label: `ตัวเลข ${key}`,
    unit: 'kWh',
    steps: [
      {
        kind: 'setting',
        label: 'ค่าที่ตั้งไว้',
        detail: 'รายละเอียดขั้นตอน',
        setting_key: 'financial.capex_per_kwp_thb',
        origin: weakest,
        origin_label: weakestLabel,
        registry_note: 'หมายเหตุจากทะเบียน',
        default_value: 30000,
        unit: 'บาท/kWp',
      },
    ],
    caveat: `ข้อควรระวังของ ${key}`,
    shown_on: [],
    weakest_origin: weakest,
    weakest_origin_label: weakestLabel,
    weakest_note: 'ขั้นที่อ่อนที่สุดในสาย',
  }
}

function renderReport(keys: string[]) {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <PrintReport valueKeys={keys} title="รายงานพลังงาน" subtitle="โซน GIS" nowIso="2026-07-26T03:00:00Z" />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('PrintReport', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    vi.stubGlobal('print', vi.fn())
  })

  it('renders the paper cover with an ICT timestamp, not UTC', () => {
    vi.spyOn(api, 'getProvenance').mockResolvedValue(chain('a', 'confirmed', 'ยืนยันแล้ว'))
    renderReport(['a'])
    // 03:00Z is 10:00 in Bangkok. Printing a report stamped with the UTC hour
    // would misdate it by seven hours for every reader.
    expect(screen.getByText(/10:00/)).toBeInTheDocument()
    expect(screen.getByText('รายงานพลังงาน')).toBeInTheDocument()
  })

  it('fetches no provenance until somebody asks to print', () => {
    const spy = vi.spyOn(api, 'getProvenance').mockResolvedValue(chain('a', 'confirmed', 'ยืนยันแล้ว'))
    renderReport(['a', 'b'])
    expect(spy).not.toHaveBeenCalled()
  })

  it('waits for every chain before opening the print dialog', async () => {
    vi.spyOn(api, 'getProvenance').mockResolvedValue(chain('a', 'derived', 'คำนวณมา'))
    renderReport(['a'])
    // Printing mid-flight would produce a report whose appendix said "loading".
    expect(window.print).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: /พิมพ์/ }))
    await waitFor(() => expect(window.print).toHaveBeenCalled())
  })

  it('orders the appendix weakest-first', async () => {
    vi.spyOn(api, 'getProvenance').mockImplementation(async (key: string) =>
      key === 'solid' ? chain('solid', 'confirmed', 'ยืนยันแล้ว') : chain('shaky', 'placeholder', 'ค่าประมาณ'),
    )
    renderReport(['solid', 'shaky'])
    await userEvent.click(screen.getByRole('button', { name: /พิมพ์/ }))

    const labels = await screen.findAllByText(/^ตัวเลข /)
    // A reader skimming the appendix should meet the figures needing caution
    // before the solid ones, whatever order the requests happened to resolve in.
    expect(labels.map((el) => el.textContent)).toEqual(['ตัวเลข shaky (kWh)', 'ตัวเลข solid (kWh)'])
  })

  it('says the appendix is incomplete rather than silently dropping a figure', async () => {
    vi.spyOn(api, 'getProvenance').mockImplementation(async (key: string) => {
      if (key === 'broken') throw new Error('boom')
      return chain('ok', 'derived', 'คำนวณมา')
    })
    renderReport(['ok', 'broken'])
    await userEvent.click(screen.getByRole('button', { name: /พิมพ์/ }))
    expect(await screen.findByText(/ยังไม่ครบทุกตัวเลข/)).toBeInTheDocument()
  })

  it('carries each figure caveat onto paper', async () => {
    vi.spyOn(api, 'getProvenance').mockResolvedValue(chain('a', 'placeholder', 'ค่าประมาณ'))
    renderReport(['a'])
    await userEvent.click(screen.getByRole('button', { name: /พิมพ์/ }))
    // On screen the caveat lives behind the ⓘ popover. On paper there is no
    // popover, so it has to be printed or the number reads as fact.
    expect(await screen.findByText(/ข้อควรระวังของ a/)).toBeInTheDocument()
  })
})
