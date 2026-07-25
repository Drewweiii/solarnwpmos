import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { OfficialSourceItem, SourcesResponse } from '../../lib/types'
import { OfficialSourcesPanel } from '../OfficialSourcesPanel'

function makeSource(overrides: Partial<OfficialSourceItem> = {}): OfficialSourceItem {
  return {
    key: 'pea_tariff',
    agency: 'กฟภ.',
    agency_full: 'การไฟฟ้าส่วนภูมิภาค (PEA)',
    page_url: 'https://www.pea.co.th/our-services/tariff',
    purpose: 'อัตราค่าไฟฟ้าที่ไซต์นี้ใช้จริง',
    quoted: [
      {
        label: 'ค่าไฟฟ้าอัตราปกติ TOU ช่วง Peak แรงดันสูง',
        value: '4.1025 บาท/kWh',
        code_location: 'api/green_savings.py: NORMAL_TOU_HV_PEAK_THB_PER_KWH',
        note: '',
      },
    ],
    watch_documents: true,
    status: 'ok',
    detail: 'รายการเอกสารทางการ 16 ฉบับ ตรงกับที่บันทึกไว้เมื่อ 2026-07-25',
    documents_now: [],
    added: [],
    removed: [],
    ...overrides,
  }
}

function makeResponse(overrides: Partial<SourcesResponse> = {}): SourcesResponse {
  return {
    overall_status: 'ok',
    checked_at: '2026-07-25T06:00:00Z',
    baseline_captured: '2026-07-25',
    sources: [makeSource()],
    method_note: 'ระบบไม่ได้อ่านตัวเลขจากประกาศโดยอัตโนมัติ',
    ...overrides,
  }
}

function renderPanel() {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <OfficialSourcesPanel />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('OfficialSourcesPanel', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('names the agency, what was taken from it, and where that lives in the code', async () => {
    // Without the code location the panel could say "this is stale" and leave
    // the reader no way to find the number.
    vi.spyOn(api, 'getOfficialSources').mockResolvedValue(makeResponse())
    renderPanel()
    expect(await screen.findByText('กฟภ.')).toBeInTheDocument()
    expect(screen.getByText('4.1025 บาท/kWh')).toBeInTheDocument()
    expect(screen.getByText('api/green_savings.py: NORMAL_TOU_HV_PEAK_THB_PER_KWH')).toBeInTheDocument()
  })

  it('links out to the official page with noopener/noreferrer', async () => {
    vi.spyOn(api, 'getOfficialSources').mockResolvedValue(makeResponse())
    renderPanel()
    const link = await screen.findByRole('link', { name: /เปิดหน้าเว็บทางการ/ })
    expect(link).toHaveAttribute('href', 'https://www.pea.co.th/our-services/tariff')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('raises an alert and lists the new documents when an agency republishes', async () => {
    vi.spyOn(api, 'getOfficialSources').mockResolvedValue(
      makeResponse({
        overall_status: 'changed',
        sources: [
          makeSource({
            status: 'changed',
            detail: 'มีเอกสารใหม่ 1 ฉบับ',
            added: ['ประกาศ กฟภ. UGT2 2570.pdf'],
          }),
        ],
      }),
    )
    renderPanel()
    expect(await screen.findByText(/มี 1 หน่วยงานที่เผยแพร่เอกสารใหม่/)).toBeInTheDocument()
    expect(screen.getByText('ประกาศ กฟภ. UGT2 2570.pdf')).toBeInTheDocument()
  })

  it('stays quiet when nothing has changed', async () => {
    vi.spyOn(api, 'getOfficialSources').mockResolvedValue(makeResponse())
    renderPanel()
    await screen.findByText('กฟภ.')
    expect(screen.queryByText(/เผยแพร่เอกสารใหม่/)).not.toBeInTheDocument()
  })

  it('surfaces a flagged value’s warning note verbatim', async () => {
    // The emission-factor discrepancy must reach the operator, not sit in a
    // docstring - it changes published carbon figures.
    vi.spyOn(api, 'getOfficialSources').mockResolvedValue(
      makeResponse({
        sources: [
          makeSource({
            quoted: [
              {
                label: 'Grid Emission Factor (scope 2)',
                value: '0.4999 kgCO₂/kWh',
                code_location: 'api/green_savings.py: EF_SCOPE2_KG_CO2_PER_KWH',
                note: '⚠️ เอกสารของ กกพ. ระบุ 0.4758 tCO₂/MWh ซึ่งไม่ตรงกับค่าที่ใช้อยู่',
              },
            ],
          }),
        ],
      }),
    )
    renderPanel()
    expect(await screen.findByText(/0\.4758 tCO₂\/MWh ซึ่งไม่ตรงกับค่าที่ใช้อยู่/)).toBeInTheDocument()
  })

  it('reports an unreachable agency as unchecked rather than as unchanged', async () => {
    vi.spyOn(api, 'getOfficialSources').mockResolvedValue(
      makeResponse({
        overall_status: 'unreachable',
        sources: [makeSource({ status: 'unreachable', detail: 'เข้าหน้าเว็บของหน่วยงานไม่ได้ในขณะนี้' })],
      }),
    )
    renderPanel()
    expect(await screen.findByText(/เข้าเว็บหน่วยงานไม่ได้/)).toBeInTheDocument()
    expect(screen.queryByText(/เผยแพร่เอกสารใหม่/)).not.toBeInTheDocument()
  })

  it('shows an honest failure state when the check itself cannot run', async () => {
    vi.spyOn(api, 'getOfficialSources').mockRejectedValue(new Error('boom'))
    renderPanel()
    expect(await screen.findByText('ตรวจสอบแหล่งอ้างอิงทางการไม่สำเร็จ')).toBeInTheDocument()
  })
})
