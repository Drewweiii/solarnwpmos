import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import { MockWebSocket } from '../../lib/__tests__/mockWebSocket'
import { VisitorNetwork } from '../VisitorNetwork'

function makeToken(sub: string, role: string) {
  const payload = btoa(JSON.stringify({ sub, role }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
  return `header.${payload}.sig`
}

const ADMIN_TOKEN = makeToken('admin', 'admin')
const VIEWER_TOKEN = makeToken('pttlng', 'viewer')

function renderWidget(token = ADMIN_TOKEN) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', token)
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <VisitorNetwork />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

async function openWidget(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'เปิดหน้าต่างเครือข่ายผู้ชม' }))
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
    await openWidget(user)

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() =>
      ws.emit({
        type: 'history',
        messages: [
          {
            type: 'message',
            id: 1,
            username: 'alice',
            role: 'viewer',
            text: 'สวัสดีค่ะ',
            created_at: '2026-01-01T00:00:00Z',
            display_name: 'Alice',
            avatar: 'fox',
            client_id: 'alice-client',
          },
        ],
      }),
    )

    expect(await screen.findByText('สวัสดีค่ะ')).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
  })

  it('admin skips the profile picker entirely and sends as "admin" with a fixed avatar', async () => {
    const user = userEvent.setup()
    renderWidget(ADMIN_TOKEN)
    await openWidget(user)
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit({ type: 'history', messages: [] }))

    expect(screen.queryByRole('radiogroup', { name: 'เลือก avatar' })).not.toBeInTheDocument()

    const input = screen.getByLabelText('พิมพ์ข้อความแชท')
    await user.type(input, 'ทดสอบ')
    await user.click(screen.getByRole('button', { name: 'ส่ง' }))

    const sent = JSON.parse(ws.sent[0]) as { text: string; display_name: string; avatar: string; client_id: string }
    expect(sent).toMatchObject({ text: 'ทดสอบ', display_name: 'admin', avatar: 'crown' })
    expect(sent.client_id).toEqual(expect.any(String))
  })

  it('a viewer without a saved profile sees the name+avatar setup form before they can chat', async () => {
    const user = userEvent.setup()
    renderWidget(VIEWER_TOKEN)
    await openWidget(user)

    expect(screen.getByLabelText('ชื่อที่แสดง')).toBeInTheDocument()
    expect(screen.queryByLabelText('พิมพ์ข้อความแชท')).not.toBeInTheDocument()

    await user.type(screen.getByLabelText('ชื่อที่แสดง'), 'น้องแมว')
    await user.click(screen.getByRole('radio', { name: 'avatar cat' }))
    await user.click(screen.getByRole('button', { name: 'เริ่มแชท' }))

    expect(await screen.findByLabelText('พิมพ์ข้อความแชท')).toBeInTheDocument()

    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit({ type: 'history', messages: [] }))
    await user.type(screen.getByLabelText('พิมพ์ข้อความแชท'), 'หวัดดี')
    await user.click(screen.getByRole('button', { name: 'ส่ง' }))

    const sent = JSON.parse(ws.sent[0]) as { display_name: string; avatar: string }
    expect(sent).toMatchObject({ display_name: 'น้องแมว', avatar: 'cat' })
  })

  it('remembers a saved viewer profile across remounts and offers an edit-profile button', async () => {
    const user = userEvent.setup()
    const { unmount } = renderWidget(VIEWER_TOKEN)
    await openWidget(user)
    await user.type(screen.getByLabelText('ชื่อที่แสดง'), 'คนดูเว็บ')
    await user.click(screen.getByRole('button', { name: 'เริ่มแชท' }))
    await screen.findByLabelText('พิมพ์ข้อความแชท')
    unmount()

    renderWidget(VIEWER_TOKEN)
    await openWidget(user)
    expect(screen.queryByLabelText('ชื่อที่แสดง')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '✏️ คนดูเว็บ' })).toBeInTheDocument()
  })

  it('sending a chat message goes out over the socket with the profile fields attached', async () => {
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit({ type: 'history', messages: [] }))

    const input = screen.getByLabelText('พิมพ์ข้อความแชท')
    await user.type(input, 'ทดสอบ')
    await user.click(screen.getByRole('button', { name: 'ส่ง' }))

    const sent = JSON.parse(ws.sent[0]) as { text: string }
    expect(sent.text).toBe('ทดสอบ')
  })

  it('shows an unread badge for messages from someone else while the panel is closed, and clears it on open', async () => {
    const user = userEvent.setup()
    renderWidget()
    // Open once so the socket connects and we can grab it, then close again.
    await openWidget(user)
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit({ type: 'history', messages: [] }))
    await user.click(screen.getByRole('button', { name: 'ปิดกล่องเครือข่ายผู้ชม' }))

    act(() =>
      ws.emit({
        type: 'message',
        id: 5,
        username: 'someone',
        role: 'viewer',
        text: 'แวะมาทัก',
        created_at: '2026-01-01T00:00:00Z',
        display_name: 'someone',
        avatar: 'dog',
        client_id: 'a-different-browser',
      }),
    )

    await waitFor(() => expect(screen.getByText('1')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /เปิดหน้าต่างเครือข่ายผู้ชม/ }))
    await waitFor(() => expect(screen.queryByText('1')).not.toBeInTheDocument())
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
    await openWidget(user)
    await user.click(screen.getByRole('tab', { name: 'ติดต่อแอดมิน' }))

    const textarea = screen.getByLabelText('ข้อความถึงแอดมิน')
    await user.type(textarea, 'ข้อความทดสอบ')
    await user.click(screen.getByRole('button', { name: 'ส่งข้อความ' }))

    await waitFor(() => expect(api.postFeedback).toHaveBeenCalledWith('ข้อความทดสอบ', expect.any(String)))
    expect(await screen.findByText('ส่งข้อความเรียบร้อยแล้วค่ะ ขอบคุณค่ะ')).toBeInTheDocument()
  })
})
