import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Login } from '../Login'
import { AuthProvider, useAuth } from '../../lib/auth'
import * as api from '../../lib/api'

// Simulates arriving at the Login screen via a forced logout (session
// expired, or - as of 2026-07-17 - a redeploy - see lib/deployWatch.ts)
// instead of a fresh unauthenticated visit, so the notice's rendering can
// be tested without going through a real 401 round-trip.
function LoginAfterForcedLogout({ reason }: { reason: string }) {
  const { forceLogout } = useAuth()
  useEffect(() => {
    forceLogout(reason)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return <Login />
}

describe('Login', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('signs in and stores the token on success', async () => {
    vi.spyOn(api, 'login').mockResolvedValue({ access_token: 'a.b.c', token_type: 'bearer' })
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText(/username/i), 'admin')
    await user.type(screen.getByLabelText(/password/i), 'admin-demo-pw')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(localStorage.getItem('nongfab_ems_token')).toBe('a.b.c'))
  })

  it('shows an error message on failed login', async () => {
    vi.spyOn(api, 'login').mockRejectedValue(new api.ApiError(401, 'incorrect username or password'))
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText(/username/i), 'admin')
    await user.type(screen.getByLabelText(/password/i), 'wrong')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/incorrect username or password/i)
  })

  it('shows the auto-logout reason when arriving via a forced logout', async () => {
    render(
      <AuthProvider>
        <LoginAfterForcedLogout reason="เว็บไซต์มีการอัปเดตใหม่ กรุณาเข้าสู่ระบบอีกครั้ง" />
      </AuthProvider>,
    )

    expect(await screen.findByRole('status')).toHaveTextContent('เว็บไซต์มีการอัปเดตใหม่ กรุณาเข้าสู่ระบบอีกครั้ง')
  })

  it('does not show any notice on a fresh, non-forced visit', () => {
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    )

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
