import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { SettingItem, SettingsResponse } from '../../lib/types'
import { pendingChanges, SettingsPage } from '../SettingsPage'

function makeToken(sub: string, role: string) {
  const payload = btoa(JSON.stringify({ sub, role })).replace(/\+/g, '-').replace(/\//g, '_')
  return `header.${payload}.sig`
}
const ADMIN_TOKEN = makeToken('admin', 'admin')
const VIEWER_TOKEN = makeToken('pttlng', 'viewer')

function setting(overrides: Partial<SettingItem> = {}): SettingItem {
  return {
    key: 'financial.capex_thb_per_kwp',
    group: 'financial',
    group_label: 'สมมติฐานการเงิน (Financial assumptions)',
    label: 'CAPEX ต่อกำลังติดตั้ง',
    unit: 'บาท/kWp',
    default: 30000,
    value: 30000,
    minimum: 1000,
    maximum: 200000,
    step: 100,
    origin: 'placeholder',
    origin_label: 'ค่าประมาณ ยังไม่ยืนยันกับโครงการนี้',
    note: 'ยังไม่ได้ยืนยันกับโครงการนี้',
    frontend_only: false,
    overridden: false,
    updated_at: null,
    updated_by: null,
    ...overrides,
  }
}

function response(overrides: Partial<SettingsResponse> = {}): SettingsResponse {
  return {
    settings: [
      setting(),
      setting({
        key: 'losses.soiling_pct',
        group: 'losses',
        group_label: 'การสูญเสียของระบบ (Loss factors)',
        label: 'ฝุ่น/คราบสกปรก',
        unit: '%',
        default: 2,
        value: 3.5,
        minimum: 0,
        maximum: 30,
        step: 0.1,
        origin: 'literature',
        origin_label: 'ค่าอ้างอิงจากงานวิจัย/มาตรฐาน ไม่ได้วัดที่ไซต์นี้',
        overridden: true,
        updated_at: '2026-07-25T02:00:00Z',
        updated_by: 'admin',
      }),
    ],
    groups: { financial: 'สมมติฐานการเงิน (Financial assumptions)', losses: 'การสูญเสียของระบบ (Loss factors)' },
    origins: { placeholder: 'ค่าประมาณ ยังไม่ยืนยันกับโครงการนี้' },
    can_publish: true,
    ...overrides,
  }
}

function renderPage(token = ADMIN_TOKEN) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', token)
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <SettingsPage />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('pendingChanges', () => {
  it('keeps only drafted values that actually differ from the published one', () => {
    const items = [setting({ key: 'a', value: 10 }), setting({ key: 'b', value: 20 })]
    expect(pendingChanges(items, { a: 10, b: 25 })).toEqual({ b: 25 })
  })

  it('is empty when nothing was drafted', () => {
    expect(pendingChanges([setting({ key: 'a', value: 10 })], {})).toEqual({})
  })
})

describe('SettingsPage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('renders every group and field from the API metadata, with units and origin', async () => {
    vi.spyOn(api, 'getSettings').mockResolvedValue(response())
    renderPage()

    expect(await screen.findByText(/สมมติฐานการเงิน/)).toBeInTheDocument()
    expect(screen.getByText(/การสูญเสียของระบบ/)).toBeInTheDocument()
    // label + unit come from metadata, never hardcoded in the page
    expect(screen.getByLabelText(/CAPEX ต่อกำลังติดตั้ง/)).toHaveValue(30000)
    expect(screen.getByText(/ค่าประมาณ ยังไม่ยืนยัน/)).toBeInTheDocument()
  })

  it('keeps a typed value as a local draft and offers to publish only the changed one', async () => {
    vi.spyOn(api, 'getSettings').mockResolvedValue(response())
    const put = vi.spyOn(api, 'putSettings').mockResolvedValue({ updated: {}, settings: response().settings })
    const user = userEvent.setup()
    renderPage()

    const capex = await screen.findByLabelText(/CAPEX ต่อกำลังติดตั้ง/)
    await user.clear(capex)
    await user.type(capex, '45000')

    expect(screen.getByText(/แก้ไว้ 1 ค่า/)).toBeInTheDocument()
    // the draft survives a reload - it lives in localStorage, per-browser
    expect(JSON.parse(localStorage.getItem('nongfab_settings_draft')!)).toMatchObject({
      'financial.capex_thb_per_kwp': 45000,
    })

    await user.click(screen.getByRole('button', { name: /บันทึกเป็นค่ากลาง/ }))
    await waitFor(() => expect(put).toHaveBeenCalled())
    // only the changed key is sent, not the whole form
    expect(put.mock.calls[0][0]).toEqual({ 'financial.capex_thb_per_kwp': 45000 })
  })

  it('hides publishing from a non-admin but still lets them try values locally', async () => {
    vi.spyOn(api, 'getSettings').mockResolvedValue(response({ can_publish: false }))
    const user = userEvent.setup()
    renderPage(VIEWER_TOKEN)

    const capex = await screen.findByLabelText(/CAPEX ต่อกำลังติดตั้ง/)
    await user.clear(capex)
    await user.type(capex, '31000')

    expect(screen.queryByRole('button', { name: /บันทึกเป็นค่ากลาง/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /คืนค่าตั้งต้นทั้งหมด/ })).not.toBeInTheDocument()
    // ...but the local draft still worked
    expect(screen.getByText(/แก้ไว้ 1 ค่า/)).toBeInTheDocument()
  })

  it('offers a per-field reset only for a published override, and calls DELETE for it', async () => {
    vi.spyOn(api, 'getSettings').mockResolvedValue(response())
    const del = vi.spyOn(api, 'deleteSetting').mockResolvedValue({ updated: {}, settings: response().settings })
    const user = userEvent.setup()
    const { container } = renderPage()

    await screen.findByLabelText(/CAPEX ต่อกำลังติดตั้ง/)
    const fields = container.querySelectorAll('.settings-field')
    // field 0 is not overridden -> no reset; field 1 is -> has one
    expect(within(fields[0] as HTMLElement).queryByRole('button', { name: 'คืนค่าตั้งต้น' })).not.toBeInTheDocument()
    const reset = within(fields[1] as HTMLElement).getByRole('button', { name: 'คืนค่าตั้งต้น' })

    await user.click(reset)
    await waitFor(() => expect(del).toHaveBeenCalledWith('losses.soiling_pct', expect.any(String)))
  })

  it('shows who last published an override and when', async () => {
    vi.spyOn(api, 'getSettings').mockResolvedValue(response())
    renderPage()
    expect(await screen.findByText(/แก้ล่าสุดโดย admin/)).toBeInTheDocument()
    expect(screen.getByText('แอดมินตั้งค่าไว้')).toBeInTheDocument()
  })

  it('warns when a typed value falls outside the allowed range', async () => {
    vi.spyOn(api, 'getSettings').mockResolvedValue(response())
    const user = userEvent.setup()
    renderPage()

    const capex = await screen.findByLabelText(/CAPEX ต่อกำลังติดตั้ง/)
    await user.clear(capex)
    await user.type(capex, '5') // below the 1000 minimum
    expect(screen.getByText(/ต้องอยู่ระหว่าง 1000 ถึง 200000/)).toBeInTheDocument()
  })

  it('shows an error state when the settings request fails', async () => {
    vi.spyOn(api, 'getSettings').mockRejectedValue(new Error('boom'))
    renderPage()
    expect(await screen.findByText(/โหลดค่าระบบไม่สำเร็จ/)).toBeInTheDocument()
  })
})
