import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { FeedbackItem } from '../../lib/types'
import { AdminFeedbackPage } from '../AdminFeedbackPage'

function renderPage(token = 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', token)
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AdminFeedbackPage />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('AdminFeedbackPage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('lists submitted feedback messages', async () => {
    const items: FeedbackItem[] = [
      { id: 2, username: 'pttlng', role: 'viewer', text: 'second message', created_at: '2026-01-02T00:00:00Z', display_name: 'คุณเอ' },
      { id: 1, username: 'pttlng', role: 'viewer', text: 'first message', created_at: '2026-01-01T00:00:00Z', display_name: null },
    ]
    vi.spyOn(api, 'getFeedback').mockResolvedValue(items)

    renderPage()

    expect(await screen.findByText('second message')).toBeInTheDocument()
    expect(screen.getByText('first message')).toBeInTheDocument()
  })

  it('shows an empty state when there are no messages yet', async () => {
    vi.spyOn(api, 'getFeedback').mockResolvedValue([])
    renderPage()
    expect(await screen.findByText('ยังไม่มีข้อความ')).toBeInTheDocument()
  })
})
