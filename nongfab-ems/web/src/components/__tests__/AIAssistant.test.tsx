import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AIAssistant } from '../AIAssistant'
import { AuthProvider } from '../../lib/auth'
import * as api from '../../lib/api'
import type { PerformanceResponse } from '../../lib/types'

function makePerformance(zone: string, ac_kw: number): PerformanceResponse {
  return {
    zone,
    simulated_zone: false,
    latitude: 12.68,
    longitude: 101.12,
    ac_energy_kwh_today: 0,
    poa_irradiance_kwh_per_m2_today: 0,
    performance_ratio: 0,
    specific_yield_kwh_per_kwp_today: 0,
    loss_breakdown: {},
    hourly: [{ timestamp: new Date().toISOString(), ac_kw, ssrd_w_m2: 500, temp_c: 30 }],
    history: [],
    cloud_factor: 0.5,
  }
}

function renderAssistant() {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <AuthProvider>
      <AIAssistant />
    </AuthProvider>,
  )
}

describe('AIAssistant', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('starts closed - only the mascot button is visible, no chat panel', () => {
    renderAssistant()
    expect(screen.getByRole('button', { name: /เปิดผู้ช่วย AI/i })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('opens the chat panel with a greeting when the mascot is clicked', async () => {
    const user = userEvent.setup()
    renderAssistant()

    await user.click(screen.getByRole('button', { name: /เปิดผู้ช่วย AI/i }))

    expect(await screen.findByRole('dialog', { name: /ผู้ช่วย AI/i })).toBeInTheDocument()
    expect(screen.getByText(/ผมชื่อ "น้อง Solar"/)).toBeInTheDocument()
  })

  it('closes the panel when the mascot is clicked again', async () => {
    const user = userEvent.setup()
    renderAssistant()

    const toggle = screen.getByRole('button', { name: /เปิดผู้ช่วย AI/i })
    await user.click(toggle)
    expect(await screen.findByRole('dialog')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /ปิดผู้ช่วย AI/i }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes the panel via its own close (x) button too', async () => {
    const user = userEvent.setup()
    renderAssistant()

    await user.click(screen.getByRole('button', { name: /เปิดผู้ช่วย AI/i }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'ปิดหน้าต่างผู้ช่วย' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('clicking a quick-reply chip sends the question and shows a real-data-grounded answer', async () => {
    vi.spyOn(api, 'getPerformance').mockImplementation((zone) =>
      Promise.resolve(makePerformance(zone, { GIS: 10, ISB: 20, Jetty: 30 }[zone] ?? 0)),
    )
    const user = userEvent.setup()
    renderAssistant()
    await user.click(screen.getByRole('button', { name: /เปิดผู้ช่วย AI/i }))

    await user.click(await screen.findByRole('button', { name: 'ตอนนี้ผลิตไฟเท่าไหร่' }))

    expect(await screen.findByText(/60\.0 kW/)).toBeInTheDocument()
  })

  it('typing a question and pressing send shows the assistant response', async () => {
    const user = userEvent.setup()
    renderAssistant()
    await user.click(screen.getByRole('button', { name: /เปิดผู้ช่วย AI/i }))

    const input = await screen.findByLabelText('พิมพ์คำถามถึงผู้ช่วย AI')
    await user.type(input, 'kWp คือ อะไร')
    await user.click(screen.getByRole('button', { name: 'ส่ง' }))

    await waitFor(() => expect(screen.getByText(/กิโลวัตต์พีค/)).toBeInTheDocument())
    expect(screen.getByText('kWp คือ อะไร')).toBeInTheDocument() // the user's own message echoed back
  })

  it('the mascot smiles after a real answer and looks sad after a fallback', async () => {
    const user = userEvent.setup()
    const { container } = renderAssistant()
    await user.click(screen.getByRole('button', { name: /เปิดผู้ช่วย AI/i }))
    const mouth = () => container.querySelector('.mascot-mouth')?.getAttribute('d')
    const idleMouth = mouth()

    const input = await screen.findByLabelText('พิมพ์คำถามถึงผู้ช่วย AI')
    await user.type(input, 'kWp คือ อะไร')
    await user.click(screen.getByRole('button', { name: 'ส่ง' }))
    await waitFor(() => expect(mouth()).not.toBe(idleMouth))
    const happyMouth = mouth()

    await user.clear(input)
    await user.type(input, 'อยากรู้เรื่องดวงจันทร์')
    await user.click(screen.getByRole('button', { name: 'ส่ง' }))
    await waitFor(() => expect(mouth()).not.toBe(happyMouth))
  })

  describe('เล่นกับน้อง Solar (play interactions)', () => {
    it('the play panel is closed by default and opens on the 🎮 toggle, offering plenty of options', async () => {
      const user = userEvent.setup()
      renderAssistant()
      await user.click(screen.getByRole('button', { name: /เปิดผู้ช่วย AI/i }))

      expect(screen.queryByRole('group', { name: 'เล่นกับน้อง Solar' })).not.toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'เล่นกับน้อง Solar' }))
      const playGroup = screen.getByRole('group', { name: 'เล่นกับน้อง Solar' })
      expect(playGroup.querySelectorAll('button').length).toBeGreaterThanOrEqual(10)
    })

    it('petting the head visibly changes the mascot face and shows its speech bubble', async () => {
      const user = userEvent.setup()
      const { container } = renderAssistant()
      await user.click(screen.getByRole('button', { name: /เปิดผู้ช่วย AI/i }))
      const mouth = () => container.querySelector('.mascot-mouth')?.getAttribute('d')
      const idleMouth = mouth()

      await user.click(screen.getByRole('button', { name: 'เล่นกับน้อง Solar' }))
      await user.click(screen.getByRole('button', { name: '🤚 ลูบหัว' }))

      expect(mouth()).not.toBe(idleMouth)
      expect(await screen.findByText('ขอบคุณค้าบบ~ 😳')).toBeInTheDocument()
    })

    it('poking gives a distinctly different reaction than petting the head', async () => {
      const user = userEvent.setup()
      renderAssistant()
      await user.click(screen.getByRole('button', { name: /เปิดผู้ช่วย AI/i }))
      await user.click(screen.getByRole('button', { name: 'เล่นกับน้อง Solar' }))

      await user.click(screen.getByRole('button', { name: '👉 จิ้มแก้ม' }))
      expect(await screen.findByText('อย่าจิ้มเค้าาา!')).toBeInTheDocument()
    })

    it('does not add anything to the chat log - play interactions are purely visual on the mascot', async () => {
      const user = userEvent.setup()
      const { container } = renderAssistant()
      await user.click(screen.getByRole('button', { name: /เปิดผู้ช่วย AI/i }))
      await user.click(screen.getByRole('button', { name: 'เล่นกับน้อง Solar' }))
      const bubbleCountBefore = container.querySelectorAll('.assistant-bubble').length

      await user.click(screen.getByRole('button', { name: '🤗 กอด' }))

      // The speech bubble itself lives on the mascot, outside the chat
      // dialog - no new .assistant-bubble message should appear.
      expect(container.querySelectorAll('.assistant-bubble').length).toBe(bubbleCountBefore)
    })

    it('the panel stays open after an interaction, so rapid repeated play does not require reopening it', async () => {
      const user = userEvent.setup()
      renderAssistant()
      await user.click(screen.getByRole('button', { name: /เปิดผู้ช่วย AI/i }))
      await user.click(screen.getByRole('button', { name: 'เล่นกับน้อง Solar' }))

      await user.click(screen.getByRole('button', { name: '🤏 บีบแก้ม' }))
      await user.click(screen.getByRole('button', { name: '🌸 มอบดอกไม้' }))

      expect(await screen.findByText('ขอบคุณดอกไม้สวยๆ นะครับ 🌸')).toBeInTheDocument()
      expect(screen.getByRole('group', { name: 'เล่นกับน้อง Solar' })).toBeInTheDocument()
    })
  })
})
