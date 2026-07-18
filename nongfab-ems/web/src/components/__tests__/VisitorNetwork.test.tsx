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

/** Every role (including admin) now goes through the same name/avatar
 * picker before ChatTab is reachable - see VisitorNetwork.tsx's docstring.
 */
async function setupProfile(user: ReturnType<typeof userEvent.setup>, name = 'ทดสอบ', avatarId = 'cat') {
  await user.type(screen.getByLabelText('ชื่อที่แสดง'), name)
  await user.click(screen.getByRole('radio', { name: `avatar ${avatarId}` }))
  await user.click(screen.getByRole('button', { name: 'เริ่มแชท' }))
  await screen.findByLabelText('พิมพ์ข้อความแชท')
}

describe('VisitorNetwork', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    MockWebSocket.instances.length = 0
    vi.stubGlobal('WebSocket', MockWebSocket)
    // jsdom has no speechSynthesis - stub it so sticker-send tests (which
    // exercise speakSticker()) don't crash on a missing global.
    vi.stubGlobal('speechSynthesis', { speak: vi.fn() })
    vi.stubGlobal(
      'SpeechSynthesisUtterance',
      class {
        text: string
        lang = ''
        constructor(text: string) {
          this.text = text
        }
      },
    )
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
    await setupProfile(user)

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

  it('shows น้อง Solar in the name+avatar setup form', async () => {
    const user = userEvent.setup()
    renderWidget(VIEWER_TOKEN)
    await openWidget(user)

    expect(screen.getByText(/น้อง Solar/)).toBeInTheDocument()
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

  it('admin also gets the name/avatar picker, and the raw (unprefixed) values are what get sent', async () => {
    const user = userEvent.setup()
    renderWidget(ADMIN_TOKEN)
    await openWidget(user)
    expect(screen.getByLabelText('ชื่อที่แสดง')).toBeInTheDocument()
    await setupProfile(user, 'สมชาย', 'lion')

    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit({ type: 'history', messages: [] }))
    await user.type(screen.getByLabelText('พิมพ์ข้อความแชท'), 'ทดสอบ')
    await user.click(screen.getByRole('button', { name: 'ส่ง' }))

    // No "admin " prefix added client-side - ws_chat.py applies it server-side.
    const sent = JSON.parse(ws.sent[0]) as { text: string; display_name: string; avatar: string; client_id: string }
    expect(sent).toMatchObject({ text: 'ทดสอบ', display_name: 'สมชาย', avatar: 'lion' })
    expect(sent.client_id).toEqual(expect.any(String))
  })

  it('renders the server-provided display_name as-is, including the "admin " prefix on an admin message', async () => {
    const user = userEvent.setup()
    renderWidget(VIEWER_TOKEN)
    await openWidget(user)
    await setupProfile(user)

    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() =>
      ws.emit({
        type: 'history',
        messages: [
          {
            type: 'message',
            id: 1,
            username: 'boss',
            role: 'admin',
            text: 'ประกาศจากแอดมิน',
            created_at: '2026-01-01T00:00:00Z',
            display_name: 'admin สมชาย',
            avatar: 'lion',
            client_id: 'admin-client',
          },
        ],
      }),
    )

    expect(await screen.findByText('admin สมชาย')).toBeInTheDocument()
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

  it('editing an existing profile prefills the current name/avatar, can be cancelled, and saving updates it in place', async () => {
    const user = userEvent.setup()
    renderWidget(VIEWER_TOKEN)
    await openWidget(user)
    await user.type(screen.getByLabelText('ชื่อที่แสดง'), 'คนเดิม')
    await user.click(screen.getByRole('radio', { name: 'avatar fox' }))
    await user.click(screen.getByRole('button', { name: 'เริ่มแชท' }))
    await screen.findByRole('button', { name: '✏️ คนเดิม' })

    await user.click(screen.getByRole('button', { name: '✏️ คนเดิม' }))
    const nameInput = screen.getByLabelText('ชื่อที่แสดง') as HTMLInputElement
    expect(nameInput.value).toBe('คนเดิม')
    expect(screen.getByRole('radio', { name: 'avatar fox' })).toHaveAttribute('aria-checked', 'true')

    // Cancelling a reopened edit leaves the saved profile untouched.
    await user.click(screen.getByRole('button', { name: 'ยกเลิก' }))
    expect(screen.getByRole('button', { name: '✏️ คนเดิม' })).toBeInTheDocument()

    // Reopening and actually saving updates the profile in place.
    await user.click(screen.getByRole('button', { name: '✏️ คนเดิม' }))
    await user.clear(screen.getByLabelText('ชื่อที่แสดง'))
    await user.type(screen.getByLabelText('ชื่อที่แสดง'), 'ชื่อใหม่')
    await user.click(screen.getByRole('radio', { name: 'avatar unicorn' }))
    await user.click(screen.getByRole('button', { name: 'บันทึก' }))

    expect(await screen.findByRole('button', { name: '✏️ ชื่อใหม่' })).toBeInTheDocument()
  })

  it('sending a chat message goes out over the socket with the profile fields attached', async () => {
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    await setupProfile(user)
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
    await openWidget(user)
    await setupProfile(user)
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

  it('sending a sticker goes out as an encoded text payload, not a plain message', async () => {
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    await setupProfile(user)
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit({ type: 'history', messages: [] }))

    await user.click(screen.getByRole('button', { name: 'เปิดแผงสติกเกอร์' }))
    await user.click(screen.getByRole('button', { name: 'ส่งสติกเกอร์ สวัสดี' }))

    const sent = JSON.parse(ws.sent[0]) as { text: string }
    expect(sent.text).toBe('::sticker::hello')
  })

  it('renders a received sticker message as a big emoji + caption, not raw text, and speaks its caption aloud', async () => {
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    await setupProfile(user)
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() => ws.emit({ type: 'history', messages: [] }))

    act(() =>
      ws.emit({
        type: 'message',
        id: 9,
        username: 'someone',
        role: 'viewer',
        text: '::sticker::fight',
        created_at: '2026-01-01T00:00:00Z',
        display_name: 'someone',
        avatar: 'dog',
        client_id: 'a-different-browser',
      }),
    )

    expect(await screen.findByLabelText('สติกเกอร์: สู้ๆ')).toBeInTheDocument()
    expect(screen.queryByText('::sticker::fight')).not.toBeInTheDocument()
    expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1)
  })

  it('does not speak stickers replayed from history, only ones that arrive live', async () => {
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    await setupProfile(user)
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() =>
      ws.emit({
        type: 'history',
        messages: [
          {
            type: 'message',
            id: 1,
            username: 'someone',
            role: 'viewer',
            text: '::sticker::love',
            created_at: '2026-01-01T00:00:00Z',
            display_name: 'someone',
            avatar: 'dog',
            client_id: 'a-different-browser',
          },
        ],
      }),
    )

    expect(await screen.findByLabelText('สติกเกอร์: รักนะ')).toBeInTheDocument()
    expect(window.speechSynthesis.speak).not.toHaveBeenCalled()
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
