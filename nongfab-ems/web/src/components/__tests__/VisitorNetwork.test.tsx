import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import { saveChatProfile } from '../../lib/chatProfile'
import type { ChatMessage } from '../../lib/types'
import type { ChatSocketState, ConversationState, Contact, LocalChatMessage } from '../../lib/useChatSocket'
import { VisitorNetwork } from '../VisitorNetwork'

// The chat transport (REST polling) is covered directly in
// useChatSocket.test.tsx. Here we mock the hook so these tests exercise the
// *UI* against a controlled ChatSocketState, independent of how messages
// actually travel - much less brittle than driving a fake transport.
let mockState: ChatSocketState
let capturedOnLive: ((m: ChatMessage) => void) | undefined

vi.mock('../../lib/useChatSocket', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/useChatSocket')>()
  return {
    ...actual,
    useChatSocket: (_profile: unknown, _peer: unknown, _active: unknown, onLive?: (m: ChatMessage) => void) => {
      capturedOnLive = onLive
      return mockState
    },
  }
})

function makeToken(sub: string, role: string) {
  const payload = btoa(JSON.stringify({ sub, role })).replace(/\+/g, '-').replace(/\//g, '_')
  return `header.${payload}.sig`
}
const ADMIN_TOKEN = makeToken('admin', 'admin')

function message(overrides: Partial<LocalChatMessage> = {}): LocalChatMessage {
  return {
    type: 'message',
    id: 1,
    username: 'alice',
    role: 'viewer',
    text: 'hi there',
    created_at: '2026-01-01T00:00:00Z',
    display_name: 'Alice',
    avatar: 'fox',
    client_id: 'peer-1',
    recipient_client_id: 'my-client-id',
    ...overrides,
  }
}

function conversation(messages: LocalChatMessage[], unreadCount = 0): ConversationState {
  return { messages, loaded: true, hasMoreOlder: false, loadingOlder: false, unreadCount }
}

function contact(overrides: Partial<Contact> = {}): Contact {
  return { clientId: 'peer-1', displayName: 'Alice', avatar: 'fox', role: 'viewer', online: true, ...overrides }
}

function makeState(overrides: Partial<ChatSocketState> = {}): ChatSocketState {
  return {
    contacts: [],
    connected: true,
    totalUnreadCount: 0,
    conversations: {},
    openConversation: vi.fn(),
    sendMessage: vi.fn(),
    retrySend: vi.fn(),
    loadOlder: vi.fn(),
    updateProfile: vi.fn(),
    ...overrides,
  }
}

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
    mockState = makeState()
    capturedOnLive = undefined
    // Pin this browser's client id so own-message bubbles (client_id
    // 'my-client-id') are recognised as ours; then save a profile so tests
    // land straight on the chat, not the setup gate (exercised on its own).
    localStorage.setItem('nongfab_chat_client_id', 'my-client-id')
    saveChatProfile('ทดสอบ', 'cat')
  })

  it('gates chat behind the name/avatar setup until a profile is saved', async () => {
    localStorage.removeItem('nongfab_chat_profile')
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    expect(screen.getByLabelText('ชื่อที่แสดง')).toBeInTheDocument()

    await user.type(screen.getByLabelText('ชื่อที่แสดง'), 'มานี')
    await user.click(screen.getByRole('radio', { name: 'avatar cat' }))
    await user.click(screen.getByRole('button', { name: 'เริ่มแชท' }))
    expect(await screen.findByText(/ยังไม่มีผู้ชมคนอื่นออนไลน์/)).toBeInTheDocument()
  })

  it('shows the online contact count and lists contacts', async () => {
    mockState = makeState({ contacts: [contact()] })
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    expect(screen.getByRole('tab', { name: /แชท \(1 ออนไลน์\)/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Alice/ })).toBeInTheDocument()
  })

  it('opens a thread and renders that conversation’s messages', async () => {
    mockState = makeState({
      contacts: [contact()],
      conversations: { 'peer-1': conversation([message({ id: 5, text: 'สวัสดีจ้า' })]) },
    })
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    await user.click(screen.getByRole('button', { name: /Alice/ }))
    expect(mockState.openConversation).toHaveBeenCalledWith('peer-1')
    expect(await screen.findByText('สวัสดีจ้า')).toBeInTheDocument()
  })

  it('sends a message through the hook', async () => {
    mockState = makeState({ contacts: [contact()], conversations: { 'peer-1': conversation([]) } })
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    await user.click(screen.getByRole('button', { name: /Alice/ }))
    await user.type(screen.getByLabelText('พิมพ์ข้อความแชท'), 'ทดสอบส่ง')
    await user.click(screen.getByRole('button', { name: 'ส่ง' }))
    expect(mockState.sendMessage).toHaveBeenCalledWith('peer-1', 'ทดสอบส่ง')
  })

  it('shows a pending own message and a retry affordance on a failed one', async () => {
    const own = { client_id: 'my-client-id', recipient_client_id: 'peer-1', display_name: 'ทดสอบ', avatar: 'cat' }
    mockState = makeState({
      contacts: [contact()],
      conversations: {
        'peer-1': conversation([
          message({ ...own, id: 9, text: 'กำลังไป', pending: true, clientTempId: 't1' }),
          message({ ...own, id: 10, text: 'ล้มเหลว', failed: true, clientTempId: 't2' }),
        ]),
      },
    })
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    await user.click(screen.getByRole('button', { name: /Alice/ }))

    expect(screen.getByText('กำลังส่ง…')).toBeInTheDocument()
    const retry = screen.getByRole('button', { name: /ส่งไม่สำเร็จ/ })
    await user.click(retry)
    expect(mockState.retrySend).toHaveBeenCalledWith('peer-1', 't2')
  })

  it('shows a toast when a live message arrives for a thread that is not open', async () => {
    mockState = makeState({ contacts: [contact()] })
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user) // on the contact list, no thread open
    act(() => capturedOnLive?.(message({ id: 3, client_id: 'peer-1', text: 'ทักหน่อย' })))
    expect(await screen.findByText(/Alice ทักคุณมา/)).toBeInTheDocument()
    expect(screen.getByText('ทักหน่อย')).toBeInTheDocument()
  })

  it('surfaces the total unread count on the collapsed toggle', () => {
    mockState = makeState({ totalUnreadCount: 4 })
    renderWidget()
    expect(within(screen.getByRole('button', { name: 'เปิดหน้าต่างเครือข่ายผู้ชม' })).getByText('4')).toBeInTheDocument()
  })

  it('submits admin feedback through the REST endpoint', async () => {
    const postFeedback = vi.spyOn(api, 'postFeedback').mockResolvedValue({
      id: 1,
      username: 'admin',
      role: 'admin',
      text: 'ping',
      created_at: '2026-01-01T00:00:00Z',
      display_name: null,
    })
    const user = userEvent.setup()
    renderWidget()
    await openWidget(user)
    await user.click(screen.getByRole('tab', { name: 'ติดต่อแอดมิน' }))
    await user.type(screen.getByLabelText('ข้อความถึงแอดมิน'), 'ping')
    await user.click(screen.getByRole('button', { name: 'ส่งข้อความ' }))
    await waitFor(() => expect(postFeedback).toHaveBeenCalled())
    expect(postFeedback.mock.calls[0][0]).toBe('ping')
  })
})
