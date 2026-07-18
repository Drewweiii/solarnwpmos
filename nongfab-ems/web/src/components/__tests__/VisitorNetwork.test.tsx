import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import { MockWebSocket } from '../../lib/__tests__/mockWebSocket'
import { VisitorNetwork } from '../VisitorNetwork'

function renderWidget() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <VisitorNetwork />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('VisitorNetwork', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    MockWebSocket.instances.length = 0
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  it('starts closed with just the toggle button visible', () => {
    renderWidget()
    expect(screen.getByRole('button', { name: 'เปิดหน้าต่างเครือข่ายผู้ชม' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('opens the panel on the chat tab and shows history replayed by the server', async () => {
    const user = userEvent.setup()
    renderWidget()
    await user.click(screen.getByRole('button', { name: 'เปิดหน้าต่างเครือข่ายผู้ชม' }))

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() =>
      ws.emit({
        type: 'history',
        messages: [{ type: 'message', id: 1, username: 'alice', role: 'viewer', text: 'สวัสดีค่ะ', created_at: '2026-01-01T00:00:00Z' }],
      }),
    )

    expect(await screen.findByText('สวัสดีค่ะ')).toBeInTheDocument()
  })

  it('sending a chat message goes out over the socket', async () => {
    const user = userEvent.setup()
    renderWidget()
    await user.click(screen.getByRole('button', { name: 'เปิดหน้าต่างเครือข่ายผู้ชม' }))
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit({ type: 'history', messages: [] }))

    const input = screen.getByLabelText('พิมพ์ข้อความแชท')
    await user.type(input, 'ทดสอบ')
    await user.click(screen.getByRole('button', { name: 'ส่ง' }))

    expect(ws.sent).toEqual([JSON.stringify({ text: 'ทดสอบ' })])
  })

  it('shows the online count as a badge once presence arrives', async () => {
    renderWidget()
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit({ type: 'presence', count: 4, usernames: ['a', 'b', 'c', 'd'] }))

    await waitFor(() => expect(screen.getByText('4')).toBeInTheDocument())
  })

  it('the feedback tab submits via POST /feedback and shows a success message', async () => {
    vi.spyOn(api, 'postFeedback').mockResolvedValue({
      id: 1,
      username: 'admin',
      role: 'admin',
      text: 'ข้อความทดสอบ',
      created_at: '2026-01-01T00:00:00Z',
    })
    const user = userEvent.setup()
    renderWidget()
    await user.click(screen.getByRole('button', { name: 'เปิดหน้าต่างเครือข่ายผู้ชม' }))
    await user.click(screen.getByRole('tab', { name: 'ติดต่อแอดมิน' }))

    const textarea = screen.getByLabelText('ข้อความถึงแอดมิน')
    await user.type(textarea, 'ข้อความทดสอบ')
    await user.click(screen.getByRole('button', { name: 'ส่งข้อความ' }))

    await waitFor(() => expect(api.postFeedback).toHaveBeenCalledWith('ข้อความทดสอบ', expect.any(String)))
    expect(await screen.findByText('ส่งข้อความเรียบร้อยแล้วค่ะ ขอบคุณค่ะ')).toBeInTheDocument()
  })
})
