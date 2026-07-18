import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import App, { RequireOperator } from './App'
import { AuthProvider } from './lib/auth'

describe('App', () => {
  it('renders the login screen when no token is stored', () => {
    localStorage.removeItem('nongfab_ems_token')
    render(<App />)
    expect(screen.getByRole('heading', { name: /Nong Fab Solar EMS/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/Username/i)).toBeInTheDocument()
  })
})

function makeToken(sub: string, role: string) {
  const payload = btoa(JSON.stringify({ sub, role }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
  return `header.${payload}.sig`
}

function renderGuarded(role: string) {
  localStorage.setItem('nongfab_ems_token', makeToken('u', role))
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/financial']}>
        <Routes>
          <Route
            path="/financial"
            element={
              <RequireOperator>
                <p>เนื้อหา Financial</p>
              </RequireOperator>
            }
          />
          <Route path="/forecast" element={<p>เนื้อหา Forecast</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

// Simulation/Financial are operator-and-up - see App.tsx's own RequireOperator
// docstring for why (mirrors the backend's existing require_role("operator")
// on those two POST routes; this is the matching direct-URL guard for the
// pages themselves, added 2026-07-18 alongside hiding their nav links).
describe('RequireOperator', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('redirects a viewer to /forecast instead of rendering the guarded page', () => {
    renderGuarded('viewer')
    expect(screen.getByText('เนื้อหา Forecast')).toBeInTheDocument()
    expect(screen.queryByText('เนื้อหา Financial')).not.toBeInTheDocument()
  })

  it('renders the guarded page for an operator', () => {
    renderGuarded('operator')
    expect(screen.getByText('เนื้อหา Financial')).toBeInTheDocument()
  })

  it('renders the guarded page for an admin', () => {
    renderGuarded('admin')
    expect(screen.getByText('เนื้อหา Financial')).toBeInTheDocument()
  })
})
