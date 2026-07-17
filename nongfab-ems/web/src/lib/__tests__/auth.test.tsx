import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '../auth'
import * as api from '../api'

// A valid-shaped (but fake) JWT: header.payload.signature, where payload
// base64url-decodes to {"sub":"a","role":"viewer"} - decodeClaims() only
// reads the payload segment, never verifies the signature client-side (the
// backend does that on every request regardless, see auth.tsx's own comment).
const FAKE_TOKEN = 'header.eyJzdWIiOiJhIiwicm9sZSI6InZpZXdlciJ9.sig'

function Probe() {
  const { token, autoLogoutReason, forceLogout, logout } = useAuth()
  return (
    <div>
      <span data-testid="token">{token ?? 'none'}</span>
      <span data-testid="reason">{autoLogoutReason ?? 'none'}</span>
      <button onClick={() => forceLogout('เว็บไซต์มีการอัปเดตใหม่')}>force</button>
      <button onClick={() => logout()}>manual</button>
    </div>
  )
}

describe('AuthProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('nongfab_ems_token', FAKE_TOKEN)
  })

  it('forceLogout clears the token and records a reason', async () => {
    const user = userEvent.setup()
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    expect(screen.getByTestId('token')).toHaveTextContent(FAKE_TOKEN)

    await user.click(screen.getByText('force'))

    expect(screen.getByTestId('token')).toHaveTextContent('none')
    expect(screen.getByTestId('reason')).toHaveTextContent('เว็บไซต์มีการอัปเดตใหม่')
  })

  it('manual logout clears the token without setting a reason', async () => {
    const user = userEvent.setup()
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await user.click(screen.getByText('manual'))

    expect(screen.getByTestId('token')).toHaveTextContent('none')
    expect(screen.getByTestId('reason')).toHaveTextContent('none')
  })

  it('registers an unauthorized handler on mount that force-logs-out with a reason', async () => {
    const spy = vi.spyOn(api, 'setUnauthorizedHandler')
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    const registeredHandler = spy.mock.calls.find(([handler]) => handler != null)?.[0]
    expect(registeredHandler).toBeInstanceOf(Function)

    registeredHandler!()

    await waitFor(() => expect(screen.getByTestId('token')).toHaveTextContent('none'))
    expect(screen.getByTestId('reason')).not.toHaveTextContent('none')
  })
})
