import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import { AuthProvider } from '../../lib/auth'
import { Layout } from '../Layout'

function makeToken(sub: string, role: string) {
  const payload = btoa(JSON.stringify({ sub, role }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
  return `header.${payload}.sig`
}

function renderLayout(token = makeToken('admin', 'admin')) {
  localStorage.setItem('nongfab_ems_token', token)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/forecast']}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/forecast" element={<p>เนื้อหาแดชบอร์ด</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('Layout - post-login chat profile gate', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('blocks the dashboard behind a full-screen name/avatar setup when no chat profile is saved yet', () => {
    renderLayout()
    expect(screen.getByRole('heading', { name: 'ก่อนเข้าเว็บ...' })).toBeInTheDocument()
    expect(screen.getByLabelText('ชื่อที่แสดง')).toBeInTheDocument()
    expect(screen.queryByText('เนื้อหาแดชบอร์ด')).not.toBeInTheDocument()
    expect(screen.queryByText('Nong Fab Solar EMS')).not.toBeInTheDocument()
  })

  it('reveals the dashboard immediately after saving a profile, with no page reload needed', async () => {
    const user = userEvent.setup()
    renderLayout()

    await user.type(screen.getByLabelText('ชื่อที่แสดง'), 'ผู้ชมทดสอบ')
    await user.click(screen.getByRole('button', { name: 'เริ่มแชท' }))

    expect(await screen.findByText('เนื้อหาแดชบอร์ด')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'ก่อนเข้าเว็บ...' })).not.toBeInTheDocument()
  })

  it('skips the gate entirely on a repeat visit once a profile already exists', () => {
    localStorage.setItem('nongfab_chat_profile', JSON.stringify({ displayName: 'คนเดิม', avatarId: 'cat' }))
    renderLayout()
    expect(screen.getByText('เนื้อหาแดชบอร์ด')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'ก่อนเข้าเว็บ...' })).not.toBeInTheDocument()
  })
})

describe('Layout - Simulation/Financial nav links hidden from viewer', () => {
  beforeEach(() => {
    localStorage.clear()
    // Skip the chat-profile gate above so the nav itself is reachable.
    localStorage.setItem('nongfab_chat_profile', JSON.stringify({ displayName: 'คนเดิม', avatarId: 'cat' }))
  })

  it('hides Simulation and Financial for a viewer', () => {
    renderLayout(makeToken('pttlng', 'viewer'))
    expect(screen.queryByRole('link', { name: 'Simulation' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Financial' })).not.toBeInTheDocument()
    // Everything else stays visible for a viewer.
    expect(screen.getByRole('link', { name: 'Forecast' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '3D View' })).toBeInTheDocument()
  })

  it('shows Simulation and Financial for an operator', () => {
    renderLayout(makeToken('op', 'operator'))
    expect(screen.getByRole('link', { name: 'Simulation' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Financial' })).toBeInTheDocument()
  })

  it('shows Simulation and Financial for an admin', () => {
    renderLayout(makeToken('admin', 'admin'))
    expect(screen.getByRole('link', { name: 'Simulation' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Financial' })).toBeInTheDocument()
  })
})
