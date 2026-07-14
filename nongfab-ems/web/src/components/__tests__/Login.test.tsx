import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Login } from '../Login'
import { AuthProvider } from '../../lib/auth'
import * as api from '../../lib/api'

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
})
