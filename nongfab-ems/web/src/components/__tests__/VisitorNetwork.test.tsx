import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
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
 * picker before the contact list is reachable - see VisitorNetwork.tsx's
 * docstring. Landing on the contact list (not directly on a chat input) is
 * itself the point of this rework - see useChatSocket.ts's docstring: a
 * conversation can no longer be reached without picking who to talk to
 * first, since there is no more single shared public room.
 */
async function setupProfile(user: ReturnType<typeof userEvent.setup>, name = 'ทดสอบ', avatarId = 'cat') {
  await user.type(screen.getByLabelText('ชื่อที่แสดง'), name)
  await user.click(screen.getByRole('radio', { name: `avatar ${avatarId}` }))
  await user.click(screen.getByRole('button', { name: 'เริ่มแชท' }))
  await screen.findByText('ยังไม่มีผู้ชมคนอื่นออนไลน์ตอนนี้ - รอสักครู่แล้วลองดูใหม่นะคะ')
}

/** Announces `peerClientId` as online (the server's own `online_users` push
 * - see ws_chat.py), then clicks that contact to open a private thread with
 * them, and waits for the thread's message input to appear.
 */
async function openThreadWith(
  user: ReturnType<typeof userEvent.setup>,
  ws: MockWebSocket,
  peerClientId: string,
  peerName = 'Alice',
  avatar = 'fox',
  role = 'viewer',
) {
  act(() => ws.emit({ type: 'online_users', users: [{ client_id: peerClientId, display_name: peerName, avatar, role }] }))
  await user.click(await screen.findByRole('button', { name: new RegExp(peerName) }))
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
    vi.stubGlobal('speechSynthesis', { speak: vi.fn(), cancel: vi.fn(), getVoices: vi.fn(() => []), addEventListener: vi.fn() })
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
    // Any thread opened via a contact seen only in `online_users` (not yet
    // via a live message) fetches its history from the server - stub a
    // blank page by default so tests that don't care about this don't have
    // to mock it individually. Tests that do care override with
    // mockResolvedValueOnce before opening that thread.
    vi.spyOn(api, 'getChatHistory').mockResolvedValue({ messages: [] })
  })

  it('starts closed with just the toggle button visible', () => {
    renderWidget()
    expect(screen.getByRole('button', { name: 'เปิดหน้าต่างเครือข่ายผู้ชม' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('opens the panel on an empty contact list until someone else is online, then opening their thread loads its history', async () => {
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    await setupProfile(user)

    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    vi.spyOn(api, 'getChatHistory').mockResolvedValueOnce({
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
          recipient_client_id: 'me',
        },
      ],
    })

    await openThreadWith(user, ws, 'alice-client', 'Alice')

    expect(await screen.findByText('สวัสดีค่ะ')).toBeInTheDocument()
    expect(api.getChatHistory).toHaveBeenCalledWith(expect.any(String), 'alice-client', expect.any(String), undefined, 50)
  })

  it('shows น้อง Solar in the name+avatar setup form', async () => {
    const user = userEvent.setup()
    renderWidget(VIEWER_TOKEN)
    await openWidget(user)

    expect(screen.getByText(/น้อง Solar/)).toBeInTheDocument()
  })

  it('a viewer without a saved profile sees the name+avatar setup form before they can pick a contact to chat with', async () => {
    const user = userEvent.setup()
    renderWidget(VIEWER_TOKEN)
    await openWidget(user)

    expect(screen.getByLabelText('ชื่อที่แสดง')).toBeInTheDocument()
    expect(screen.queryByText('ยังไม่มีผู้ชมคนอื่นออนไลน์ตอนนี้ - รอสักครู่แล้วลองดูใหม่นะคะ')).not.toBeInTheDocument()

    await user.type(screen.getByLabelText('ชื่อที่แสดง'), 'น้องแมว')
    await user.click(screen.getByRole('radio', { name: 'avatar cat' }))
    await user.click(screen.getByRole('button', { name: 'เริ่มแชท' }))

    expect(await screen.findByText('ยังไม่มีผู้ชมคนอื่นออนไลน์ตอนนี้ - รอสักครู่แล้วลองดูใหม่นะคะ')).toBeInTheDocument()

    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    await openThreadWith(user, ws, 'alice-client', 'Alice')
    await user.type(screen.getByLabelText('พิมพ์ข้อความแชท'), 'หวัดดี')
    await user.click(screen.getByRole('button', { name: 'ส่ง' }))

    const sent = JSON.parse(ws.sent.at(-1)!) as { display_name: string; avatar: string; recipient_client_id: string }
    expect(sent).toMatchObject({ display_name: 'น้องแมว', avatar: 'cat', recipient_client_id: 'alice-client' })
  })

  it('admin also gets the name/avatar picker, and the raw (unprefixed) values are what get sent', async () => {
    const user = userEvent.setup()
    renderWidget(ADMIN_TOKEN)
    await openWidget(user)
    expect(screen.getByLabelText('ชื่อที่แสดง')).toBeInTheDocument()
    await setupProfile(user, 'สมชาย', 'lion')

    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    await openThreadWith(user, ws, 'alice-client', 'Alice')
    await user.type(screen.getByLabelText('พิมพ์ข้อความแชท'), 'ทดสอบ')
    await user.click(screen.getByRole('button', { name: 'ส่ง' }))

    // No "admin " prefix added client-side - ws_chat.py applies it server-side.
    const sent = JSON.parse(ws.sent.at(-1)!) as { text: string; display_name: string; avatar: string; recipient_client_id: string }
    expect(sent).toMatchObject({ text: 'ทดสอบ', display_name: 'สมชาย', avatar: 'lion', recipient_client_id: 'alice-client' })
  })

  it('renders the server-provided display_name as-is, including the "admin " prefix on an admin message', async () => {
    const user = userEvent.setup()
    renderWidget(VIEWER_TOKEN)
    await openWidget(user)
    await setupProfile(user)

    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    // Arrives live from someone never announced via online_users - the
    // contact list should still pick them up (see useChatSocket.ts's
    // rememberPeer) so their thread can be opened.
    act(() =>
      ws.emit({
        type: 'message',
        id: 1,
        username: 'boss',
        role: 'admin',
        text: 'ประกาศจากแอดมิน',
        created_at: '2026-01-01T00:00:00Z',
        display_name: 'admin สมชาย',
        avatar: 'lion',
        client_id: 'admin-client',
        recipient_client_id: 'me',
      }),
    )

    await user.click(await screen.findByRole('button', { name: /admin สมชาย/ }))
    expect(await screen.findByText('ประกาศจากแอดมิน')).toBeInTheDocument()
  })

  it('a message from one peer never shows up in a different peer thread', async () => {
    const user = userEvent.setup()
    const { container } = renderWidget()
    await openWidget(user)
    await setupProfile(user)

    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    act(() =>
      ws.emit({
        type: 'online_users',
        users: [
          { client_id: 'alice-client', display_name: 'Alice', avatar: 'fox', role: 'viewer' },
          { client_id: 'bob-client', display_name: 'Bob', avatar: 'dog', role: 'viewer' },
        ],
      }),
    )
    act(() =>
      ws.emit({
        type: 'message',
        id: 1,
        username: 'bob',
        role: 'viewer',
        text: 'ข้อความลับของบ๊อบ',
        created_at: '2026-01-01T00:00:00Z',
        display_name: 'Bob',
        avatar: 'dog',
        client_id: 'bob-client',
        recipient_client_id: 'me',
      }),
    )

    await user.click(await screen.findByRole('button', { name: /Alice/ }))
    await screen.findByLabelText('พิมพ์ข้อความแชท')
    // Scoped to the open thread's own message list - the incoming-message
    // toast (added 2026-07-18) legitimately shows a preview of Bob's
    // message elsewhere on screen at the same time; that's not the bug this
    // test guards against (a message rendered inside the wrong thread).
    const messageList = () => container.querySelector('.visitor-messages')!
    expect(within(messageList()).queryByText('ข้อความลับของบ๊อบ')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'กลับไปหน้ารายชื่อผู้ชม' }))
    await user.click(await screen.findByRole('button', { name: /Bob/ }))
    expect(await within(messageList()).findByText('ข้อความลับของบ๊อบ')).toBeInTheDocument()
  })

  it('remembers a saved viewer profile across remounts and offers an edit-profile button', async () => {
    const user = userEvent.setup()
    const { unmount } = renderWidget(VIEWER_TOKEN)
    await openWidget(user)
    await user.type(screen.getByLabelText('ชื่อที่แสดง'), 'คนดูเว็บ')
    await user.click(screen.getByRole('button', { name: 'เริ่มแชท' }))
    await screen.findByRole('button', { name: '✏️ คนดูเว็บ' })
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

  it('sending a chat message goes out over the socket addressed to the open thread, with the profile fields attached', async () => {
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    await setupProfile(user)
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    await openThreadWith(user, ws, 'alice-client', 'Alice')

    const input = screen.getByLabelText('พิมพ์ข้อความแชท')
    await user.type(input, 'ทดสอบ')
    await user.click(screen.getByRole('button', { name: 'ส่ง' }))

    const sent = JSON.parse(ws.sent.at(-1)!) as { text: string; recipient_client_id: string }
    expect(sent).toMatchObject({ text: 'ทดสอบ', recipient_client_id: 'alice-client' })
  })

  it('shows a total unread badge for a message from someone else while the panel is closed, cleared only once that specific thread is opened', async () => {
    const user = userEvent.setup()
    const { container } = renderWidget()
    await openWidget(user)
    await setupProfile(user)
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
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
        recipient_client_id: 'me',
      }),
    )

    await waitFor(() => expect(container.querySelector('.visitor-unread-badge')?.textContent).toBe('1'))

    await user.click(screen.getByRole('button', { name: /เปิดหน้าต่างเครือข่ายผู้ชม/ }))
    // Still shows the badge - only opening that specific person's thread
    // (not just the contact-list view) counts as "read" now, since each
    // conversation is its own private thread.
    expect(container.querySelector('.visitor-unread-badge')?.textContent).toBe('1')
    expect(container.querySelector('.visitor-contact-unread')?.textContent).toBe('1')

    await user.click(await screen.findByRole('button', { name: /someone/ }))
    await waitFor(() => expect(container.querySelector('.visitor-unread-badge')).not.toBeInTheDocument())
  })

  describe('การแจ้งเตือนข้อความเข้า (incoming-message notification, added 2026-07-18)', () => {
    it('shows a toast naming the sender and a preview when their message arrives while the panel is closed', async () => {
      const user = userEvent.setup()
      renderWidget()
      await openWidget(user)
      await setupProfile(user)
      const ws = MockWebSocket.instances[0]
      act(() => ws.open())
      await user.click(screen.getByRole('button', { name: 'ปิดกล่องเครือข่ายผู้ชม' }))

      act(() =>
        ws.emit({
          type: 'message',
          id: 5,
          username: 'someone',
          role: 'viewer',
          text: 'แวะมาทักหน่อยนะ',
          created_at: '2026-01-01T00:00:00Z',
          display_name: 'Someone',
          avatar: 'dog',
          client_id: 'a-different-browser',
          recipient_client_id: 'me',
        }),
      )

      expect(await screen.findByText('💬 Someone ทักคุณมา')).toBeInTheDocument()
      expect(screen.getByText('แวะมาทักหน่อยนะ')).toBeInTheDocument()
    })

    it('clicking the toast opens the panel straight to that sender\'s thread', async () => {
      const user = userEvent.setup()
      renderWidget()
      await openWidget(user)
      await setupProfile(user)
      const ws = MockWebSocket.instances[0]
      act(() => ws.open())
      await user.click(screen.getByRole('button', { name: 'ปิดกล่องเครือข่ายผู้ชม' }))

      act(() =>
        ws.emit({
          type: 'message',
          id: 5,
          username: 'someone',
          role: 'viewer',
          text: 'สวัสดีครับ',
          created_at: '2026-01-01T00:00:00Z',
          display_name: 'Someone',
          avatar: 'dog',
          client_id: 'a-different-browser',
          recipient_client_id: 'me',
        }),
      )

      await user.click(await screen.findByText('💬 Someone ทักคุณมา'))

      expect(await screen.findByText('สวัสดีครับ')).toBeInTheDocument()
      expect(screen.queryByText('💬 Someone ทักคุณมา')).not.toBeInTheDocument()
    })

    it('the × button dismisses the toast without opening the panel', async () => {
      const user = userEvent.setup()
      renderWidget()
      await openWidget(user)
      await setupProfile(user)
      const ws = MockWebSocket.instances[0]
      act(() => ws.open())
      await user.click(screen.getByRole('button', { name: 'ปิดกล่องเครือข่ายผู้ชม' }))

      act(() =>
        ws.emit({
          type: 'message',
          id: 5,
          username: 'someone',
          role: 'viewer',
          text: 'สวัสดีครับ',
          created_at: '2026-01-01T00:00:00Z',
          display_name: 'Someone',
          avatar: 'dog',
          client_id: 'a-different-browser',
          recipient_client_id: 'me',
        }),
      )
      await screen.findByText('💬 Someone ทักคุณมา')

      await user.click(screen.getByRole('button', { name: 'ปิดการแจ้งเตือน' }))

      expect(screen.queryByText('💬 Someone ทักคุณมา')).not.toBeInTheDocument()
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('does not show a toast for a message in the thread already open on screen', async () => {
      const user = userEvent.setup()
      renderWidget()
      await openWidget(user)
      await setupProfile(user)
      const ws = MockWebSocket.instances[0]
      act(() => ws.open())
      await openThreadWith(user, ws, 'alice-client', 'Alice')

      act(() =>
        ws.emit({
          type: 'message',
          id: 5,
          username: 'alice',
          role: 'viewer',
          text: 'ข้อความในห้องที่เปิดอยู่',
          created_at: '2026-01-01T00:00:00Z',
          display_name: 'Alice',
          avatar: 'fox',
          client_id: 'alice-client',
          recipient_client_id: 'me',
        }),
      )

      await screen.findByText('ข้อความในห้องที่เปิดอยู่') // the bubble itself did arrive
      expect(screen.queryByText(/ทักคุณมา/)).not.toBeInTheDocument()
    })

    it('shows a sticker-specific preview, not the raw encoded text', async () => {
      const user = userEvent.setup()
      renderWidget()
      await openWidget(user)
      await setupProfile(user)
      const ws = MockWebSocket.instances[0]
      act(() => ws.open())
      await user.click(screen.getByRole('button', { name: 'ปิดกล่องเครือข่ายผู้ชม' }))

      act(() =>
        ws.emit({
          type: 'message',
          id: 5,
          username: 'someone',
          role: 'viewer',
          text: '::sticker::love',
          created_at: '2026-01-01T00:00:00Z',
          display_name: 'Someone',
          avatar: 'dog',
          client_id: 'a-different-browser',
          recipient_client_id: 'me',
        }),
      )

      expect(await screen.findByText(/ส่งสติกเกอร์.*รักนะ/)).toBeInTheDocument()
      expect(screen.queryByText('::sticker::love')).not.toBeInTheDocument()
    })
  })

  it('sending a sticker goes out as an encoded text payload, not a plain message', async () => {
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    await setupProfile(user)
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    await openThreadWith(user, ws, 'alice-client', 'Alice')

    await user.click(screen.getByRole('button', { name: 'เปิดแผงสติกเกอร์' }))
    await user.click(screen.getByRole('button', { name: 'ส่งสติกเกอร์ สวัสดี' }))

    const sent = JSON.parse(ws.sent.at(-1)!) as { text: string }
    expect(sent.text).toBe('::sticker::hello')
  })

  it('renders a received sticker message as a big emoji + caption, not raw text, and speaks its caption aloud', async () => {
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    await setupProfile(user)
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    await openThreadWith(user, ws, 'alice-client', 'Alice')

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
        client_id: 'alice-client',
        recipient_client_id: 'me',
      }),
    )

    expect(await screen.findByLabelText('สติกเกอร์: สู้ๆ')).toBeInTheDocument()
    expect(screen.queryByText('::sticker::fight')).not.toBeInTheDocument()
    expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1)
  })

  it('does not speak a sticker replayed from GET /chat/history, only ones that arrive live', async () => {
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    await setupProfile(user)
    const ws = MockWebSocket.instances[0]
    act(() => ws.open())
    vi.spyOn(api, 'getChatHistory').mockResolvedValueOnce({
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
          client_id: 'alice-client',
          recipient_client_id: 'me',
        },
      ],
    })

    await openThreadWith(user, ws, 'alice-client', 'Alice')

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
