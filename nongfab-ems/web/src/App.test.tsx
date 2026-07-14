import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the login screen when no token is stored', () => {
    localStorage.removeItem('nongfab_ems_token')
    render(<App />)
    expect(screen.getByRole('heading', { name: /Nong Fab Solar EMS/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/Username/i)).toBeInTheDocument()
  })
})
