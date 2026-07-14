import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the default scaffold without crashing', () => {
    render(<App />)
    expect(screen.getByText(/Count is 0/i)).toBeInTheDocument()
  })
})
